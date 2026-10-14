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

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(BGEAccountSensor(coordinator, key, description) for key in coordinator.data for description in DESCRIPTIONS)

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
        if self.entity_description.key == 'supplier_balance':
            return {'negative_means': 'credit', 'positive_means': 'amount_due',
                    'source': 'supplier_reported', 'includes_unbilled_estimates': False,
                    'last_successful_update': self.coordinator.last_success.isoformat() if self.coordinator.last_success else None}
        if self.entity_description.key == 'latest_bill_charge':
            return {'source': 'ordinary_bill_transaction', 'combined_export_bill_charge_available': False}
        return None
