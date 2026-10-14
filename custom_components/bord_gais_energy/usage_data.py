"""Supplier billed energy periods; never interpolated or cumulative counters."""
from .account_data import amount
from .gas_data import day

def normalize_electricity(report, account_id):
    history = []
    seen = {}
    if isinstance(report, dict) and isinstance(report.get('items'), list) and len(report['items']) <= 200:
        for row in report['items']:
            if not isinstance(row, dict) or row.get('accountId') != account_id:
                raise ValueError('invalid_usage_report')
            ident = row.get('billId')
            if not isinstance(ident, str) or not ident:
                raise ValueError('invalid_usage_report')
            start, end, issued = day(row.get('startDate')), day(row.get('endDate')), day(row.get('billDate'))
            kwh = amount(row.get('kwh', {}).get('total')) if isinstance(row.get('kwh'), dict) else None
            if not start or not end or not issued or start > end or kwh is None or kwh < 0:
                raise ValueError('invalid_usage_report')
            normalized = {'period_start': start, 'period_end': end, 'bill_date': issued,
                'usage_kwh': kwh, 'cost_including_vat': amount(row.get('cost')),
                'cost_excluding_vat': amount(row.get('costExVat')), 'vat': amount(row.get('vat'))}
            if ident in seen and seen[ident] != normalized:
                raise ValueError('conflicting_usage_bill')
            seen[ident] = normalized
        history = sorted(seen.values(), key=lambda x: (x['bill_date'], x['period_end']), reverse=True)
    elif report is not None:
        raise ValueError('invalid_usage_report')
    latest = history[0] if history else {}
    return {'electricity_usage_available': bool(history),
        'electricity_latest_billed_usage_kwh': latest.get('usage_kwh'),
        'electricity_bill_period_start': latest.get('period_start'),
        'electricity_bill_period_end': latest.get('period_end'),
        'electricity_latest_bill_cost': latest.get('cost_including_vat'),
        'electricity_latest_bill_vat': latest.get('vat'),
        'electricity_usage_history': history}
