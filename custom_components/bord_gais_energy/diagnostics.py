"""Strict allowlist diagnostics; never expose sessions or account finances."""
async def async_get_config_entry_diagnostics(hass, entry):
    c = entry.runtime_data
    return {'integration_version': '0.1.0-beta.11', 'poll_hours': c.poll_hours,
            'account_count': len(c.data or {}), 'last_update_success': c.last_update_success,
            'last_successful_update': c.last_success.isoformat() if c.last_success else None,
            'session_requires_reauthentication': c._session_auth_failed,
            'session_renewals_since_load': c.renewal_count,
            'last_session_renewal': c.last_renewal_success.isoformat() if c.last_renewal_success else None,
            'last_session_renewal_error': c.last_renewal_error,
            'transactions_available': [bool(v.get('transactions_available')) for v in (c.data or {}).values()]}
