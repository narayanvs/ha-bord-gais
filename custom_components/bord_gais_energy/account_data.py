"""Normalize verified portal fields without treating balances as bill charges."""
from decimal import Decimal, InvalidOperation


def amount(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
        return float(result) if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def summarize(details, transactions):
    account = details.get('account', {})
    balance = amount(account.get('balance'))
    last_bill = details.get('lastBill', {})
    matched = next((r for r in transactions if isinstance(r, dict)
                    and r.get('type') == 'Bill'
                    and r.get('billId') == last_bill.get('billId')), None)
    # billAmount is the bill charge for ordinary bills, but includes microgen
    # netting on BillWithMicrogenCredit. Do not fabricate a gross charge there.
    charge = amount(matched.get('billAmount')) if matched and matched.get('transactionType') == 'Bill' else None
    return {
        'service': {'EL': 'electricity', 'GS': 'gas'}.get(account.get('serviceType'), 'other'),
        'currency': 'EUR',
        'supplier_balance': balance,
        'balance_convention': 'negative_credit_positive_due',
        'account_credit': max(-balance, 0) if balance is not None else None,
        'account_amount_due': max(balance, 0) if balance is not None else None,
        'latest_bill_issue_date': last_bill.get('billDate'),
        'latest_bill_due_date': last_bill.get('dueDate'),
        'latest_bill_charge': charge,
        'latest_bill_resulting_balance': amount(last_bill.get('amount')),
        'next_bill_date': details.get('nextBill'),
        'has_export_capability': account.get('hasExportCapability') is True,
        'posted_export_credit': None,
        'posted_export_credit_status': 'not_separately_exposed_in_verified_responses',
        'transaction_count': len(transactions),
        'estimated_unbilled_balance': None,
        'estimated_unbilled_balance_status': 'not_calculated',
    }
