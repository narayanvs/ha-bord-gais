"""Strict allowlist diagnostics; never expose sessions or account finances."""
async def async_get_config_entry_diagnostics(hass, entry):
    c = entry.runtime_data
    return {'integration_version': '0.1.0-beta.2', 'poll_hours': c.poll_hours,
            'account_count': len(c.data or {}), 'last_update_success': c.last_update_success,
            'last_successful_update': c.last_success.isoformat() if c.last_success else None,
            'transactions_available': [bool(v.get('transactions_available')) for v in (c.data or {}).values()]}
