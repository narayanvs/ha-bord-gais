"""Short-lived, separate-origin HTTPS login test. Never logs request data."""
import asyncio
import html
import ipaddress
import datetime
from pathlib import Path
import tempfile
import os
import json
import logging
import re
import secrets
import ssl
import time
from urllib.parse import urlsplit
from .client import parse_session, PortalError
import aiohttp
from aiohttp import web

BASE = 'https://www.bordgaisenergy.ie'
PORT = 8743
MAX_BYTES = 4 * 1024 * 1024
COOKIE = 'bge_trial'
_LOGGER = logging.getLogger(__name__)


def allowed(method, path):
    if method == 'POST':
        return path == '/api/auth/token'
    return method in ('GET', 'HEAD') and (path in ('/', '/sign-in', '/favicon.ico') or
        path.startswith(('/_next/', '/lib/', '/images/', '/fonts/', '/assets/')))


def rewrite(text, origin):
    # Separate origin means root-relative Next.js resources remain correct.
    return text.replace(BASE, origin).replace(BASE.replace('/', r'\/'), origin.replace('/', r'\/'))


def category(status, data):
    if status == 200:
        return 'login_response_received'
    if status == 429:
        return 'rate_limited'
    words = ' '.join(str(data.get(k, '')) for k in ('message', 'error', 'code')) if isinstance(data, dict) else ''
    if 'captcha' in words.lower():
        return 'captcha_required_or_rejected'
    return 'login_rejected' if status in (400, 401, 403) else 'supplier_error'


def make_certificate(host):
    """Ephemeral TLS key on disk only while the login server is alive."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    folder = tempfile.TemporaryDirectory(prefix='bge-browser-')
    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Temporary local Bord Gais login')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]), critical=False)
            .sign(key, hashes.SHA256()))
        keypath, certpath = Path(folder.name)/'key.pem', Path(folder.name)/'cert.pem'
        keypath.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        os.chmod(keypath, 0o600)
        certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        return folder, certpath, keypath
    except Exception:
        folder.cleanup()
        raise


class BrowserLogin:
    def __init__(self, host, on_complete, reserve=None):
        ip = ipaddress.ip_address(host)
        if ip.version != 4 or not ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_multicast:
            raise ValueError('Use the private LAN address of Home Assistant.')
        self.host = str(ip)
        self.origin = f'https://{self.host}:{PORT}'
        self.start_token = secrets.token_urlsafe(32)
        self.cookie = secrets.token_urlsafe(32)
        self.certificate = None
        self.reserve = reserve
        self.on_complete = on_complete
        self.deadline = time.monotonic() + 900
        self.runner = None
        self.http = None
        self.timer = None
        self.lock = asyncio.Lock()
        self.attempts = 0
        self.last_attempt = 0
        self.result = {'state': 'waiting', 'attempts': 0}
        self.claimed = False

    async def start(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.certificate, cert, key = await asyncio.to_thread(make_certificate, self.host)
        try:
            await asyncio.to_thread(context.load_cert_chain, cert, key)
        except Exception:
            await self.close()
            raise
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35))
        app = web.Application(client_max_size=65536)
        app.router.add_route('*', '/{tail:.*}', self.handle)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        try:
            await web.TCPSite(self.runner, self.host, PORT, ssl_context=context).start()
        except Exception:
            await self.close()
            raise
        self.timer = asyncio.get_running_loop().call_later(900, lambda: asyncio.create_task(self.close()))
        return self.origin + '/start/' + self.start_token

    async def close(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.runner:
            runner, self.runner = self.runner, None
            await runner.cleanup()
        if self.http:
            await self.http.close()
            self.http = None
        self.cookie = ''
        self.start_token = ''
        if self.certificate:
            self.certificate.cleanup()
            self.certificate = None

    def response(self, body, status=200, content_type='text/html'):
        return web.Response(body=body, status=status, content_type=content_type, headers={
            'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
            'Cross-Origin-Opener-Policy': 'same-origin',
        })

    async def handle(self, request):
        if request.host != f'{self.host}:{PORT}' or time.monotonic() >= self.deadline:
            return self.response(b'Test expired or wrong address.', 403)
        path = request.path
        if path.startswith('/start/'):
            token = path[len('/start/'):]
            if request.method != 'GET' or self.claimed or not secrets.compare_digest(token, self.start_token):
                return self.response(b'Invalid or used test link.', 403)
            self.claimed = True
            response = web.Response(status=302, headers={'Location': '/sign-in'})
            response.set_cookie(COOKIE, self.cookie, secure=True, httponly=True, samesite='Lax', max_age=900)
            response.headers['Referrer-Policy'] = 'no-referrer'
            response.headers['Cache-Control'] = 'no-store'
            return response
        if not self.cookie or not secrets.compare_digest(request.cookies.get(COOKIE, ''), self.cookie):
            return self.response(b'Open this test from Home Assistant.', 403)
        if request.method not in ('GET', 'HEAD') and request.headers.get('Origin') != self.origin:
            return self.response(b'Wrong request origin.', 403)
        if path == '/trial-result' and request.method == 'GET':
            return self.response(json.dumps(self.result).encode(), content_type='application/json')
        if path == '/finished' and request.method == 'GET':
            state = self.result['state']
            success = state in ('verified', 'reauth_successful')
            message = {
                'verified': 'Connected. Home Assistant has your renewable session, not your password.',
                'reauth_successful': 'Reconnected. Your Home Assistant session has been renewed.',
                'already_configured': 'These accounts are already configured. Use reauthentication on the existing integration.',
                'wrong_account': 'This login belongs to different accounts. Your existing connection was not changed.',
                'setup_closed': 'The Home Assistant setup flow is no longer available. Start a fresh setup.',
            }.get(state, 'Sign-in is not complete. Return to Home Assistant to check setup.')
            auto_close = 'setTimeout(()=>{try{window.close();}catch(e){}},1200);' if success else ''
            page = ('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Bord Gais sign-in</title><style>body{font:16px system-ui;background:#151a22;color:#eee;'
                'max-width:460px;margin:12vh auto;padding:24px;line-height:1.6}button{padding:12px 20px;'
                'border:0;border-radius:12px;cursor:pointer}p{color:#bdc5d2}</style></head><body>'
                '<h2>Bord Gais sign-in</h2><p>' + html.escape(message) + '</p>'
                '<p>This tab will close after successful sign-in when the browser permits it. Otherwise, you can close it now.</p>'
                '<button onclick="window.close()">Close tab</button><script>'
                'for(const s of [localStorage,sessionStorage]){for(const k of Object.keys(s))'
                '{if(k.startsWith("bge"))s.removeItem(k);}}' + auto_close + '</script></body></html>')
            response = self.response(page.encode())
            response.del_cookie(COOKIE, secure=True, httponly=True, samesite='Lax')
            return response
        if self.result['state'] in ('verified', 'reauth_successful', 'already_configured', 'wrong_account', 'setup_closed') or not allowed(request.method, path):
            return self.response(b'Endpoint disabled in this login-only test.', 403)
        if request.method == 'POST':
            async with self.lock:
                now = time.monotonic()
                if self.attempts >= 3 or now - self.last_attempt < 30:
                    return self.response(b'{"message":"Login cooldown. Wait 30 seconds; maximum three attempts per test."}',429,'application/json')
                self.attempts += 1
                self.last_attempt = now
                return await self.forward(request)
        return await self.forward(request)

    async def bounded(self, response):
        data = bytearray()
        async for chunk in response.content.iter_chunked(65536):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError('response_limit')
        return bytes(data)

    async def forward(self, request):
        headers = {k: v for k, v in request.headers.items() if k.lower() in (
            'accept', 'accept-language', 'content-type', 'user-agent', 'x-api-key', 'captcha', 'anonymousid')}
        headers.update({'Origin': BASE, 'Referer': BASE + '/sign-in'})
        body = await request.read() if request.method == 'POST' else None
        if body is not None and self.reserve:
            try:
                credentials = json.loads(body)
                username = credentials.get('username')
                if not isinstance(username, str) or not username.strip():
                    raise PortalError('invalid_auth')
                if 'password' in credentials:
                    await self.reserve(username.strip().lower())
            except (ValueError, AttributeError):
                return self.response(b'{"message":"Invalid login request."}', 400, 'application/json')
            except PortalError:
                return self.response(b'{"message":"Login cooldown. Wait before trying again."}', 429, 'application/json')
            finally:
                credentials = None
        try:
            async with self.http.request(request.method, BASE + request.rel_url.path_qs,
                    data=body, headers=headers, allow_redirects=False) as response:
                raw = await self.bounded(response)
                status = response.status
                mime = response.headers.get('Content-Type', 'application/octet-stream').split(';')[0]
                if status in (301, 302, 303, 307, 308):
                    target = urlsplit(response.headers.get('Location', ''))
                    if target.netloc and target.netloc != 'www.bordgaisenergy.ie':
                        return self.response(b'External redirect blocked.', 502)
                    return web.Response(status=status, headers={'Location': target.path or '/sign-in', 'Cache-Control': 'no-store'})
                if request.path == '/api/auth/token':
                    try:
                        data = json.loads(raw)
                    except ValueError:
                        data = {}
                    self.result = {'state': category(status, data), 'http_status': status, 'attempts': self.attempts}
                    _LOGGER.warning('Browser login outcome=%s status=%s', self.result['state'], status)
                    if status == 200 and isinstance(data, dict):
                        if data.get('accessToken') and data.get('refreshToken'):
                            anonymous = request.headers.get('AnonymousId', '')
                            await self.verify({**data, 'anonymousId': anonymous})
                        elif data.get('tempToken'):
                            self.result['state'] = 'otp_requested'
                if mime in ('text/html', 'application/javascript', 'text/javascript', 'application/json', 'text/css'):
                    text = rewrite(raw.decode('utf-8'), self.origin)
                    if mime == 'text/html':
                        bridge = '''<script>(function(){
// Keep supplier session keys in this tab, not persistent browser storage.
for(const method of ['getItem','setItem','removeItem']){const original=Storage.prototype[method];Storage.prototype[method]=function(key,...args){return original.call(this===localStorage&&String(key).startsWith('bge')?sessionStorage:this,key,...args);};}
const tick=setInterval(async()=>{try{const r=await fetch('/trial-result',{cache:'no-store'});const d=await r.json();if(['verified','already_configured','wrong_account','reauth_successful','setup_closed'].includes(d.state)){clearInterval(tick);location.replace('/finished');}}catch(e){}},2000);
})();</script>'''
                        text = text.replace('</head>', bridge + '</head>', 1)
                    raw = text.encode()
                return self.response(raw, status, mime)
        except (aiohttp.ClientError, TimeoutError, ValueError, UnicodeError):
            self.result = {'state': 'upstream_error', 'attempts': self.attempts}
            return self.response(b'Temporary supplier connection error. No automatic login retry.', 502)
        finally:
            body = None

    async def verify(self, data):
        try:
            session = parse_session(data)
            outcome = await self.on_complete(session)
        except PortalError as exc:
            known = {'invalid_session', 'invalid_auth', 'rate_limited', 'cannot_connect'}
            self.result['state'] = str(exc) if str(exc) in known else 'account_verification_failed'
            _LOGGER.warning('Browser login outcome=%s', self.result['state'])
            return
        finally:
            data = None
        self.result = {'state': 'verified', 'account_count': outcome['account_count'], 'attempts': self.attempts}
        _LOGGER.info('Browser login outcome=verified')
