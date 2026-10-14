"""Admin-only manual meter submission with preview as the default."""
import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store
from .const import DOMAIN
from .client import PortalError
from .gas_submission import reading_value,submit_gas_reading,SubmissionGuard

SERVICE='submit_gas_meter_reading'

def validate_reading(value):
    try:
        return reading_value(value)
    except PortalError:
        raise vol.Invalid('Enter whole gas meter digits, without decimals or units.') from None


def register_services(hass):
    if hass.services.has_service(DOMAIN,SERVICE):return
    guards={}
    async def handle(call):
        entity=er.async_get(hass).async_get(call.data['entity_id'])
        suffix='_gas_last_actual_reading'
        if not entity or entity.platform!=DOMAIN or not entity.unique_id.endswith(suffix):
            raise HomeAssistantError('Select this integration\'s Last actual gas meter reading sensor.')
        key=entity.unique_id[:-len(suffix)]
        entry=hass.config_entries.async_get_entry(entity.config_entry_id)
        if not entry or not getattr(entry,'runtime_data',None):
            raise HomeAssistantError('Bord Gais integration is not loaded.')
        coordinator=entry.runtime_data
        if coordinator.data.get(key,{}).get('service')!='gas':
            raise HomeAssistantError('The selected entity is not a gas account.')
        if entry.entry_id not in guards:
            guards[entry.entry_id]=SubmissionGuard(Store(hass,1,DOMAIN+'.gas_submissions.'+entry.entry_id))
        guard=guards[entry.entry_id]
        async def reserve(reading):await guard.reserve(key,reading)
        async def record(reading,status):await guard.record(key,reading,status)
        try:
            return await submit_gas_reading(coordinator.client,key,call.data['reading'],
                dry_run=call.data['dry_run'],confirm=call.data['confirm'],reserve=reserve,record=record)
        except PortalError as exc:
            safe={'confirmation_required','invalid_meter_reading','gas_account_not_found','not_a_gas_account',
                'invalid_meter_config','too_many_digits','reading_below_last_actual_or_missing',
                'supplier_not_accepting_readings','supplier_rejected_reading','submission_outcome_unknown',
                'reading_already_sent_or_uncertain','submission_cooldown','invalid_auth','rate_limited'}
            reason=str(exc) if str(exc) in safe else 'supplier_request_failed'
            raise HomeAssistantError('Gas reading action: '+reason+'. No automatic submission retry was made.') from None
    async_register_admin_service(hass,DOMAIN,SERVICE,handle,schema=vol.Schema({
        vol.Required('entity_id'):str,
        vol.Required('reading'):validate_reading,
        vol.Optional('dry_run',default=True):vol.Boolean(),
        vol.Optional('confirm',default=False):vol.Boolean(),
    }),supports_response=SupportsResponse.OPTIONAL)
