# Changelog

## 0.1.0-beta.7

- Fix session expiry after browser sign-in: observed access tokens last five minutes and refresh tokens 15 minutes.
- Renew the session before refresh-token expiry, independently of weekly account downloads; persist every rotated token immediately.
- Stop renewal on authentication/rate-limit failures, bound transient retries, and cancel timers on unload.
- Preserve captured session scheduling after cached restarts; request browser reauthentication if HA was offline beyond token expiry.
- Move temporary browser certificate cleanup out of the HA event loop.
- Gas-usage endpoints remain under investigation; this release does not add unverified usage sensors.

## 0.1.0-beta.6

- Remove the unsuccessful experimental direct username/password option; keep browser sign-in and session JSON fallback.
- Automatically detect the local IPv4 address through HA networking for browser sign-in, avoiding the normal manual IP step.
- Retain manual entry when detection fails or advanced setup is selected.
- The temporary self-signed certificate warning still applies; trusted-hostname deployment remains a separate future improvement.

## 0.1.0-beta.5

- Fix the browser sign-in completion race that could report invalid flow after successful supplier authentication.
- Let Home Assistant consume the external-step completion once; retain the captured session until that finish request.
- Clear unconsumed session captures when the temporary login server expires or closes.

## 0.1.0-beta.4

- Add browser sign-in and reauthentication with normal supplier CAPTCHA handling; verified locally with one electricity/gas account.
- Capture renewable sessions automatically without copying JSON; validate accounts before setup and reject wrong-account reauthentication.
- Isolate supplier scripts from HA browser storage using a temporary HTTPS listener on the private LAN IP, with a generated local certificate.
- Complete the HA flow automatically and clean up the short-lived listener, certificate and browser session keys.
- Preserve browser-session and experimental password fallbacks, existing polling, restart cache and token refresh.
- Document the beta limitation: local-network browser login and a temporary certificate exception are required.

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
