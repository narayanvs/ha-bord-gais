"""Browser-session setup and reauthentication without logging credentials."""
import hashlib
import json
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from .client import AuthError, BGEClient, PortalError, parse_session
from .const import DOMAIN, NAME, DEFAULT_POLL_HOURS


def session_schema():
    return vol.Schema({vol.Required('session_json'): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})


class BGEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def validate(self, data):
        client = BGEClient(async_get_clientsession(self.hass), parse_session(data['session_json']))
        accounts = await client.fetch()
        identity = hashlib.sha256(json.dumps(sorted(accounts)).encode()).hexdigest()
        return client.session, accounts, identity

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                session, accounts, identity = await self.validate(user_input)
            except AuthError:
                errors['base'] = 'invalid_auth'
            except PortalError as exc:
                errors['base'] = str(exc) if str(exc) in ('invalid_session', 'rate_limited') else 'cannot_connect'
            except TimeoutError:
                errors['base'] = 'cannot_connect'
            else:
                await self.async_set_unique_id(identity)
                self._abort_if_unique_id_configured()
                self.hass.data.setdefault(DOMAIN, {})[identity] = {'retrieved_at': dt_util.utcnow().isoformat(), 'accounts': accounts}
                return self.async_create_entry(title=NAME, data={'session': session, 'account_keys': sorted(accounts)})
        return self.async_show_form(step_id='user', data_schema=session_schema(), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            try:
                session, accounts, identity = await self.validate(user_input)
                if identity != entry.unique_id:
                    return self.async_abort(reason='wrong_account')
            except AuthError:
                errors['base'] = 'invalid_auth'
            except PortalError as exc:
                errors['base'] = str(exc) if str(exc) in ('invalid_session', 'rate_limited') else 'cannot_connect'
            except TimeoutError:
                errors['base'] = 'cannot_connect'
            else:
                self.hass.data.setdefault(DOMAIN, {})[identity] = {'retrieved_at': dt_util.utcnow().isoformat(), 'accounts': accounts}
                return self.async_update_reload_and_abort(entry, data_updates={'session': session, 'account_keys': sorted(accounts)})
        return self.async_show_form(step_id='reauth_confirm', data_schema=session_schema(), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BGEOptionsFlow()


class BGEOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title='', data=user_input)
        return self.async_show_form(step_id='init', data_schema=vol.Schema({
            vol.Required('poll_hours', default=self.config_entry.options.get('poll_hours', DEFAULT_POLL_HOURS)):
                vol.All(vol.Coerce(int), vol.Range(min=24, max=720)),
        }))
