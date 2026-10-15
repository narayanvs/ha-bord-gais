# Changelog

## 0.1.0-beta.12

- Fix successful browser reauthentication crashing on Home Assistant because of an unsupported reload keyword.
- Use the supported update-and-abort API; the existing config-entry listener performs the session reload.
- Tighten the reauthentication regression test API signature so unsupported keywords fail tests.

## 0.1.0-beta.11

- Renew before access-token expiry as well as refresh-token expiry, including cached startup with an expired access token.
- Mark supplier entities unavailable when session renewal requires reauthentication; retain the cached snapshot without presenting it as a working connection.
- Add credential-free session-renewal diagnostics and stop account requests after confirmed authentication failure.
- Use the config-entry update listener for reauthentication reloads; ordinary token rotation never reloads the integration.
- A supplier-revoked session (for example after another login) still requires browser sign-in; this release does not claim to bypass supplier session policy.


## 0.1.0-beta.10

- Add electricity billed usage, period dates, billed cost and VAT sensors alongside gas usage.
- Expose identifier-free billed history for both fuels; missing reports remain unknown, never zero or fabricated daily values.
- Fetch optional electricity reports on the existing polling schedule, with one cache refresh on upgrade.
- Electricity report parsing is tested against the shared portal schema; live account verification still requires a valid supplier session.

## 0.1.0-beta.9

- Expose an admin-only manual gas meter-reading action in HA, with preview enabled by default and explicit confirmation required for real submissions.
- Validate the selected gas account, current supplier eligibility, digit count and last actual reading before sending.
- Send at most one gas-reading POST per action; never replay writes after authentication failures, timeouts or ambiguous responses.
- Persist a pre-send guard so identical accepted/uncertain readings cannot be blindly resent after an HA restart.
- Tests use synthetic readings and mocked HTTP only; no actual supplier reading has been submitted by development checks.

## 0.1.0-beta.8

- Add supplier-reported billed gas usage (kWh), bill-period dates, cost including VAT and VAT amount.
- Add the last actual gas meter-register reading and date; do not guess its physical unit.
- Include normalized billed-period history on the gas-usage sensor, with account and bill identifiers removed.
- Fetch gas reports on the existing account-update schedule; preserve financial data if optional gas endpoints fail.
- Refresh older cached gas snapshots once on upgrade so the new sensors populate.
- Billed usage is a period total, not live/daily gas flow or a cumulative HA Energy counter.

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
