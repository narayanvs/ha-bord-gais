import unittest
from support import model
summarize = model.summarize

class Tests(unittest.TestCase):
    def test_charge_is_not_account_balance(self):
        d={'account':{'serviceType':'EL','balance':-12.50},'lastBill':{'billId':'test','amount':-12.50}}
        s=summarize(d,[{'type':'Bill','transactionType':'Bill','billId':'test','billAmount':7.25}])
        self.assertEqual(s['account_credit'],12.50)
        self.assertEqual(s['account_amount_due'],0)
        self.assertEqual(s['latest_bill_charge'],7.25)
        self.assertEqual(s['latest_bill_resulting_balance'],-12.50)
    def test_missing_values_are_not_zero(self):
        s=summarize({},[])
        self.assertIsNone(s['account_credit'])
        self.assertIsNone(s['latest_bill_charge'])
    def test_combined_microgen_bill_is_not_gross_charge(self):
        s=summarize({'lastBill':{'billId':'test'}},[{'type':'Bill','transactionType':'BillWithMicrogenCredit','billId':'test','billAmount':-15.75}])
        self.assertIsNone(s['latest_bill_charge'])
        self.assertIsNone(s['posted_export_credit'])

if __name__=='__main__':unittest.main()
