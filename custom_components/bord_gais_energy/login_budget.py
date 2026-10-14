"""Persistent short login limit shared by config flows; never store usernames."""
import asyncio
import hashlib
import time
from homeassistant.helpers.storage import Store
from .client import PortalError
from .const import DOMAIN

class LoginBudget:
    def __init__(self, hass):
        self.store = Store(hass, 1, DOMAIN + '.login_budget')
        self.lock = asyncio.Lock()
        self.records = None

    async def reserve(self, username):
        key = hashlib.sha256(username.strip().lower().encode()).hexdigest()
        async with self.lock:
            if self.records is None:
                self.records = await self.store.async_load() or {}
            now = time.time()
            self.records = {k: [t for t in times if isinstance(t,(int,float)) and now-900 < t <= now]
                            for k,times in self.records.items() if isinstance(times,list)}
            self.records = {k:v for k,v in self.records.items() if v}
            recent = self.records.get(key, [])
            if len(recent) >= 3 or recent and now - max(recent) < 60:
                raise PortalError('login_cooldown')
            if key not in self.records and len(self.records) >= 64:
                raise PortalError('login_cooldown')
            self.records[key] = recent + [now]
            await self.store.async_save(self.records)


def budget(hass):
    data = hass.data.setdefault(DOMAIN, {})
    if 'login_budget' not in data:
        data['login_budget'] = LoginBudget(hass)
    return data['login_budget']
