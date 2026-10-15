"""Cached account polling and immediate refresh-token persistence."""
from datetime import timedelta
import logging
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from .client import AuthError, BGEClient, PortalError
from .const import DOMAIN, DEFAULT_POLL_HOURS
from .session_timing import renewal_delay
_LOGGER = logging.getLogger(__name__)

class BGECoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.poll_hours = entry.options.get('poll_hours', DEFAULT_POLL_HOURS)
        self.last_success = None
        self.last_attempt = None
        self._cancel_renewal = None
        self._renewal_failures = 0
        self.last_renewal_success = None
        self.last_renewal_error = None
        self.renewal_count = 0
        self._session_auth_failed = False
        self._session_closed = False
        self.store = Store(hass, 1, DOMAIN + '.' + entry.entry_id)
        self.client = BGEClient(async_get_clientsession(hass), entry.data['session'], self.persist_session)
        super().__init__(hass, _LOGGER, name='Bord Gáis Energy Account', config_entry=entry,
                         update_interval=timedelta(hours=self.poll_hours), always_update=False)
        entry.async_on_unload(self.shutdown_session)

    async def persist_session(self, session):
        self.hass.config_entries.async_update_entry(self.entry, data={**self.entry.data, 'session': session})
        self._renewal_failures = 0
        self.schedule_renewal()

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
                usage_supported = all(v.get('service') not in ('gas', 'electricity') or f"{v['service']}_usage_available" in v for v in cached['accounts'].values() if isinstance(v, dict))
                if usage_supported and timedelta(0) <= age < timedelta(hours=self.poll_hours):
                    self.update_interval = timedelta(hours=self.poll_hours) - age
                    self.async_set_updated_data(cached['accounts'])
                    self.schedule_renewal()
                    return
        await self.async_config_entry_first_refresh()
        self.schedule_renewal()

    def cancel_renewal(self):
        if self._cancel_renewal:
            self._cancel_renewal()
            self._cancel_renewal = None

    def shutdown_session(self):
        self._session_closed = True
        self.cancel_renewal()

    def request_reauth(self, reason='session_expired_or_revoked'):
        if self._session_closed:
            return
        self.cancel_renewal()
        if not self._session_auth_failed:
            self._session_auth_failed = True
            self.last_renewal_error = reason
            self.async_set_update_error(ConfigEntryAuthFailed(
                'Supplier session expired or was revoked; browser sign-in is required'))
            _LOGGER.warning('Supplier session requires browser reauthentication (%s)', reason)
            self.entry.async_start_reauth(self.hass)

    def schedule_renewal(self, retry_delay=None):
        self.cancel_renewal()
        if self._session_auth_failed or self._session_closed:
            return
        delay = renewal_delay(self.client.session)
        if delay <= 0:
            self.request_reauth()
            return
        if retry_delay is not None:
            delay = min(delay, retry_delay)
        self._cancel_renewal = async_call_later(self.hass, delay, self._renew_session)

    async def _renew_session(self, _now):
        self._cancel_renewal = None
        if self._session_closed:
            return
        try:
            await self.client.renew_session()
        except AuthError:
            self.request_reauth('supplier_rejected_session')
        except PortalError as exc:
            self.last_renewal_error = str(exc)
            self._renewal_failures += 1
            if str(exc) == 'rate_limited' or self._renewal_failures >= 3:
                # A long cooldown outlives the short refresh token. Stop; never hammer login.
                self.request_reauth('rate_limited' if str(exc) == 'rate_limited' else 'renewal_unreachable')
            else:
                self.schedule_renewal(retry_delay=30 * 2 ** (self._renewal_failures - 1))
        else:
            self._renewal_failures = 0
            self.last_renewal_success = dt_util.utcnow()
            self.last_renewal_error = None
            self.renewal_count += 1
            self.schedule_renewal()

    async def _async_update_data(self):
        if self._session_auth_failed:
            raise ConfigEntryAuthFailed('Supplier session requires browser reauthentication')
        now = dt_util.utcnow()
        if self.last_attempt and now - self.last_attempt < timedelta(minutes=5):
            if self.data is not None and self.last_update_success:
                return self.data
            raise UpdateFailed('Recent request failed; wait five minutes before retrying', retry_after=300)
        self.last_attempt = now
        try:
            result = await self.client.fetch()
        except AuthError:
            self.cancel_renewal()
            self._session_auth_failed = True
            raise ConfigEntryAuthFailed('Sign in again and supply a fresh browser session') from None
        except PortalError as exc:
            if str(exc) == 'rate_limited':
                raise UpdateFailed('Supplier rate limit; waiting six hours', retry_after=21600) from None
            raise UpdateFailed(str(exc)) from None
        self.update_interval = timedelta(hours=self.poll_hours)
        self.last_success = now
        await self.store.async_save({'retrieved_at': now.isoformat(), 'accounts': result})
        return result
