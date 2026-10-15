"""Renewal lifecycle contract; no authenticated requests or full HA runtime."""
import importlib,types,unittest,sys
from unittest.mock import AsyncMock,Mock,patch
from support import client
from test_config_flow import mods,module
mods={**mods,
 'homeassistant.exceptions':module('exceptions',ConfigEntryAuthFailed=type('AuthFailed',(Exception,),{})),
 'homeassistant.helpers.event':module('event',async_call_later=Mock()),
 'homeassistant.helpers.update_coordinator':module('update_coordinator',DataUpdateCoordinator=object,UpdateFailed=Exception),
}
with patch.dict(sys.modules,mods):
 m=importlib.import_module('bge_test_component.coordinator')
class Tests(unittest.IsolatedAsyncioTestCase):
 def coordinator(self):
  c=m.BGECoordinator.__new__(m.BGECoordinator)
  c.async_set_update_error=Mock();c.last_renewal_success=None;c.last_renewal_error=None;c.renewal_count=0
  c.hass=object();c.entry=types.SimpleNamespace(async_start_reauth=Mock())
  c.client=types.SimpleNamespace(session={'refreshToken':'synthetic-opaque'},renew_session=AsyncMock())
  c._cancel_renewal=None;c._renewal_failures=0;c._session_auth_failed=False;c._session_closed=False
  return c
 async def test_renewal_does_not_poll_accounts(self):
  c=self.coordinator()
  with patch.object(m,'async_call_later',return_value=Mock()) as timer:
   await c._renew_session(None)
  c.client.renew_session.assert_awaited_once()
  self.assertEqual(timer.call_args.args[1],600)
  c.entry.async_start_reauth.assert_not_called()
 async def test_auth_failure_stops_and_requests_reauth_once(self):
  c=self.coordinator();c.client.renew_session.side_effect=client.AuthError('invalid_auth')
  with self.assertLogs(m._LOGGER,level='WARNING'):
   await c._renew_session(None);c.request_reauth()
  c.entry.async_start_reauth.assert_called_once()
  c.async_set_update_error.assert_called_once()
  self.assertEqual(c.last_renewal_error,'supplier_rejected_session')
  self.assertIsNone(c._cancel_renewal)
 async def test_network_retries_are_bounded(self):
  c=self.coordinator();c.client.renew_session.side_effect=client.PortalError('cannot_connect')
  with patch.object(m,'async_call_later',return_value=Mock()) as timer,self.assertLogs(m._LOGGER,level='WARNING'):
   for _ in range(3):await c._renew_session(None)
  self.assertEqual([call.args[1] for call in timer.call_args_list],[30,60])
  c.entry.async_start_reauth.assert_called_once()
 async def test_rate_limit_never_hammers_refresh(self):
  c=self.coordinator();c.client.renew_session.side_effect=client.PortalError('rate_limited')
  with patch.object(m,'async_call_later') as timer,self.assertLogs(m._LOGGER,level='WARNING'):
   await c._renew_session(None)
  timer.assert_not_called();c.entry.async_start_reauth.assert_called_once()
 async def test_unload_prevents_rescheduling_inflight_request(self):
  c=self.coordinator()
  async def finish():c.shutdown_session()
  c.client.renew_session.side_effect=finish
  with patch.object(m,'async_call_later') as timer:
   await c._renew_session(None)
  timer.assert_not_called()
