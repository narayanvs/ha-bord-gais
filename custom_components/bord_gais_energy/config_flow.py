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
from .auth import password_login
from .login_budget import budget
from .const import DOMAIN, NAME, DEFAULT_POLL_HOURS


def session_schema():
    return vol.Schema({vol.Required('session_json'): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})


class BGEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def validate(self, data, method):
        http = async_get_clientsession(self.hass)
        if method == 'password':
            session = await password_login(http, data['username'], data['password'], budget(self.hass).reserve)
        else:
            session = parse_session(data['session_json'])
        client = BGEClient(http, session)
        accounts = await client.fetch()
        identity = hashlib.sha256(json.dumps(sorted(accounts)).encode()).hexdigest()
        return client.session, accounts, identity

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id='user', menu_options=['password', 'session'])

    async def async_step_password(self, user_input=None):
        schema = vol.Schema({
            vol.Required('username'): str,
            vol.Required('password'): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        })
        return await self._authenticate('password', schema, user_input)

    async def async_step_session(self, user_input=None):
        return await self._authenticate('session', session_schema(), user_input)

    async def _authenticate(self, method, schema, user_input):
        errors = {}
        if user_input is not None:
            try:
                session, accounts, identity = await self.validate(user_input, method)
            except AuthError:
                errors['base'] = 'invalid_auth'
            except PortalError as exc:
                allowed = {'invalid_session', 'rate_limited', 'login_cooldown', 'browser_verification_required',
                           'otp_required', 'password_change_required', 'login_rejected', 'login_page_changed'}
                errors['base'] = str(exc) if str(exc) in allowed else 'cannot_connect'
            except TimeoutError:
                errors['base'] = 'cannot_connect'
            else:
                self.hass.data.setdefault(DOMAIN, {})[identity] = {'retrieved_at': dt_util.utcnow().isoformat(), 'accounts': accounts}
                data = {'session': session, 'account_keys': sorted(accounts), 'auth_method': method}
                # Username/password are discarded after login; only renewable session tokens persist.
                if self.context.get('source') == config_entries.SOURCE_REAUTH:
                    entry = self._get_reauth_entry()
                    if identity != entry.unique_id:
                        self.hass.data[DOMAIN].pop(identity, None)
                        return self.async_abort(reason='wrong_account')
                    return self.async_update_reload_and_abort(entry, data_updates=data)
                await self.async_set_unique_id(identity)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=NAME, data=data)
        return self.async_show_form(step_id=method, data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return self.async_show_menu(step_id='reauth_confirm', menu_options=['password', 'session'])

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
