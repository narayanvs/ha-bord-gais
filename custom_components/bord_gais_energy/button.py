"""Rate-limited account refresh."""
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BGERefresh(entry.runtime_data, entry.entry_id)])

class BGERefresh(CoordinatorEntity, ButtonEntity):
    _attr_name = 'Bord Gáis Energy refresh'
    _attr_icon = 'mdi:refresh'
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = entry_id + '_refresh'

    async def async_press(self):
        await self.coordinator.async_request_refresh()
