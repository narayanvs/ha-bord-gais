"""Supplier account sensors; monetary balances are never energy counters."""
from datetime import date
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import EntityCategory
from .const import DOMAIN, NAME

DESCRIPTIONS = (
    SensorEntityDescription(key='supplier_balance', name='Account balance', native_unit_of_measurement='EUR', device_class=SensorDeviceClass.MONETARY, icon='mdi:wallet'),
    SensorEntityDescription(key='account_credit', name='Account credit', native_unit_of_measurement='EUR', device_class=SensorDeviceClass.MONETARY, icon='mdi:cash-check'),
    SensorEntityDescription(key='account_amount_due', name='Amount due', native_unit_of_measurement='EUR', device_class=SensorDeviceClass.MONETARY, icon='mdi:cash-clock'),
    SensorEntityDescription(key='latest_bill_charge', name='Latest bill charge', native_unit_of_measurement='EUR', device_class=SensorDeviceClass.MONETARY, icon='mdi:receipt-text'),
    SensorEntityDescription(key='latest_bill_issue_date', name='Latest bill issued', device_class=SensorDeviceClass.DATE),
    SensorEntityDescription(key='latest_bill_due_date', name='Latest bill due', device_class=SensorDeviceClass.DATE),
    SensorEntityDescription(key='next_bill_date', name='Next bill', device_class=SensorDeviceClass.DATE),
    SensorEntityDescription(key='last_success', name='Last successful update', device_class=SensorDeviceClass.TIMESTAMP, entity_category=EntityCategory.DIAGNOSTIC),
)

# Period quantities are intentionally not total_increasing energy counters.
GAS_DESCRIPTIONS = (
    SensorEntityDescription(key='gas_latest_billed_usage_kwh', name='Latest billed gas usage', native_unit_of_measurement='kWh', device_class=SensorDeviceClass.ENERGY),
    SensorEntityDescription(key='gas_bill_period_start', name='Gas bill period start', device_class=SensorDeviceClass.DATE),
    SensorEntityDescription(key='gas_bill_period_end', name='Gas bill period end', device_class=SensorDeviceClass.DATE),
    SensorEntityDescription(key='gas_latest_bill_cost', name='Gas billed period cost', native_unit_of_measurement='EUR', device_class=SensorDeviceClass.MONETARY),
    SensorEntityDescription(key='gas_latest_bill_vat', name='Gas billed period VAT', native_unit_of_measurement='EUR', device_class=SensorDeviceClass.MONETARY),
    SensorEntityDescription(key='gas_last_actual_reading', name='Last actual gas meter reading', icon='mdi:counter'),
    SensorEntityDescription(key='gas_last_actual_read_date', name='Last actual gas reading date', device_class=SensorDeviceClass.DATE),
)

ELECTRICITY_DESCRIPTIONS = (
    SensorEntityDescription(key='electricity_latest_billed_usage_kwh', name='Latest billed electricity usage', native_unit_of_measurement='kWh', device_class=SensorDeviceClass.ENERGY),
    SensorEntityDescription(key='electricity_bill_period_start', name='Electricity bill period start', device_class=SensorDeviceClass.DATE),
    SensorEntityDescription(key='electricity_bill_period_end', name='Electricity bill period end', device_class=SensorDeviceClass.DATE),
    SensorEntityDescription(key='electricity_latest_bill_cost', name='Electricity billed period cost', native_unit_of_measurement='EUR', device_class=SensorDeviceClass.MONETARY),
    SensorEntityDescription(key='electricity_latest_bill_vat', name='Electricity billed period VAT', native_unit_of_measurement='EUR', device_class=SensorDeviceClass.MONETARY),
)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(BGEAccountSensor(coordinator, key, description) for key in coordinator.data for description in (DESCRIPTIONS + GAS_DESCRIPTIONS if coordinator.data[key]['service'] == 'gas' else DESCRIPTIONS + ELECTRICITY_DESCRIPTIONS if coordinator.data[key]['service'] == 'electricity' else DESCRIPTIONS))

class BGEAccountSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, description):
        super().__init__(coordinator, context=key)
        self.key = key
        self.entity_description = description
        self._attr_unique_id = key + '_' + description.key
        service = coordinator.data[key]['service'].title()
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, key)}, name=NAME + ' ' + service, manufacturer='Bord Gáis Energy', model='Supplier account')

    @property
    def available(self):
        return super().available and self.key in self.coordinator.data

    @property
    def native_value(self):
        if self.entity_description.key == 'last_success':
            return self.coordinator.last_success
        value = self.coordinator.data.get(self.key, {}).get(self.entity_description.key)
        if value is not None and self.entity_description.device_class == SensorDeviceClass.DATE:
            try:
                return date.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return value

    @property
    def extra_state_attributes(self):
        if self.entity_description.key in ('gas_latest_billed_usage_kwh', 'electricity_latest_billed_usage_kwh'):
            data = self.coordinator.data.get(self.key, {})
            fuel = self.entity_description.key.split('_', 1)[0]
            return {'source': 'supplier_billed_periods', 'period_start': data.get(f'{fuel}_bill_period_start'),
                    'period_end': data.get(f'{fuel}_bill_period_end'), 'billed_history': data.get(f'{fuel}_usage_history', []),
                    'daily_usage_available': False}
        if self.entity_description.key == 'gas_last_actual_reading':
            return {'source': 'supplier_last_actual_meter_read', 'register_unit': 'not_provided_by_supplier_api'}
        if self.entity_description.key == 'supplier_balance':
            return {'negative_means': 'credit', 'positive_means': 'amount_due',
                    'source': 'supplier_reported', 'includes_unbilled_estimates': False,
                    'last_successful_update': self.coordinator.last_success.isoformat() if self.coordinator.last_success else None}
        if self.entity_description.key == 'latest_bill_charge':
            return {'source': 'ordinary_bill_transaction', 'combined_export_bill_charge_available': False}
        return None
