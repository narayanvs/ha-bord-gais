"""Flow orchestration contract tests with small HA API doubles (not runtime HA)."""
import asyncio
import hashlib
import importlib
import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from support import client

class Abort(Exception):pass
class Flow:
 def __init_subclass__(cls, **kwargs):pass
 def __init__(self):self.context={};self.flow_id='synthetic-flow'
 async def async_set_unique_id(self, identity):self.identity=identity
 def _abort_if_unique_id_configured(self):
  if getattr(self,'duplicate',False):raise Abort()
 def async_abort(self,**kw):return {'type':'abort',**kw}
 def async_create_entry(self,**kw):return {'type':'create_entry',**kw}
 def async_show_form(self,**kw):return {'type':'form',**kw}
 def async_show_menu(self,**kw):return {'type':'menu',**kw}
 def async_external_step(self,**kw):return {'type':'external',**kw}
 def async_external_step_done(self,**kw):return {'type':'external_done',**kw}
 def _get_reauth_entry(self):return self.entry
 def async_update_reload_and_abort(self,entry,**kw):
  self.updated=kw;return {'type':'abort','reason':'reauth_successful'}

def module(name,**values):
 m=types.ModuleType(name);m.__dict__.update(values);return m
mods={
 'homeassistant':module('homeassistant'),
 'homeassistant.config_entries':module('config_entries',ConfigFlow=Flow,OptionsFlow=Flow,SOURCE_REAUTH='reauth'),
 'homeassistant.const':module('const',EVENT_HOMEASSISTANT_STOP='stop'),
 'homeassistant.core':module('core',callback=lambda f:f),
 'homeassistant.helpers':module('helpers'),
 'homeassistant.helpers.selector':module('selector'),
 'homeassistant.helpers.network':module('network',get_url=lambda h,**kw:'http://192.168.1.2:8123'),
 'homeassistant.helpers.aiohttp_client':module('aiohttp_client',async_get_clientsession=lambda h:None),
 'homeassistant.helpers.storage':module('storage',Store=object),
 'homeassistant.util':module('util'),
 'homeassistant.util.dt':module('dt',utcnow=lambda:__import__('datetime').datetime.now(__import__('datetime').timezone.utc)),
}
for name, value in mods.items():
 value.__name__=name
 value.__path__=[]
 if '.' in name:
  parent, attr=name.rsplit('.',1)
  if parent in mods:setattr(mods[parent],attr,value)
with patch.dict(sys.modules,mods):
 config=importlib.import_module('bge_test_component.config_flow')
browser=importlib.import_module('bge_test_component.browser_proxy')
SESSION={'accessToken':'synthetic-access','refreshToken':'synthetic-refresh','anonymousId':'synthetic-anonymous'}
ACCOUNTS={'synthetic-hash':{'balance':1.25}}
IDENTITY=hashlib.sha256(json.dumps(sorted(ACCOUNTS)).encode()).hexdigest()

class Tests(unittest.IsolatedAsyncioTestCase):
 def flow(self):
  f=config.BGEConfigFlow();f.hass=types.SimpleNamespace(data={},config_entries=types.SimpleNamespace(flow=None))
  return f
 async def test_wrong_account_reauth_does_not_cache_or_update(self):
  f=self.flow();f.context={'source':'reauth'};f.entry=types.SimpleNamespace(unique_id='different')
  result=await f.finish_auth(SESSION,ACCOUNTS,IDENTITY,'browser')
  self.assertEqual(result['reason'],'wrong_account');self.assertEqual(f.hass.data,{})
  self.assertFalse(hasattr(f,'updated'))
 async def test_correct_reauth_stores_only_session_and_account_keys(self):
  f=self.flow();f.context={'source':'reauth'};f.entry=types.SimpleNamespace(unique_id=IDENTITY)
  result=await f.finish_auth(SESSION,ACCOUNTS,IDENTITY,'browser')
  self.assertEqual(result['reason'],'reauth_successful')
  self.assertEqual(set(f.updated['data_updates']),{'session','account_keys','auth_method'})
 async def test_duplicate_does_not_replace_cache(self):
  f=self.flow();f.duplicate=True;f.hass.data={'keep':'unchanged'}
  with self.assertRaises(Abort):await f.finish_auth(SESSION,ACCOUNTS,IDENTITY,'browser')
  self.assertEqual(f.hass.data,{'keep':'unchanged'})
 async def test_expired_browser_aborts(self):
  self.assertEqual((await self.flow().async_step_browser_wait())['reason'],'browser_expired')
 async def test_browser_finishes_without_frontend_and_clears_capture(self):
  f=self.flow();tasks=[];results=[];step='wait'
  def task(coro):
   t=asyncio.create_task(coro);tasks.append(t);return t
  async def configure(flow_id,data=None):
   nonlocal step
   if step=='wait':
    step='finish';return await f.async_step_browser_wait(data)
   r=await f.async_step_browser_finish(data);results.append(r);return r
  f.hass.async_create_task=task
  f.hass.config_entries.flow=types.SimpleNamespace(async_configure=configure)
  f.hass.bus=types.SimpleNamespace(async_listen_once=lambda *args:None)
  class Browser:
   def __init__(self,host,capture,reserve):self.capture=capture;self.result={};self.runner=object()
   async def start(self):return 'https://192.168.1.2:8743/start/synthetic'
   async def close(self):pass
  class Client:
   def __init__(self,http,session):self.session=dict(session)
   async def fetch(self):return ACCOUNTS
  with patch.object(browser,'BrowserLogin',Browser),patch.object(config,'BGEClient',Client),patch.object(config,'budget',return_value=types.SimpleNamespace(reserve=AsyncMock())):
   result=await f.async_step_browser({'local_host':'192.168.1.2'})
   self.assertEqual(result['type'],'external')
   self.assertEqual(await f._browser.capture(SESSION),{'account_count':1})
   await asyncio.gather(*tasks)
  self.assertEqual(results[0]['type'],'create_entry')
  self.assertEqual(results[0]['data']['session'],SESSION)
  self.assertNotIn('password',results[0]['data'])
  self.assertIsNone(f._browser_auth)
