"""Verified billed gas usage and actual register reads; no daily interpolation."""
from datetime import date
from .account_data import amount


def day(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def normalize_gas(report, meter, account_id):
    history = []
    seen = {}
    if isinstance(report, dict) and isinstance(report.get('items'), list) and len(report['items']) <= 200:
        for row in report['items']:
            if not isinstance(row, dict) or row.get('accountId') != account_id:
                raise ValueError('invalid_gas_report')
            ident = row.get('billId')
            if not isinstance(ident, str) or not ident:
                raise ValueError('invalid_gas_report')
            start, end, issued = day(row.get('startDate')), day(row.get('endDate')), day(row.get('billDate'))
            kwh = amount(row.get('kwh', {}).get('total')) if isinstance(row.get('kwh'), dict) else None
            if not start or not end or not issued or start > end or kwh is None or kwh < 0:
                raise ValueError('invalid_gas_report')
            normalized = {'period_start': start, 'period_end': end, 'bill_date': issued,
                'usage_kwh': kwh, 'cost_including_vat': amount(row.get('cost')),
                'cost_excluding_vat': amount(row.get('costExVat')), 'vat': amount(row.get('vat'))}
            if ident in seen and seen[ident] != normalized:
                raise ValueError('conflicting_gas_bill')
            seen[ident] = normalized
        history = sorted(seen.values(), key=lambda x: (x['bill_date'], x['period_end']), reverse=True)
    elif report is not None:
        raise ValueError('invalid_gas_report')
    latest = history[0] if history else {}
    reading = None
    read_date = None
    if isinstance(meter, dict):
        reads = meter.get('lastActualReads', [])
        gas_reads = [r for r in reads if isinstance(r, dict) and r.get('registerType') == 'Gas Meter'] if isinstance(reads, list) else []
        if len(gas_reads) == 1:
            reading = amount(gas_reads[0].get('readValue'))
            read_date = day(meter.get('lastActualReadDate'))
            if reading is not None and reading < 0:
                reading = None
    return {'gas_usage_available': bool(history), 'gas_latest_billed_usage_kwh': latest.get('usage_kwh'),
        'gas_bill_period_start': latest.get('period_start'), 'gas_bill_period_end': latest.get('period_end'),
        'gas_latest_bill_cost': latest.get('cost_including_vat'), 'gas_latest_bill_vat': latest.get('vat'),
        'gas_usage_history': history, 'gas_last_actual_reading': reading, 'gas_last_actual_read_date': read_date,
        'gas_meter_available': reading is not None and read_date is not None}
