"""Support for Orbit BHyve sensors."""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_FLOOD, DOMAIN
from .coordinator import BHyveUpdateCoordinator
from .entities import BHyveDeviceEntity
from .pybhyve.typings import BHyveDevice
from .util import filter_configured_devices

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the BHyve binary sensor platform from a config entry."""
    coordinator: BHyveUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []
    devices = filter_configured_devices(entry, coordinator.data.devices)

    for device in devices:
        if device.get("type") == DEVICE_FLOOD:
            sensors.append(
                BHyveFloodSensor(
                    coordinator,
                    BinarySensorEntityDescription(
                        key="water",
                        name=f"{device.get('name')} flood sensor",
                        device_class=BinarySensorDeviceClass.MOISTURE,
                    ),
                    device,
                )
            )
            sensors.append(
                BHyveFloodSensor(
                    coordinator,
                    BinarySensorEntityDescription(
                        key="tempalert",
                        name=f"{device.get('name')} temperature alert",
                    ),
                    device,
                )
            )

    async_add_entities(sensors)


class BHyveBinarySensorEntity(BHyveDeviceEntity, BinarySensorEntity):
    """Define a BHyve sensor."""

    def __init__(
        self,
        coordinator: BHyveUpdateCoordinator,
        entity_description: BinarySensorEntityDescription,
        device: BHyveDevice,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            entity_description=entity_description,
            device=device,
        )


class BHyveFloodSensor(BHyveBinarySensorEntity):
    """Define a BHyve flood sensor."""

    def __init__(
        self,
        coordinator: BHyveUpdateCoordinator,
        entity_description: BinarySensorEntityDescription,
        device: BHyveDevice,
    ) -> None:
        """Initialize the sensor."""
        _LOGGER.info("Creating flood sensor: %s", entity_description.name)
        super().__init__(
            coordinator=coordinator,
            entity_description=entity_description,
            device=device,
        )

    def _update_attrs(self, device: BHyveDevice) -> None:
        status = device.get("status", {})
        self._state = status.get("flood_alarm_status") == "alarm"
        self._attr_extra_state_attributes["location"] = device.get("location_name")
        self._attr_extra_state_attributes["shutoff"] = device.get("auto_shutoff")
        self._attr_extra_state_attributes["rssi"] = status.get("rssi")
        super()._update_attrs(device)

    """
    # def _on_ws_data(self, data: dict) -> None:
    #     # {"last_flood_alarm_at":"2021-08-29T16:32:35.585Z","rssi":-60,"onboard_complete":true,"temp_f":75.2,"provisioned":true,"phy":"le_1m_1000","event":"fs_status_update","temp_alarm_status":"ok","status_updated_at":"2021-08-29T16:33:17.089Z","identify_enabled":false,"device_id":"612ad9134f0c6c9c9faddbba","timestamp":"2021-08-29T16:33:17.089Z","flood_alarm_status":"ok","last_temp_alarm_at":null}
    #     _LOGGER.info("Received program data update %s", data)
    #     event = data.get("event")
    #     if event == EVENT_FS_ALARM:
    #         self._state = self._parse_status(data)
    #         self._attrs["rssi"] = data.get("rssi")

    # def _should_handle_event(self, event_name: str, _data: dict) -> bool:
    #     return event_name in [EVENT_FS_ALARM]
    """  # noqa: E501


class BHyveTemperatureBinarySensor(BHyveBinarySensorEntity):
    """Define a BHyve temperature sensor."""

    def __init__(
        self,
        coordinator: BHyveUpdateCoordinator,
        entity_description: BinarySensorEntityDescription,
        device: BHyveDevice,
    ) -> None:
        """Initialize the sensor."""
        _LOGGER.info("Creating temperature sensor: %s", entity_description.name)
        super().__init__(
            coordinator=coordinator,
            entity_description=entity_description,
            device=device,
        )

    def _update_attrs(self, device: BHyveDevice) -> None:
        self._state = "alarm" in device.get("status", {}).get("temp_alarm_status", [])
        self._attr_extra_state_attributes = device.get("temp_alarm_thresholds", {})
        super()._update_attrs(device)

    """
    def _on_ws_data(self, data: dict) -> None:
        _LOGGER.info("Received program data update %s", data)
        event = data.get("event")
        if event == EVENT_FS_ALARM:
            self._state = self._parse_status(data)

    def _should_handle_event(self, event_name: str, _data: dict) -> bool:
        return event_name in [EVENT_FS_ALARM]
    """
