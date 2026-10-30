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
  self.assertEqual(result['electricity_bill_period_start'],'2024-01-02')
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

class CombinedBills(unittest.TestCase):
 def report(self):
  consumption={**row(), 'cost':80, 'costExVat':73.39, 'vat':6.61}
  export={**row(kwh=0), 'cost':0, 'costExVat':-200, 'vat':0,
          'startDate':'2023-12-01', 'endDate':'2024-02-01'}
  return consumption,export
 def test_combined_rows_and_duplicates_are_separate(self):
  consumption,export=self.report()
  result=m.normalize_electricity({'items':[export,consumption,export,consumption]},'synthetic-account')
  self.assertEqual(result['electricity_latest_bill_cost'],80)
  self.assertEqual(result['electricity_posted_export_credit'],200)
  self.assertEqual(len(result['electricity_usage_history']),1)
  self.assertEqual(result['electricity_export_period_start'],'2023-12-02')
  self.assertNotIn('synthetic-bill',json.dumps(result))
 def test_ev_subtotal_is_never_presented_as_total(self):
  consumption,export=self.report()
  result=m.normalize_electricity({'items':[consumption,export]},'synthetic-account',usage_complete=False)
  self.assertIsNone(result['electricity_latest_billed_usage_kwh'])
  self.assertEqual(result['electricity_reported_usage_subtotal_kwh'],123)
  self.assertFalse(result['electricity_usage_available'])
  self.assertTrue(result['electricity_report_available'])
  self.assertIsNone(result['electricity_usage_history'][0]['usage_kwh'])
 def test_missing_latest_bill_does_not_use_previous(self):
  consumption,export=self.report()
  result=m.normalize_electricity({'items':[consumption,export]},'synthetic-account',latest_bill_id='new-bill')
  self.assertIsNone(result['electricity_latest_bill_cost'])
  self.assertIsNone(result['electricity_posted_export_credit'])
 def test_conflicting_export_is_rejected(self):
  consumption,export=self.report()
  with self.assertRaises(ValueError):
   m.normalize_electricity({'items':[consumption,export,{**export,'costExVat':-201}]},'synthetic-account')
 def test_bill_reconciliation_uses_net_charge_not_account_balance(self):
  from support import model
  consumption,export=self.report()
  usage=m.normalize_electricity({'items':[consumption,export]},'synthetic-account',latest_bill_id='synthetic-bill')
  details={'account':{'balance':-700},'lastBill':{'billId':'synthetic-bill'}}
  transaction={'type':'Bill','transactionType':'BillWithMicrogenCredit','billId':'synthetic-bill','billAmount':-120}
  result=model.summarize(details,[transaction],usage)
  self.assertEqual(result['latest_bill_charge'],80)
  self.assertEqual(result['posted_export_credit'],200)
  self.assertEqual(result['account_credit'],700)
  self.assertIsNone(model.summarize(details,[{**transaction,'billAmount':-121}],usage)['latest_bill_charge'])
 def test_invalid_export_shapes_not_accepted(self):
  consumption,export=self.report()
  for change in [{'cost':1},{'vat':1},{'kwh':{'total':1}}]:
   with self.assertRaises(ValueError):
    m.normalize_electricity({'items':[consumption,{**export,**change}]},'synthetic-account')
