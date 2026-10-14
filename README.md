# Bord Gáis Energy Account for Home Assistant

An unofficial, read-only supplier-account integration for Home Assistant. It reports actual Bord Gáis account credit/balance, bills and payment due dates. It complements ESB meter integrations; it does not import duplicate electricity readings or require solar, an inverter, MQTT or another container.

**Early beta:** authenticated account reads and one token refresh have been verified against a real electricity/gas account. Long-term refresh reliability and other account types still need testing. This is not affiliated with Bord Gáis Energy.

## Authentication

**Browser sign-in**, verified with a real electricity/gas account. HA opens a separate browser tab/window containing the normal supplier sign-in page. You complete CAPTCHA normally; the integration captures and validates the resulting renewable session without JSON copying. After successful setup the tab tries to close automatically. Browser restrictions can prevent closing; a clear completion message and Close tab button remain available. Whether a browser opens a tab or window is controlled by its settings. Session refresh remains automatic; rejected refresh requests trigger reauthentication with the same sign-in choices.

**Local-network beta limitation:** browser sign-in temporarily serves HTTPS on Home Assistant's private IPv4 address, port **8743**. Use the same LAN/Wi-Fi as HA and allow that port locally. A temporary self-signed certificate means accepting a warning for that specific local address. No certificate installation, external container or browser extension is needed. Do not expose or forward this port through your router, tunnel or public reverse proxy. Remote-only users can use the browser-session fallback below. Supplier JavaScript runs on a separate browser origin, not on the HA frontend origin.

The initial link is random and single-use. The listener requires a Secure/HttpOnly cookie and validates POST origins, forwards only login and sign-in asset requests, and expires after 15 minutes (or shortly after completion). The TLS key and certificate are generated temporarily and removed on normal cleanup; an abrupt container crash can leave a small temporary directory for the OS to clean. Passwords are forwarded in memory, never saved. Supplier session keys use tab-scoped browser storage and are cleared on the completion page. HA retains the renewable session using its existing config-entry storage.

Beta.6 removes experimental direct username/password setup, which was rejected by the supplier. Choose browser sign-in normally; browser-session JSON remains a fallback when local browser sign-in is unavailable. OTP flows use the supplier page but have not been verified with a real OTP-enabled account.

No credentials, real account identifiers, customer files or financial snapshots belong in this repository. Sessions are stored in HA's config-entry storage and normalized financial data in its local cache. They are **not encrypted by this integration**; protect HA's config directory and backups as you would other integration credentials. Downloadable integration diagnostics exclude tokens, identifiers, addresses and financial figures.

## Install with HACS

1. HACS → Custom repositories → add this repository as **Integration**.
2. Download **Bord Gáis Energy Account** and restart HA. Enable beta versions in HACS to select this prerelease.
3. Settings → Devices & Services → Add integration → **Bord Gáis Energy Account**.
4. Choose **Sign in with browser (local network beta)**. HA detects its local IPv4 address automatically. A manual address form appears only if detection fails or advanced setup is selected.
5. In the separate browser window, accept the certificate exception for that local address and log in normally. Allow HA's popup if the browser blocks it. Setup finishes automatically and the tab attempts to close after success. No token copying is required.

For an existing connection, updating the integration does not force a new login. HA offers reauthentication when its saved session cannot renew; choose browser sign-in there. Adding the same accounts again will report that they are already configured.

### Browser-session fallback

1. Choose **Browser session** during setup or reauthentication.
2. Sign in normally at https://www.bordgaisenergy.ie/sign-in in Chrome.
3. On that signed-in page, open Developer Console (`⌘⌥J` on macOS) and run:

   ```javascript
   copy(JSON.stringify({
     accessToken: localStorage.getItem('bgeAccessToken'),
     refreshToken: localStorage.getItem('bgeRefreshToken'),
     anonymousId: localStorage.getItem('bgeSessionUuid')
   }))
   ```

   `undefined` is normal: the command copies the session JSON to your clipboard.
4. Paste it into the integration's masked **Browser session JSON** field. Clear the clipboard afterward. Never paste session tokens into chat, issues or screenshots.

Electricity and gas accounts are discovered automatically and receive separate devices. Multiple accounts of the same service type have separate stable IDs even if their initial display names match.

## Entities

Each account exposes:

| Sensor | Meaning |
|---|---|
| Account balance | Supplier-reported EUR balance: negative = credit, positive = amount due |
| Account credit | Positive presentation of existing supplier credit |
| Amount due | Positive presentation of money owed |
| Latest bill charge | Ordinary bill charge from the matching transaction; unknown for combined microgeneration bills |
| Latest bill issued / due | Supplier dates for the latest bill |
| Next bill | Supplier's expected bill date |
| Last successful update | Timestamp of the last successful supplier read |

One diagnostic **Refresh** button updates all accounts. These balances are not cumulative energy counters and have no `total_increasing` state class.

### Gas usage (beta.8)

Gas accounts also expose **latest billed gas usage (kWh)**, the bill period's start/end dates, billed-period cost including VAT, VAT amount, and the last actual meter reading/date. This is real supplier-reported data. The gas-usage sensor's `billed_history` attribute holds normalized billed periods returned for a rolling one-year request; it contains no account or bill identifiers. Available history depends on the supplier account. No daily usage is invented between meter readings.

The meter endpoint supplies the register value but does not identify its physical unit, so the integration does not label it m³ or convert it. Use billed kWh for comparable energy amounts. These sensors update when the supplier publishes readings/bills and HA next polls; they are not live measurements.

**Do not use the latest billed usage as a cumulative HA Energy gas counter.** It is an individual bill-period quantity, has no `total_increasing` state class, and can legitimately decrease on the next bill. The integration does not allocate a two-month bill across individual days. Period dates and history support bill-to-bill charts and comparisons.

Gas reports add two read-only requests per gas account on the existing account-update schedule. A missing/malformed gas response leaves usage unknown without inventing zero or discarding otherwise valid financial data. A supplier rate limit still stops the update. Upgrading an older cached gas account performs one new account-data update to populate these fields.

### What it does not calculate

The supplier account balance is authoritative as reported; it excludes our own estimates of unbilled usage and unposted export earnings. Combined microgeneration bills can contain net amounts. This beta does not guess separate export-credit components or gross bill charges from those amounts. The bill-summary endpoint failed in initial testing and is not polled.

The portal's `lastBill.amount` is a resulting balance, not necessarily the bill charge. The integration deliberately uses the matching ordinary transaction's `billAmount` for bill charge.

## Polling, cache and restarts

Default account-data polling is **weekly (168 hours)** because bills are monthly. Options allow 24–720 hours; **720** means every 30 days, not a calendar-month schedule. Payments and posted credits can change between bills, so the update timestamp matters.

**Session renewal is separate from bill downloads.** Observed access tokens expire after about five minutes and refresh tokens after 15 minutes. Beta.7 schedules a lightweight token-renewal request before the refresh token expires (normally about every ten minutes), persisting rotated tokens immediately. It does not download account/bill data each time. Authentication or rate-limit rejection stops renewal and requests reauthentication; transient failures get only bounded retries. If HA is offline past refresh-token expiry, a new browser sign-in is needed. Indefinite unattended renewal has not yet been proved.

HA reloads/restarts reuse the cached account data until the next update is due. Cached data retains its original timestamp. Expired tokens are refreshed once; rotated tokens are persisted immediately. A rejected session triggers HA reauthentication. Network failures leave entities unavailable rather than showing invented zero balances. Manual refresh is limited to one attempt every five minutes; rate limiting delays automatic retries.

All requests are asynchronous. Account-data updates normally involve one account-list request plus two reads per account; session renewal is one additional small request on its separate timer. No PDFs or CSVs accumulate. Only the latest normalized snapshot is cached; recorder history follows your HA settings.

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install aiohttp cryptography voluptuous
python3 -m unittest discover -s tests -v
python3 -m compileall -q custom_components
```

Tests use synthetic sessions and account IDs. Do not use real portal credentials as fixtures. No authenticated network requests run in CI. HA runtime/config-flow installation still requires beta testing on an actual HA instance.

## Limitations

Private portal endpoints may change without notice. A successful refresh today does not guarantee indefinite unattended access. CAPTCHA/MFA are handled through the normal website, not bypassed. Only verified residential electricity and gas response formats are supported initially. Account-list pagination is checked; unexpected partial lists fail explicitly.

## Publishing this repository

Create the public `ha-bord-gais` repository, then push `main`. Add GitHub topics `home-assistant`, `hacs`, `custom-integration`, `bord-gais` and `ireland` so HACS repository checks pass. Version updates pushed to `main` automatically run validation and publish a matching release. Beta/alpha/rc versions become prereleases; stable versions become normal releases. Bump the manifest version and add matching changelog notes for each release; no manual tag is needed. The Release workflow can also be rerun manually after fixing repository metadata. Existing releases are left unchanged. Enable beta versions in HACS to select it. Being installable as a HACS custom repository does not mean inclusion in the default HACS catalogue.

## Licence

MIT. This integration was written independently from observations of the public portal frontend and verified private responses; no supplier frontend bundles, customer files or existing ESB integration code are distributed.

## Sign-in diagnostics and certificate warnings

Browser sign-in logs fixed outcome/status categories, never passwords, tokens, account identifiers or request bodies. Do not enable global HTTP/aiohttp debug logging while authenticating. Login attempts are limited to three per username per 15 minutes and at least 60 seconds apart; only hashed usernames and timestamps are saved for this protective budget.

Automatic IP detection removes the normal address-entry step, but cannot make a self-signed certificate trusted. Removing the warning needs either a certificate trusted on every client, or a dedicated login hostname served with a trusted certificate (for example through a locally accessible reverse proxy). Keep that hostname separate from the HA frontend to isolate supplier scripts. A trusted-hostname proxy mode is not implemented in this beta; do not forward the current listener publicly or assume a hostname alone fixes its certificate.
