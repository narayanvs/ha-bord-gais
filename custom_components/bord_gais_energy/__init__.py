"""Bord Gáis supplier account data, independent of ESB meter statistics."""
from homeassistant.const import Platform
from .coordinator import BGECoordinator
from .const import DOMAIN, DEFAULT_POLL_HOURS
from homeassistant.helpers import config_validation as cv
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR, Platform.BUTTON]

async def async_setup(hass, config):
    from .services import register_services
    register_services(hass)
    return True

async def async_setup_entry(hass, entry):
    coordinator = BGECoordinator(hass, entry)
    await coordinator.async_initialize()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True

async def async_update_options(hass, entry):
    coordinator = entry.runtime_data
    if (coordinator.poll_hours != entry.options.get('poll_hours', DEFAULT_POLL_HOURS)
            or entry.data.get('session') != coordinator.client.session):
        # Token rotation persists the same session held by the live client and
        # must not reload it. A browser reauthentication replaces that session.
        hass.config_entries.async_schedule_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def async_remove_entry(hass, entry):
    from homeassistant.helpers.storage import Store
    from .const import DOMAIN
    await Store(hass, 1, DOMAIN + '.' + entry.entry_id).async_remove()
    await Store(hass, 1, DOMAIN + '.gas_submissions.' + entry.entry_id).async_remove()
