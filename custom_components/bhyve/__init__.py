"""
Support for Orbit BHyve irrigation devices.

For more details about this integration, please refer to
https://github.com/sebr/bhyve-home-assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.bhyve.pybhyve.client import BHyveClient

from .const import DOMAIN
from .coordinator import BHyveUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import BHyveConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    # Platform.SWITCH,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BHyveConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    bhyve_client = BHyveClient(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session=async_get_clientsession(hass),
    )
    coordinator = BHyveUpdateCoordinator(
        hass=hass,
        entry=entry,
        api=bhyve_client,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    entry.async_create_background_task(
        hass,
        coordinator.client_listen(),
        "websocket_task",
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: BHyveConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: BHyveConfigEntry,
) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
