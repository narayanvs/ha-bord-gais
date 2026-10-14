"""Cached account polling and immediate refresh-token persistence."""
from datetime import timedelta
import logging
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from .client import AuthError, BGEClient, PortalError
from .const import DOMAIN, DEFAULT_POLL_HOURS
_LOGGER = logging.getLogger(__name__)

class BGECoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.poll_hours = entry.options.get('poll_hours', DEFAULT_POLL_HOURS)
        self.last_success = None
        self.last_attempt = None
        self.store = Store(hass, 1, DOMAIN + '.' + entry.entry_id)
        self.client = BGEClient(async_get_clientsession(hass), entry.data['session'], self.persist_session)
        super().__init__(hass, _LOGGER, name='Bord Gáis Energy Account', config_entry=entry,
                         update_interval=timedelta(hours=self.poll_hours), always_update=False)

    async def persist_session(self, session):
        self.hass.config_entries.async_update_entry(self.entry, data={**self.entry.data, 'session': session})

    async def async_initialize(self):
        cached = self.hass.data.get(DOMAIN, {}).pop(self.entry.unique_id, None)
        if cached:
            await self.store.async_save(cached)
        else:
            cached = await self.store.async_load()
        if cached and isinstance(cached.get('accounts'), dict):
            stamp = dt_util.parse_datetime(cached.get('retrieved_at', ''))
            if stamp and stamp.tzinfo:
                self.last_success = stamp
                age = dt_util.utcnow() - stamp
                if timedelta(0) <= age < timedelta(hours=self.poll_hours):
                    self.update_interval = timedelta(hours=self.poll_hours) - age
                    self.async_set_updated_data(cached['accounts'])
                    return
        await self.async_config_entry_first_refresh()

    async def _async_update_data(self):
        now = dt_util.utcnow()
        if self.last_attempt and now - self.last_attempt < timedelta(minutes=5):
            if self.data is not None and self.last_update_success:
                return self.data
            raise UpdateFailed('Recent request failed; wait five minutes before retrying', retry_after=300)
        self.last_attempt = now
        try:
            result = await self.client.fetch()
        except AuthError:
            raise ConfigEntryAuthFailed('Sign in again and supply a fresh browser session') from None
        except PortalError as exc:
            if str(exc) == 'rate_limited':
                raise UpdateFailed('Supplier rate limit; waiting six hours', retry_after=21600) from None
            raise UpdateFailed(str(exc)) from None
        self.update_interval = timedelta(hours=self.poll_hours)
        self.last_success = now
        await self.store.async_save({'retrieved_at': now.isoformat(), 'accounts': result})
        return result
