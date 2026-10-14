"""Explicit gas-reading writes, isolated from the read-only polling client."""
import hashlib
import re
import time
import aiohttp
from .client import BASE, AuthError, PortalError
from .gas_data import normalize_gas


class SubmissionRejected(PortalError):
    """Supplier explicitly rejected a write; it was not automatically retried."""


def reading_value(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise PortalError('invalid_meter_reading')
    text = str(value).strip()
    if not re.fullmatch(r'[0-9]{1,9}', text):
        raise PortalError('invalid_meter_reading')
    return int(text)


async def submit_gas_reading(client, account_key, reading, *, dry_run=True, confirm=False, reserve=None, record=None):
    reading = reading_value(reading)
    if not dry_run and confirm is not True:
        raise PortalError('confirmation_required')
    async with client.lock:
        client.refreshed = False
        listing = await client._read('/api/accounts/')
        content = listing.get('content') if isinstance(listing, dict) else None
        if not isinstance(content, list) or listing.get('totalElements',len(content)) > len(content):
            raise PortalError('invalid_response')
        matches = [x['accountId'] for x in content if isinstance(x, dict) and isinstance(x.get('accountId'),str)
            and hashlib.sha256(x['accountId'].encode()).hexdigest() == account_key]
        if len(matches) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]+',matches[0]):
            raise PortalError('gas_account_not_found')
        ident = matches[0]
        details = await client._read('/api/accounts/'+ident)
        account = details.get('account',{}) if isinstance(details,dict) else {}
        if account.get('accountId') != ident or account.get('serviceType') != 'GS':
            raise PortalError('not_a_gas_account')
        meter = await client._read('/api/meters/v1/config',{'accountId':ident})
        if not isinstance(meter,dict) or meter.get('serviceType') != 'GS':
            raise PortalError('invalid_meter_config')
        previous = normalize_gas(None,meter,ident)
        old = previous['gas_last_actual_reading']
        digits = meter.get('preDecimalDigits')
        if not isinstance(digits,str) or not digits.isdigit() or not 1 <= int(digits) <= 9:
            raise PortalError('invalid_meter_config')
        if reading >= 10**int(digits):
            raise PortalError('too_many_digits')
        if old is None or reading < old:
            raise PortalError('reading_below_last_actual_or_missing')
        result = {'dry_run':dry_run,'submitted':False,'reading':reading,'previous_actual_reading':old,
                  'previous_actual_read_date':previous['gas_last_actual_read_date'],
                  'eligible':meter.get('eligible') is True,'preferred_reading_time':meter.get('goodTime') is True,
                  'meter_digits':int(digits)}
        if dry_run:
            return {**result,'status':'preview_only'}
        if meter.get('eligible') is not True:
            raise PortalError('supplier_not_accepting_readings')
        if reading == old:
            return {**result,'status':'already_recorded'}
        # Refresh only before sending. Never replay a submitted POST after any failure.
        if client._expires_soon():
            client.refreshed = False
            await client._refresh()
        if reserve:
            await reserve(reading)
        headers={'Authorization':'Bearer '+client.session['accessToken'],'AnonymousId':client.session['anonymousId'],
                 'Accept':'application/json','Origin':BASE,'Referer':BASE+'/sign-in'}
        try:
            async with client.http.request('POST',BASE+'/api/meters/v1/read',headers=headers,
                    json={'accountId':ident,'registers':[{'registerType':'Gas Meter','readValue':reading}]},
                    allow_redirects=False,timeout=aiohttp.ClientTimeout(total=30)) as response:
                status=response.status
                if status not in (200,201):
                    if status in (400,401,403,404,409,422,429):
                        if record:await record(reading,'rejected')
                        raise SubmissionRejected('supplier_rejected_reading')
                    raise PortalError('submission_outcome_unknown')
        except (aiohttp.ClientError,TimeoutError):
            raise PortalError('submission_outcome_unknown') from None
        # The portal UI also treats HTTP 200/201 as acceptance, not as a new bill.
        if record:await record(reading,'accepted')
        return {**result,'submitted':True,'status':'accepted','supplier_http_status':status}


class SubmissionGuard:
    """Store an attempt BEFORE writing; ambiguous results cannot be blindly replayed."""
    def __init__(self, store):
        self.store=store
        self.records=None

    async def reserve(self, key, reading):
        if self.records is None:self.records=await self.store.async_load() or {}
        old=self.records.get(key,{})
        if old.get('reading')==reading and old.get('status') in ('pending','accepted'):
            raise PortalError('reading_already_sent_or_uncertain')
        if time.time()-old.get('attempted_at',0)<60:
            raise PortalError('submission_cooldown')
        self.records[key]={'reading':reading,'attempted_at':time.time(),'status':'pending'}
        await self.store.async_save(self.records)

    async def record(self, key, reading, status):
        if self.records is None:self.records=await self.store.async_load() or {}
        self.records[key]={**self.records.get(key,{}),'reading':reading,'status':status}
        await self.store.async_save(self.records)
