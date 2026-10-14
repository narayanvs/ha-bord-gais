import importlib,json,unittest
from support import client
from test_client import HTTP,Response,SESSION,account_listing,details,transactions
from test_gas_data import row
m=importlib.import_module('bge_test_component.usage_data')

class Usage(unittest.TestCase):
 def test_period_and_history_are_normalized_without_identifiers(self):
  result=m.normalize_electricity({'items':[row(),row()]},'synthetic-account')
  self.assertEqual(result['electricity_latest_billed_usage_kwh'],123)
  self.assertEqual(result['electricity_latest_bill_cost'],12.5)
  self.assertEqual(result['electricity_bill_period_start'],'2024-01-01')
  self.assertEqual(len(result['electricity_usage_history']),1)
  self.assertNotIn('synthetic-account',json.dumps(result))
  self.assertNotIn('synthetic-bill',json.dumps(result))
 def test_unknown_is_not_zero(self):
  result=m.normalize_electricity(None,'synthetic-account')
  self.assertFalse(result['electricity_usage_available'])
  self.assertIsNone(result['electricity_latest_billed_usage_kwh'])
 def test_wrong_account_negative_and_conflicting_rows_rejected(self):
  for rows in [[{**row(),'accountId':'other'}],[row(kwh=-1)],[row(),row(kwh=456)]]:
   with self.assertRaises(ValueError):m.normalize_electricity({'items':rows},'synthetic-account')

class Requests(unittest.IsolatedAsyncioTestCase):
 async def test_electricity_reads_report_without_gas_meter_request(self):
  http=HTTP([account_listing(),details(),transactions(),Response(data={'items':[row()]})])
  result=next(iter((await client.BGEClient(http,SESSION).fetch()).values()))
  self.assertEqual(result['electricity_latest_billed_usage_kwh'],123)
  self.assertEqual(len(http.calls),4)
  self.assertTrue(all(method=='GET' for method,url,kw in http.calls))
 async def test_optional_failure_preserves_financial_data(self):
  http=HTTP([account_listing(),details(),transactions(),Response(500)])
  result=next(iter((await client.BGEClient(http,SESSION).fetch()).values()))
  self.assertEqual(result['account_credit'],12.5)
  self.assertIsNone(result['electricity_latest_billed_usage_kwh'])
