# Bord Gáis Energy Account for Home Assistant

An unofficial, read-only supplier-account integration for Home Assistant. It reports actual Bord Gáis account credit/balance, bills and payment due dates. It complements ESB meter integrations; it does not import duplicate electricity readings or require solar, an inverter, MQTT or another container.

**Early beta:** authenticated account reads and one token refresh have been verified against a real electricity/gas account. Long-term refresh reliability and other account types still need testing. This is not affiliated with Bord Gáis Energy.

## Authentication

**Beta.3 adds experimental username/password setup.** Choose that option in Devices & Services to submit one login request without a CAPTCHA token. This is a test path: password-only authentication has not yet been verified against a real account. If the portal requires CAPTCHA or OTP, use the verified **Browser session** fallback. The integration attempts session-token refresh automatically; if renewal fails, HA requests reauthentication. Your username and password are used only for the login request and are not saved in the config entry.

No credentials, real account identifiers, customer files or financial snapshots belong in this repository. Sessions are stored in HA's config-entry storage and normalized financial data in its local cache. They are **not encrypted by this integration**; protect HA's config directory and backups as you would other integration credentials. Downloadable integration diagnostics exclude tokens, identifiers, addresses and financial figures.

## Install with HACS

Once this repository is published:

1. HACS → Custom repositories → add this repository as **Integration**.
2. Download **Bord Gáis Energy Account** and restart HA.
3. Settings → Devices & Services → Add integration → **Bord Gáis Energy Account**.
4. Choose **Username and password (experimental)** and enter your credentials privately into HA. If login fails, inspect the safe local log category and switch to **Browser session**. For the session fallback, follow the steps below.
4. Sign in normally at https://www.bordgaisenergy.ie/sign-in in Chrome.
5. On that signed-in page, open Developer Console (`⌘⌥J` on macOS) and run:

   ```javascript
   copy(JSON.stringify({
     accessToken: localStorage.getItem('bgeAccessToken'),
     refreshToken: localStorage.getItem('bgeRefreshToken'),
     anonymousId: localStorage.getItem('bgeSessionUuid')
   }))
   ```

   `undefined` is normal: the command copies the session JSON to your clipboard.
6. Paste it into the integration's masked **Browser session JSON** field. Clear the clipboard afterward. Never paste session tokens into chat, issues or screenshots.

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

### What it does not calculate

The supplier account balance is authoritative as reported; it excludes our own estimates of unbilled usage and unposted export earnings. Combined microgeneration bills can contain net amounts. This beta does not guess separate export-credit components or gross bill charges from those amounts. The bill-summary endpoint failed in initial testing and is not polled.

The portal's `lastBill.amount` is a resulting balance, not necessarily the bill charge. The integration deliberately uses the matching ordinary transaction's `billAmount` for bill charge.

## Polling, cache and restarts

Default polling is **weekly (168 hours)** because bills are monthly. Options allow 24–720 hours; **720** means every 30 days, not a calendar-month schedule. Payments and posted credits can change between bills, so the update timestamp matters.

HA reloads/restarts reuse the cached account data until the next update is due. Cached data retains its original timestamp. Expired tokens are refreshed once; rotated tokens are persisted immediately. A rejected session triggers HA reauthentication. Network failures leave entities unavailable rather than showing invented zero balances. Manual refresh is limited to one attempt every five minutes; rate limiting delays automatic retries.

All updates are asynchronous and normally involve one account-list request plus two reads per account. No PDFs or CSVs accumulate. Only the latest normalized snapshot is cached; recorder history follows your HA settings.

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install aiohttp
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

## Password-login debugging

Failed password login logs a warning containing only stage, HTTP status and a fixed category. It does not log the username, password, API key, anonymous ID, headers, request/response bodies or tokens. A generic 400/401/403 rejection alone does not prove CAPTCHA is mandatory. No CAPTCHA token is fabricated or challenge bypass attempted. OTP challenges are detected but require browser-session fallback for now.

For extra local stage logs, call HA action `logger.set_level` with:

```yaml
custom_components.bord_gais_energy.auth: debug
```

Only enable this integration logger; enabling global HTTP or aiohttp debug logging can reveal credentials outside this integration's logging controls. Remove debug logging after testing.

Login attempts are limited to three per username in 15 minutes, at least 60 seconds apart, shared across setup flows and persisted through restarts. The budget stores only a hash and timestamps, never the username or password. These are local protective limits, not a claim about the supplier's lockout policy.
