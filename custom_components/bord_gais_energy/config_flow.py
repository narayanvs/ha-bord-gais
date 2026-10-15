"""Browser-session setup and reauthentication without logging credentials."""
import asyncio
import hashlib
import ipaddress
import json
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.network import get_url
from urllib.parse import urlsplit
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from .client import AuthError, BGEClient, PortalError, parse_session
from .login_budget import budget
from .const import DOMAIN, NAME, DEFAULT_POLL_HOURS


def session_schema():
    return vol.Schema({vol.Required('session_json'): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})


class BGEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def validate(self, data):
        http = async_get_clientsession(self.hass)
        session = parse_session(data['session_json'])
        client = BGEClient(http, session)
        accounts = await client.fetch()
        identity = hashlib.sha256(json.dumps(sorted(accounts)).encode()).hexdigest()
        return client.session, accounts, identity

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id='user', menu_options=['browser', 'session'])

    async def async_step_session(self, user_input=None):
        return await self._authenticate('session', session_schema(), user_input)

    async def _authenticate(self, method, schema, user_input):
        errors = {}
        if user_input is not None:
            try:
                session, accounts, identity = await self.validate(user_input)
            except AuthError:
                errors['base'] = 'invalid_auth'
            except PortalError as exc:
                allowed = {'invalid_session', 'rate_limited', 'login_cooldown', 'browser_verification_required',
                           'otp_required', 'password_change_required', 'login_rejected', 'login_page_changed'}
                errors['base'] = str(exc) if str(exc) in allowed else 'cannot_connect'
            except TimeoutError:
                errors['base'] = 'cannot_connect'
            else:
                return await self.finish_auth(session, accounts, identity, method)
        return self.async_show_form(step_id=method, data_schema=schema, errors=errors)

    async def finish_auth(self, session, accounts, identity, method):
        data = {'session': session, 'account_keys': sorted(accounts), 'auth_method': method}
        if self.context.get('source') == config_entries.SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if identity != entry.unique_id:
                return self.async_abort(reason='wrong_account')
            self.hass.data.setdefault(DOMAIN, {})[identity] = {
                'retrieved_at': dt_util.utcnow().isoformat(), 'accounts': accounts}
            return self.async_update_and_abort(entry, data_updates=data)
        await self.async_set_unique_id(identity)
        self._abort_if_unique_id_configured()
        self.hass.data.setdefault(DOMAIN, {})[identity] = {
            'retrieved_at': dt_util.utcnow().isoformat(), 'accounts': accounts}
        return self.async_create_entry(title=NAME, data=data)

    async def async_step_browser(self, user_input=None):
        from .browser_proxy import BrowserLogin
        errors = {}
        detected_host = ''
        if user_input is None:
            try:
                candidate = await network.async_get_source_ip(self.hass)
                address = ipaddress.ip_address(candidate)
                if address.version == 4 and address.is_private and not (
                        address.is_loopback or address.is_unspecified or address.is_multicast):
                    detected_host = str(address)
            except Exception:
                pass
            if detected_host and not self.context.get('show_advanced_options'):
                user_input = {'local_host': detected_host}
        if user_input is not None:
            previous = self.hass.data.get(DOMAIN + '_browser')
            if previous and previous.runner:
                errors['base'] = 'browser_running'
            else:
                async def capture(session):
                    client = BGEClient(async_get_clientsession(self.hass), session)
                    accounts = await client.fetch()
                    identity = hashlib.sha256(json.dumps(sorted(accounts)).encode()).hexdigest()
                    self._browser_auth = (client.session, accounts, identity)
                    self._browser_finish_result = None
                    async def advance():
                        await asyncio.sleep(0)
                        try:
                            # Notify HA's external-step UI; it owns the subsequent finish request.
                            # Removing this flow here races the frontend and causes UnknownFlow.
                            await self.hass.config_entries.flow.async_configure(self.flow_id, {'complete': True})
                        except Exception:
                            self._browser.result['state'] = 'setup_closed'
                            self._browser_auth = None
                            asyncio.get_running_loop().call_later(30, lambda: self.hass.async_create_task(self._browser.close()))
                    self.hass.async_create_task(advance())
                    return {'account_count': len(accounts)}
                try:
                    self._browser = BrowserLogin(user_input['local_host'], capture, budget(self.hass).reserve)
                    self._browser.on_close = lambda: setattr(self, '_browser_auth', None)
                    link = await self._browser.start()
                except (OSError, ValueError):
                    errors['base'] = 'browser_cannot_start'
                else:
                    self.hass.data[DOMAIN + '_browser'] = self._browser
                    self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda event: self.hass.async_create_task(self._browser.close()))
                    return self.async_external_step(step_id='browser_wait', url=link)
        try:
            default = detected_host or urlsplit(get_url(self.hass, prefer_external=False)).hostname or ''
        except Exception:
            default = ''
        return self.async_show_form(step_id='browser', data_schema=vol.Schema({
            vol.Required('local_host', default=default): str,
        }), errors=errors)

    async def async_step_browser_wait(self, user_input=None):
        if getattr(self, '_browser_auth', None):
            return self.async_external_step_done(next_step_id='browser_finish')
        return self.async_abort(reason='browser_expired')

    async def async_step_browser_finish(self, user_input=None):
        captured = getattr(self, '_browser_auth', None)
        if not captured:
            return self.async_abort(reason='browser_expired')
        try:
            result = await self.finish_auth(*captured, 'browser')
            self._browser_finish_result = result
            if result.get('type') == 'abort':
                reason = result.get('reason')
                self._browser.result['state'] = reason if reason in ('wrong_account', 'already_configured', 'reauth_successful') else 'setup_closed'
            return result
        finally:
            self._browser_auth = None
            asyncio.get_running_loop().call_later(30, lambda: self.hass.async_create_task(self._browser.close()))

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return self.async_show_menu(step_id='reauth_confirm', menu_options=['browser', 'session'])

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
