import copy,importlib,json,unittest
from support import client
from test_client import HTTP,Response,SESSION,account_listing,transactions
m=importlib.import_module('bge_test_component.gas_data')

def row(ident='synthetic-bill',issued='2024-03-02',kwh=123):
 return {'accountId':'synthetic-account','billId':ident,'billDate':issued,
  'startDate':'2024-01-01','endDate':'2024-03-01',
  'kwh':{'total':kwh,'day':0,'night':0,'peak':0},'cost':12.5,'costExVat':11.47,'vat':1.03}
def meter():
 return {'lastActualReadDate':'2024-03-01','lastActualReads':[{'registerType':'Gas Meter','readValue':3210}]}
class Model(unittest.TestCase):
 def test_verified_fields_and_private_ids_removed(self):
  result=m.normalize_gas({'items':[row()]},meter(),'synthetic-account')
  self.assertEqual(result['gas_latest_billed_usage_kwh'],123)
  self.assertEqual(result['gas_latest_bill_cost'],12.5)
  self.assertEqual(result['gas_last_actual_reading'],3210)
  self.assertEqual(result['gas_bill_period_start'],'2024-01-01')
  for private in ['synthetic-account','synthetic-bill','accountId','billId']:self.assertNotIn(private,json.dumps(result))
 def test_missing_reports_are_unknown_not_zero(self):
  result=m.normalize_gas(None,None,'synthetic-account')
  self.assertIsNone(result['gas_latest_billed_usage_kwh']);self.assertIsNone(result['gas_last_actual_reading'])
  self.assertFalse(result['gas_usage_available'])
 def test_exact_duplicates_not_counted_twice(self):
  result=m.normalize_gas({'items':[row(),row()]},None,'synthetic-account')
  self.assertEqual(len(result['gas_usage_history']),1)
 def test_latest_bill_selected_by_date(self):
  result=m.normalize_gas({'items':[row(),row('synthetic-new','2024-04-02',77)]},None,'synthetic-account')
  self.assertEqual(result['gas_latest_billed_usage_kwh'],77)
 def test_wrong_account_and_conflicting_bill_rejected(self):
  wrong=row();wrong['accountId']='different-account'
  for rows in [[wrong],[row(),row(kwh=456)]]:
   with self.assertRaises(ValueError):m.normalize_gas({'items':rows},None,'synthetic-account')
 def test_negative_or_invalid_usage_and_dates_rejected(self):
  for change in [{'kwh':{'total':-1}},{'kwh':{'total':True}},{'startDate':'invalid'},{'endDate':'2023-01-01'}]:
   r={**row(),**change}
   with self.assertRaises(ValueError):m.normalize_gas({'items':[r]},None,'synthetic-account')

class Requests(unittest.IsolatedAsyncioTestCase):
 def details(self):return Response(data={'account':{'accountId':'synthetic-account','serviceType':'GS','balance':0}})
 async def test_gas_endpoints_are_read_only_and_normalized(self):
  http=HTTP([account_listing(),self.details(),transactions(),Response(data={'items':[row()]}),Response(data=meter())])
  result=next(iter((await client.BGEClient(http,SESSION).fetch()).values()))
  self.assertEqual(result['gas_latest_billed_usage_kwh'],123)
  self.assertTrue(all(method=='GET' for method,url,kw in http.calls))
  self.assertEqual(http.calls[3][2]['params']['accountType'],'QH')
  self.assertNotIn('synthetic-account',json.dumps(result))
 async def test_optional_report_failure_preserves_finances_and_meter(self):
  http=HTTP([account_listing(),self.details(),transactions(),Response(500),Response(data=meter())])
  result=next(iter((await client.BGEClient(http,SESSION).fetch()).values()))
  self.assertEqual(result['account_amount_due'],0)
  self.assertFalse(result['gas_usage_available']);self.assertEqual(result['gas_last_actual_reading'],3210)
 async def test_usage_rate_limit_stops_without_retry(self):
  http=HTTP([account_listing(),self.details(),transactions(),Response(429)])
  with self.assertRaisesRegex(client.PortalError,'rate_limited'):await client.BGEClient(http,SESSION).fetch()
  self.assertEqual(len(http.calls),4)
 async def test_extra_params_and_writes_rejected(self):
  c=client.BGEClient(HTTP([]),SESSION)
  for params in [{'accountId':'../other'},{'accountId':'synthetic-account','extra':'private'}]:
   with self.assertRaisesRegex(client.PortalError,'forbidden_endpoint'):await c._request('/api/meters/v1/config',params=params)
  with self.assertRaisesRegex(client.PortalError,'forbidden_endpoint'):
   await c._request('/api/meters/v1/read',payload={'accountId':'synthetic-account'})
