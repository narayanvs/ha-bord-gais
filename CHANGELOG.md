# Changelog

## 0.1.0-beta.3

- Add experimental username/password setup and reauthentication, keeping browser session fallback.
- Read public client configuration from the login page; submit only one CAPTCHA-free password request per attempt.
- Log fixed request stages, HTTP statuses and error categories locally without credentials or response bodies.
- Persist a short login-attempt budget across HA restarts; discard passwords after authentication.

## 0.1.0-beta.2

- Add local integration icons required by HACS brand validation.
- Publish releases automatically from version updates on main after all checks pass.
- Validate release version and extract version-specific release notes before publishing.
- Mark the integration as Ireland-specific in HACS metadata.

## 0.1.0-beta.1

- Initial read-only supplier-account integration.
- Per-user browser-session setup, automatic token refresh and reauthentication.
- Separate electricity/gas balances, ordinary bill charges and dates.
- Weekly default polling, configurable up to 30 days, manual refresh and restart cache.
- Diagnostics omit credentials, customer identifiers and financial data.
