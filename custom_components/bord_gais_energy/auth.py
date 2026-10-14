"""Experimental password login: one request, no CAPTCHA bypass or secret logs."""
import asyncio
from html import unescape
import json
import logging
import re
import uuid
import aiohttp
from .client import BASE, MAX_BYTES, PortalError, parse_session
_LOGGER = logging.getLogger(__name__)


async def read_body(response):
    raw = bytearray()
    async for chunk in response.content.iter_chunked(65536):
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise PortalError('response_too_large')
    return raw


def public_client_key(html):
    match = re.search(r'<script\b(?=[^>]*\bid=["\']__NEXT_DATA__["\'])[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise PortalError('login_page_changed')
    try:
        data = json.loads(unescape(match.group(1)))
        key = data['props']['initialReduxState']['envVars'].get('digitalApiKey')
    except (ValueError, KeyError, TypeError, AttributeError):
        raise PortalError('login_page_changed') from None
    if not isinstance(key, str) or not key or '\n' in key or '\r' in key:
        raise PortalError('login_page_changed')
    return key


def failure_category(status, data):
    """Inspect private text in memory; emit only a fixed error category."""
    text = ' '.join(str(data.get(k, '')) for k in ('code', 'errorCode', 'errorMessage', 'message', 'error')).lower() if isinstance(data, dict) else ''
    if status == 429:
        return 'rate_limited'
    if 'captcha' in text or 'browser verification' in text:
        return 'browser_verification_required'
    if 'password_change_required' in text or 'password change' in text:
        return 'password_change_required'
    if 'otp' in text or 'one time' in text:
        return 'otp_required'
    if status in (400, 401, 403):
        return 'login_rejected'
    return 'portal_http_error'


async def password_login(http, username, password, reserve):
    username = username.strip().lower()
    if not username or not password or len(username) > 320 or len(password) > 4096:
        raise PortalError('invalid_auth')
    await reserve(username)
    anonymous = uuid.uuid4().hex
    headers = {'Accept': 'application/json', 'Origin': BASE,
               'Referer': BASE + '/sign-in', 'AnonymousId': anonymous}
    try:
        async with asyncio.timeout(65):
            async with http.get(BASE + '/sign-in', allow_redirects=False,
                                timeout=aiohttp.ClientTimeout(total=30)) as response:
                _LOGGER.debug('Password auth stage=bootstrap status=%s', response.status)
                if response.status != 200:
                    raise PortalError('login_page_changed')
                key = public_client_key((await read_body(response)).decode('utf-8'))
            headers['X-API-Key'] = key
            # Deliberately omit captcha. A rejection is reported, never bypassed.
            _LOGGER.debug('Password auth stage=submit captcha_present=false client_key_present=true')
            async with http.post(BASE + '/api/auth/token',
                    json={'username': username, 'password': password}, headers=headers,
                    allow_redirects=False, timeout=aiohttp.ClientTimeout(total=30)) as response:
                raw = await read_body(response)
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    data = None
                if response.status != 200:
                    code = failure_category(response.status, data)
                    _LOGGER.warning('Password auth stage=submit status=%s category=%s', response.status, code)
                    raise PortalError(code)
                if isinstance(data, dict) and ('state' in data or 'tempToken' in data):
                    _LOGGER.warning('Password auth stage=submit status=200 category=otp_required')
                    raise PortalError('otp_required')
                try:
                    result = parse_session({**data, 'anonymousId': anonymous})
                except (PortalError, TypeError):
                    _LOGGER.warning('Password auth stage=submit status=200 category=invalid_response')
                    raise PortalError('invalid_response') from None
                _LOGGER.info('Password auth stage=submit status=200 category=success')
                return result
    except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError):
        _LOGGER.warning('Password auth category=cannot_connect')
        raise PortalError('cannot_connect') from None
