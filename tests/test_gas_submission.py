import asyncio,copy,hashlib,importlib,unittest
from unittest.mock import AsyncMock
from support import client
from test_client import HTTP,Response,SESSION
m=importlib.import_module('bge_test_component.gas_submission')
KEY=hashlib.sha256(b'synthetic-account').hexdigest()
def preflight(service='GS',eligible=True):
 return [Response(data={'content':[{'accountId':'synthetic-account'}]}),
  Response(data={'account':{'accountId':'synthetic-account','serviceType':service}}),
  Response(data={'serviceType':'GS','eligible':eligible,'goodTime':False,'preDecimalDigits':'5',
   'lastActualReadDate':'2024-01-01','lastActualReads':[{'registerType':'Gas Meter','readValue':100}]})]
class Submit(unittest.IsolatedAsyncioTestCase):
 async def test_preview_never_posts_and_shows_nonpreferred_time(self):
  http=HTTP(preflight());result=await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,'00123')
  self.assertEqual(result['reading'],123);self.assertEqual(result['status'],'preview_only')
  self.assertFalse(result['preferred_reading_time']);self.assertFalse(result['submitted'])
  self.assertTrue(all(method=='GET' for method,url,kw in http.calls))
 async def test_actual_requires_explicit_confirmation_before_network(self):
  http=HTTP([])
  with self.assertRaisesRegex(client.PortalError,'confirmation_required'):
   await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,123,dry_run=False)
  self.assertEqual(http.calls,[])
 async def test_one_write_exact_gas_payload_and_guard_before_send(self):
  for status in [200,201]:
   http=HTTP(preflight()+[Response(status)])
   async def reserve(reading):
    self.assertEqual(len(http.calls),3);self.assertEqual(reading,123)
   record=AsyncMock()
   result=await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,123,dry_run=False,confirm=True,reserve=reserve,record=record)
   self.assertTrue(result['submitted']);self.assertEqual(len(http.calls),4)
   method,url,kwargs=http.calls[-1]
   self.assertEqual(method,'POST');self.assertTrue(url.endswith('/api/meters/v1/read'))
   self.assertEqual(kwargs['json'],{'accountId':'synthetic-account','registers':[{'registerType':'Gas Meter','readValue':123}]})
   self.assertEqual(kwargs['headers']['Authorization'],'Bearer synthetic-access')
   self.assertFalse(kwargs['allow_redirects']);record.assert_awaited_once_with(123,'accepted')
 async def test_rejection_or_unknown_never_replays_write(self):
  for status in [400,401,403,422,429,302,500]:
   http=HTTP(preflight()+[Response(status)]);record=AsyncMock()
   with self.assertRaises(client.PortalError):
    await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,123,dry_run=False,confirm=True,record=record)
   self.assertEqual(sum(method=='POST' for method,url,kw in http.calls),1)
   if status in (400,401,403,422,429):record.assert_awaited_once_with(123,'rejected')
   else:record.assert_not_awaited()
 async def test_timeout_is_unknown_and_does_not_repeat(self):
  class TimeoutHTTP(HTTP):
   def request(self,method,url,**kw):
    if method=='POST':
     self.calls.append((method,url,kw));raise TimeoutError()
    return super().request(method,url,**kw)
  http=TimeoutHTTP(preflight());record=AsyncMock()
  with self.assertRaisesRegex(client.PortalError,'submission_outcome_unknown'):
   await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,123,dry_run=False,confirm=True,record=record)
  self.assertEqual(len(http.calls),4);record.assert_not_awaited()
 async def test_invalid_digits_and_lower_reads_cannot_write(self):
  for reading in [True,12.3,'12.3','1e5',-1,'123abc']:
   with self.assertRaisesRegex(client.PortalError,'invalid_meter_reading'):
    await m.submit_gas_reading(client.BGEClient(HTTP([]),SESSION),KEY,reading)
  for reading in [99,100000]:
   http=HTTP(preflight())
   with self.assertRaises(client.PortalError):await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,reading,dry_run=False,confirm=True)
   self.assertTrue(all(method=='GET' for method,url,kw in http.calls))
 async def test_wrong_account_and_ineligible_never_write(self):
  http=HTTP(preflight(service='EL'))
  with self.assertRaisesRegex(client.PortalError,'not_a_gas_account'):
   await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,123,dry_run=False,confirm=True)
  self.assertEqual(len(http.calls),2)
  http=HTTP(preflight(eligible=False))
  with self.assertRaisesRegex(client.PortalError,'supplier_not_accepting_readings'):
   await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,123,dry_run=False,confirm=True)
  self.assertEqual(len(http.calls),3)
 async def test_equal_actual_reading_is_noop(self):
  http=HTTP(preflight())
  result=await m.submit_gas_reading(client.BGEClient(http,SESSION),KEY,100,dry_run=False,confirm=True)
  self.assertEqual(result['status'],'already_recorded');self.assertFalse(result['submitted'])

class MemoryStore:
 def __init__(self):self.data={}
 async def async_load(self):return copy.deepcopy(self.data)
 async def async_save(self,value):self.data=copy.deepcopy(value)
class Guard(unittest.IsolatedAsyncioTestCase):
 async def test_pending_reading_cannot_be_replayed_after_restart(self):
  store=MemoryStore();guard=m.SubmissionGuard(store)
  await guard.reserve(KEY,123)
  self.assertEqual(store.data[KEY]['status'],'pending')
  restarted=m.SubmissionGuard(store)
  with self.assertRaisesRegex(client.PortalError,'reading_already_sent_or_uncertain'):await restarted.reserve(KEY,123)
 async def test_accepted_reading_cannot_be_replayed(self):
  store=MemoryStore();guard=m.SubmissionGuard(store)
  await guard.reserve(KEY,123);await guard.record(KEY,123,'accepted')
  with self.assertRaisesRegex(client.PortalError,'reading_already_sent_or_uncertain'):await guard.reserve(KEY,123)
