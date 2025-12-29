"""Support for Orbit BHyve sensors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
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


@dataclass(frozen=True, kw_only=True)
class BHyveBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes BHyve binary sensor entity."""

    unique_id_suffix: str


BINARY_SENSOR_TYPES: tuple[BHyveBinarySensorEntityDescription, ...] = (
    BHyveBinarySensorEntityDescription(
        key="flood",
        translation_key="flood",
        name="flood sensor",
        device_class=BinarySensorDeviceClass.MOISTURE,
        icon="mdi:water",
        unique_id_suffix="water",
    ),
    BHyveBinarySensorEntityDescription(
        key="temperature_alert",
        translation_key="temperature_alert",
        name="temperature alert",
        device_class=BinarySensorDeviceClass.HEAT,
        icon="mdi:alert",
        unique_id_suffix="tempalert",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the BHyve binary sensor platform from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]

    entities = [
        BHyveBinarySensor(coordinator, device, description)
        for device in devices
        if device.get("type") == DEVICE_FLOOD
        for description in BINARY_SENSOR_TYPES
    ]

    async_add_entities(entities)


class BHyveBinarySensor(BHyveCoordinatorEntity, BinarySensorEntity):
    """Define a BHyve binary sensor."""

    entity_description: BHyveBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: BHyveDataUpdateCoordinator,
        device: BHyveDevice,
        description: BHyveBinarySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        super().__init__(
            coordinator,
            device,
            f"{device.get('name')} {description.name}",
            description.icon.replace("mdi:", "") if description.icon else "alert",
        )
        self._attr_unique_id = (
            f"{self._mac_address}:{self._device_id}:{description.unique_id_suffix}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        status = self.device_data.get("status", {})

        if self.entity_description.key == "flood":
            return status.get("flood_alarm_status") == "alarm"
        if self.entity_description.key == "temperature_alert":
            return "alarm" in status.get("temp_alarm_status", "")

        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.entity_description.key == "flood":
            device = self.device_data
            status = device.get("status", {})
            return {
                "location": device.get("location_name"),
                "shutoff": device.get("auto_shutoff"),
                "rssi": status.get("rssi"),
            }
        if self.entity_description.key == "temperature_alert":
            return self.device_data.get("temp_alarm_thresholds", {})

        return {}
