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
    """Refresh before its own expiry; independent of full account polling."""
    now = time.time() if now is None else now
    expiry = token_expiry(session.get('refreshToken', ''))
    if expiry is None:
        return 600.0
    remaining = expiry - now
    if remaining <= 0:
        return 0.0
    return max(1.0, min(600.0, remaining - min(120.0, remaining / 2)))
