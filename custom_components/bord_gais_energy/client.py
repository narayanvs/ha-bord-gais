"""Read-only asynchronous client for the observed BGE portal API."""
import asyncio
import base64
import hashlib
import json
import re
import time
import aiohttp
from .account_data import summarize

BASE = 'https://www.bordgaisenergy.ie'
MAX_BYTES = 4 * 1024 * 1024

class PortalError(Exception):
    """Safe error code; never includes URLs, tokens or response bodies."""
class AuthError(PortalError):
    """Browser sign-in required."""


def parse_session(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        access = value.get('accessToken') or value.get('bgeAccessToken')
        refresh = value.get('refreshToken') or value.get('bgeRefreshToken')
        anonymous = value.get('anonymousId') or value.get('bgeSessionUuid')
        if not isinstance(access, str) or not access.strip() or not isinstance(refresh, str) or not refresh.strip():
            raise ValueError
        if not isinstance(anonymous, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', anonymous):
            raise ValueError
        if any(c in access + refresh for c in '\r\n') or len(access + refresh) > 131072:
            raise ValueError
        return {'accessToken': access.strip(), 'refreshToken': refresh.strip(), 'anonymousId': anonymous}
    except (ValueError, TypeError, AttributeError):
        raise PortalError('invalid_session') from None


class BGEClient:
    def __init__(self, http, session, persist=None):
        self.http = http
        self.session = parse_session(session)
        self.persist = persist
        self.lock = asyncio.Lock()
        self.refreshed = False

    async def _request(self, path, payload=None):
        method = 'POST' if payload is not None else 'GET'
        if not ((method == 'POST' and path == '/api/auth/refresh-token') or
                (method == 'GET' and (path == '/api/accounts/' or re.fullmatch(r'/api/accounts/[A-Za-z0-9_-]+(?:/transactions)?', path)))):
            raise PortalError('forbidden_endpoint')
        headers = {'Accept': 'application/json', 'Cache-Control': 'no-cache',
                   'Origin': BASE, 'Referer': BASE + '/sign-in',
                   'AnonymousId': self.session['anonymousId']}
        if method == 'GET':
            headers['Authorization'] = 'Bearer ' + self.session['accessToken']
        try:
            async with self.http.request(method, BASE + path, headers=headers,
                    params={'cache': str(time.time_ns() // 1000000)} if method == 'GET' else None,
                    json=payload, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=30)) as response:
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise PortalError('response_too_large')
                if response.status in (401, 403):
                    raise AuthError('invalid_auth')
                if response.status == 400:
                    try:
                        error = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        error = {}
                    if isinstance(error, dict) and error.get('message') == 'The request identifier is invalid or not provided.':
                        raise AuthError('invalid_auth')
                if response.status == 429:
                    raise PortalError('rate_limited')
                if response.status != 200:
                    raise PortalError('portal_http_error')
                if 'json' not in response.headers.get('Content-Type', '').lower():
                    raise PortalError('invalid_response')
                try:
                    return json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise PortalError('invalid_response') from None
        except (aiohttp.ClientError, TimeoutError):
            raise PortalError('cannot_connect') from None

    def _expires_soon(self):
        # Unverified JWT expiry is only a refresh hint, never authentication proof.
        try:
            part = self.session['accessToken'].split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
            expiry = claims.get('exp')
            return isinstance(expiry, (int, float)) and expiry <= time.time() + 60
        except (ValueError, IndexError, TypeError, AttributeError, UnicodeDecodeError):
            return False

    async def _refresh(self):
        if self.refreshed:
            raise AuthError('invalid_auth')
        self.refreshed = True
        response = await self._request('/api/auth/refresh-token', {'refreshToken': self.session['refreshToken']})
        try:
            response = {**response, 'anonymousId': self.session['anonymousId']}
            self.session = parse_session(response)
        except (PortalError, TypeError):
            raise PortalError('invalid_response') from None
        if self.persist:
            await self.persist(dict(self.session))

    async def renew_session(self):
        """Rotate tokens without downloading account data; share the fetch lock."""
        async with self.lock:
            self.refreshed = False
            await self._refresh()

    async def _read(self, path):
        if not self.refreshed and self._expires_soon():
            await self._refresh()
        try:
            return await self._request(path)
        except AuthError:
            await self._refresh()
            return await self._request(path)

    async def fetch(self):
        async with self.lock:
            self.refreshed = False
            async with asyncio.timeout(90):
                listing = await self._read('/api/accounts/')
                content = listing.get('content') if isinstance(listing, dict) else None
                if not isinstance(content, list) or not 1 <= len(content) <= 10:
                    raise PortalError('invalid_response')
                # Refuse a partial account list instead of silently dropping devices.
                total = listing.get('totalElements', len(content))
                if not isinstance(total, int) or isinstance(total, bool):
                    raise PortalError('invalid_response')
                if total > len(content):
                    raise PortalError('pagination_required')
                result = {}
                for account in content:
                    ident = account.get('accountId') if isinstance(account, dict) else None
                    if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', ident):
                        raise PortalError('invalid_response')
                    details = await self._read('/api/accounts/' + ident)
                    if not isinstance(details, dict) or not isinstance(details.get('account'), dict):
                        raise PortalError('invalid_response')
                    if details['account'].get('accountId') != ident:
                        raise PortalError('account_mismatch')
                    available = True
                    try:
                        transactions = await self._read('/api/accounts/' + ident + '/transactions')
                        if not isinstance(transactions, list):
                            raise PortalError('invalid_response')
                    except AuthError:
                        raise
                    except PortalError as exc:
                        if str(exc) == 'rate_limited':
                            raise
                        transactions = []
                        available = False
                    key = hashlib.sha256(ident.encode()).hexdigest()
                    if key in result:
                        raise PortalError('invalid_response')
                    result[key] = {**summarize(details, transactions), 'transactions_available': available}
                return result
