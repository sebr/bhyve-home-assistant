"""Support for Orbit BHyve sensors."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from . import BHyveCoordinatorEntity
from .const import DEVICE_FLOOD, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import BHyveDataUpdateCoordinator
    from .pybhyve.typings import BHyveDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the BHyve binary sensor platform from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]

    entities = []

    for device in devices:
        if device.get("type") == DEVICE_FLOOD:
            entities.append(BHyveFloodSensor(coordinator, device))
            entities.append(BHyveTemperatureBinarySensor(coordinator, device))

    async_add_entities(entities)


class BHyveFloodSensor(BHyveCoordinatorEntity, BinarySensorEntity):
    """Define a BHyve flood sensor."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(
        self, coordinator: BHyveDataUpdateCoordinator, device: BHyveDevice
    ) -> None:
        """Initialize the sensor."""
        name = f"{device.get('name')} flood sensor"
        _LOGGER.info("Creating flood sensor: %s", name)
        super().__init__(coordinator, device, name, "water")
        self._attr_unique_id = f"{self._mac_address}:{self._device_id}:water"

    @property
    def is_on(self) -> bool:
        """Return true if flood detected."""
        status = self.device_data.get("status", {})
        return status.get("flood_alarm_status") == "alarm"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        device = self.device_data
        status = device.get("status", {})
        return {
            "location": device.get("location_name"),
            "shutoff": device.get("auto_shutoff"),
            "rssi": status.get("rssi"),
        }


class BHyveTemperatureBinarySensor(BHyveCoordinatorEntity, BinarySensorEntity):
    """Define a BHyve temperature sensor."""

    def __init__(
        self, coordinator: BHyveDataUpdateCoordinator, device: BHyveDevice
    ) -> None:
        """Initialize the sensor."""
        name = f"{device.get('name')} temperature alert"
        super().__init__(coordinator, device, name, "alert")
        self._attr_unique_id = f"{self._mac_address}:{self._device_id}:tempalert"

    @property
    def is_on(self) -> bool:
        """Return true if temperature alarm detected."""
        status = self.device_data.get("status", {})
        return "alarm" in status.get("temp_alarm_status", "")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return self.device_data.get("temp_alarm_thresholds", {})
