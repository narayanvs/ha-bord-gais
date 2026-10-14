"""HA service wiring with minimal API doubles; never sends a real reading."""
import importlib,sys,types,unittest
from unittest.mock import Mock,patch
import voluptuous as vol
from test_config_flow import mods,module
from test_gas_submission import MemoryStore,preflight,KEY
from test_client import HTTP,SESSION
from support import client
mods={**mods,
 'homeassistant.helpers.entity_registry':module('entity_registry',async_get=lambda hass:hass.registry),
 'homeassistant.helpers.service':module('service',async_register_admin_service=Mock()),
 'homeassistant.exceptions':module('exceptions',HomeAssistantError=type('HAError',(Exception,),{})),
}
mods['homeassistant.core'].SupportsResponse=types.SimpleNamespace(OPTIONAL='optional')
for name,value in mods.items():
 if '.' in name:
  parent,attr=name.rsplit('.',1)
  if parent in mods:setattr(mods[parent],attr,value)
with patch.dict(sys.modules,mods):m=importlib.import_module('bge_test_component.services')
class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_admin_registration_and_default_preview(self):
  http=HTTP(preflight());c=client.BGEClient(http,SESSION)
  entity=types.SimpleNamespace(platform='bord_gais_energy',unique_id=KEY+'_gas_last_actual_reading',config_entry_id='synthetic-entry')
  entry=types.SimpleNamespace(entry_id='synthetic-entry',runtime_data=types.SimpleNamespace(client=c,data={KEY:{'service':'gas'}}))
  hass=types.SimpleNamespace(services=types.SimpleNamespace(has_service=lambda *args:False),
   config_entries=types.SimpleNamespace(async_get_entry=lambda key:entry),registry=types.SimpleNamespace(async_get=lambda key:entity))
  with patch.object(m,'async_register_admin_service') as register,patch.object(m,'Store',return_value=MemoryStore()):
   m.register_services(hass)
   args=register.call_args
   self.assertEqual(args.args[1:3],('bord_gais_energy','submit_gas_meter_reading'))
   self.assertEqual(args.kwargs['supports_response'],'optional')
   schema=args.kwargs['schema'];handler=args.args[3]
   data=schema({'entity_id':'sensor.synthetic_gas_reading','reading':'00123'})
   self.assertTrue(data['dry_run']);self.assertFalse(data['confirm'])
   result=await handler(types.SimpleNamespace(data=data))
   self.assertEqual(result['status'],'preview_only')
   self.assertTrue(all(method=='GET' for method,url,kw in http.calls))
 async def test_wrong_entity_rejected_before_requests(self):
  entity=types.SimpleNamespace(platform='bord_gais_energy',unique_id=KEY+'_supplier_balance')
  hass=types.SimpleNamespace(services=types.SimpleNamespace(has_service=lambda *args:False),registry=types.SimpleNamespace(async_get=lambda key:entity))
  with patch.object(m,'async_register_admin_service') as register:
   m.register_services(hass)
   handler=register.call_args.args[3]
   with self.assertRaises(m.HomeAssistantError):await handler(types.SimpleNamespace(data={'entity_id':'sensor.synthetic'}))
 def test_invalid_input_is_schema_error(self):
  with self.assertRaises(vol.Invalid):m.validate_reading('12.3')
