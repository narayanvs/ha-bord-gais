"""Unverified JWT times are scheduling hints, never authentication proof."""
import base64
import json
import math
import time


def token_expiry(token):
    try:
        part = token.split('.')[1]
        if len(part) > 131072:
            return None
        claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        value = claims.get('exp')
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            return None
        return value
    except (ValueError, TypeError, AttributeError, IndexError):
        return None


def renewal_delay(session, now=None):
    """Renew before either token expires; only refresh expiry requires reauth."""
    now = time.time() if now is None else now
    refresh_expiry = token_expiry(session.get('refreshToken', ''))
    access_expiry = token_expiry(session.get('accessToken', ''))
    if refresh_expiry is not None and refresh_expiry <= now:
        return 0.0
    delay = 600.0
    for expiry in (refresh_expiry, access_expiry):
        if expiry is None:
            continue
        remaining = expiry - now
        # An expired access token can still be renewed with a valid refresh token.
        delay = min(delay, max(1.0, remaining - min(60.0, max(0.0, remaining / 2))))
    return delay
