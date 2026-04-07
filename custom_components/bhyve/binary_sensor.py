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
    # Callable that takes device_data and returns bool
    value_fn: Any = None
    # Callable that takes device_data and returns attributes
    attributes_fn: Any = None


BINARY_SENSOR_TYPES: tuple[BHyveBinarySensorEntityDescription, ...] = (
    BHyveBinarySensorEntityDescription(
        key="flood",
        translation_key="flood",
        name="flood sensor",
        device_class=BinarySensorDeviceClass.MOISTURE,
        unique_id_suffix="water",
        value_fn=lambda data: (
            data.get("status", {}).get("flood_alarm_status") == "alarm"
        ),
        attributes_fn=lambda data: {
            "location": data.get("location_name"),
            "shutoff": data.get("auto_shutoff"),
            "rssi": data.get("status", {}).get("rssi"),
        },
    ),
    BHyveBinarySensorEntityDescription(
        key="temperature_alert",
        translation_key="temperature_alert",
        name="temperature alert",
        device_class=BinarySensorDeviceClass.HEAT,
        unique_id_suffix="tempalert",
        value_fn=lambda data: (
            "alarm" in data.get("status", {}).get("temp_alarm_status", "")
        ),
        attributes_fn=lambda data: data.get("temp_alarm_thresholds", {}),
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
        super().__init__(coordinator, device)
        self._attr_unique_id = (
            f"{self._mac_address}:{self._device_id}:{description.unique_id_suffix}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.device_data)
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.entity_description.attributes_fn:
            return self.entity_description.attributes_fn(self.device_data)
        return {}
