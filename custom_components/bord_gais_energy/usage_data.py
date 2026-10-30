"""Supplier billed periods: separate consumption charges from export credits."""
from datetime import date, timedelta
from .account_data import amount
from .gas_data import day


def normalize_electricity(report, account_id, *, usage_complete=True, latest_bill_id=None):
    bills = {}
    if report is not None:
        if not isinstance(report, dict) or not isinstance(report.get('items'), list) or len(report['items']) > 200:
            raise ValueError('invalid_usage_report')
        for row in report['items']:
            if not isinstance(row, dict) or row.get('accountId') != account_id:
                raise ValueError('invalid_usage_report')
            ident = row.get('billId')
            if not isinstance(ident, str) or not ident:
                raise ValueError('invalid_usage_report')
            start, end, issued = day(row.get('startDate')), day(row.get('endDate')), day(row.get('billDate'))
            kwh = amount(row.get('kwh', {}).get('total')) if isinstance(row.get('kwh'), dict) else None
            cost, exvat, vat = (amount(row.get(k)) for k in ('cost', 'costExVat', 'vat'))
            if not start or not end or not issued or start >= end or kwh is None or kwh < 0:
                raise ValueError('invalid_usage_report')
            # QH report startDate is the exclusive previous-day boundary. End is inclusive.
            period_start = (date.fromisoformat(start) + timedelta(days=1)).isoformat()
            export = cost == 0 and exvat is not None and exvat < 0 and vat == 0 and kwh == 0
            if not export and (cost is None or exvat is None or vat is None or min(cost, exvat, vat) < 0
                               or abs(cost - exvat - vat) > 0.021):
                raise ValueError('invalid_usage_report')
            normalized = {'period_start': period_start, 'period_end': end, 'bill_date': issued,
                          'report_start_boundary': start}
            if export:
                normalized['credit'] = -exvat
            else:
                normalized.update(usage_kwh=kwh if usage_complete else None,
                    reported_usage_subtotal_kwh=kwh, usage_complete=usage_complete,
                    cost_including_vat=cost, cost_excluding_vat=exvat, vat=vat)
            group = bills.setdefault(ident, {})
            kind = 'export' if export else 'consumption'
            if kind in group and group[kind] != normalized:
                raise ValueError('conflicting_usage_bill')
            if any(v['bill_date'] != issued for v in group.values()):
                raise ValueError('conflicting_usage_bill')
            group[kind] = normalized
    history = sorted((g['consumption'] for g in bills.values() if 'consumption' in g),
                     key=lambda x: (x['bill_date'], x['period_end']), reverse=True)
    if latest_bill_id is not None:
        group = bills.get(latest_bill_id, {})
        latest, export = group.get('consumption', {}), group.get('export', {})
    else:
        latest = history[0] if history else {}
        group = next((g for g in bills.values() if g.get('consumption') == latest), {}) if latest else {}
        export = group.get('export', {})
    return {'electricity_report_available': bool(latest),
        'electricity_usage_available': bool(latest) and usage_complete,
        'electricity_usage_status': 'supplier_ev_usage_omitted' if latest and not usage_complete else 'available' if latest else 'not_available',
        'electricity_latest_billed_usage_kwh': latest.get('usage_kwh'),
        'electricity_reported_usage_subtotal_kwh': latest.get('reported_usage_subtotal_kwh'),
        'electricity_bill_period_start': latest.get('period_start'),
        'electricity_bill_period_end': latest.get('period_end'),
        'electricity_latest_bill_cost': latest.get('cost_including_vat'),
        'electricity_latest_bill_vat': latest.get('vat'),
        'electricity_usage_history': history,
        'electricity_posted_export_credit': export.get('credit'),
        'electricity_export_period_start': export.get('period_start'),
        'electricity_export_period_end': export.get('period_end')}
