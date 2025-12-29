"""Support for Orbit BHyve sensors."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.helpers.icon import icon_for_battery_level

from . import BHyveCoordinatorEntity
from .const import (
    DEVICE_FLOOD,
    DEVICE_SPRINKLER,
    DOMAIN,
)
from .util import orbit_time_to_local_time

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import BHyveDataUpdateCoordinator
    from .pybhyve.typings import BHyveDevice

_LOGGER = logging.getLogger(__name__)

ATTR_BUDGET = "budget"
ATTR_CONSUMPTION_GALLONS = "consumption_gallons"
ATTR_CONSUMPTION_LITRES = "consumption_litres"
ATTR_IRRIGATION = "irrigation"
ATTR_PROGRAM = "program"
ATTR_PROGRAM_NAME = "program_name"
ATTR_RUN_TIME = "run_time"
ATTR_START_TIME = "start_time"
ATTR_STATUS = "status"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the BHyve sensor platform from a config entry."""
    coordinator: BHyveDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    devices: list[BHyveDevice] = hass.data[DOMAIN][entry.entry_id]["devices"]

    sensors = []

    for device in devices:
        if device.get("type") == DEVICE_SPRINKLER:
            sensors.append(BHyveStateSensor(coordinator, device))
            all_zones = device.get("zones", [])
            for zone in all_zones:
                # if the zone doesn't have a name, set it to the device's name if
                # there is only one (eg a hose timer)
                zone_name: str = zone.get("name") or (
                    device.get("name", "Unnamed Zone")
                    if len(all_zones) == 1
                    else "Unnamed Zone"
                )
                sensors.append(
                    BHyveZoneHistorySensor(coordinator, device, zone, zone_name)
                )

            if device.get("battery", None) is not None:
                sensors.append(BHyveBatterySensor(coordinator, device))
        if device.get("type") == DEVICE_FLOOD:
            sensors.append(BHyveTemperatureSensor(coordinator, device))
            sensors.append(BHyveBatterySensor(coordinator, device))

    async_add_entities(sensors)


class BHyveBatterySensor(BHyveCoordinatorEntity, SensorEntity):
    """Define a BHyve battery sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: BHyveDataUpdateCoordinator, device: BHyveDevice
    ) -> None:
        """Initialize the sensor."""
        name = f"{device.get('name')} battery level"
        _LOGGER.info("Creating battery sensor: %s", name)
        super().__init__(
            coordinator, device, name, "battery", SensorDeviceClass.BATTERY
        )

    @property
    def native_value(self) -> int | None:
        """Return battery level from coordinator."""
        battery = self.device_data.get("battery")
        if battery:
            return self.parse_battery_level(battery)
        return None

    @property
    def icon(self) -> str | None:
        """Icon to use in the frontend, if any."""
        battery_level = self.native_value
        if battery_level is not None:
            return icon_for_battery_level(
                battery_level=int(battery_level), charging=False
            )
        return self._attr_icon

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device state attributes."""
        battery_level = self.native_value
        if battery_level is not None:
            return {ATTR_BATTERY_LEVEL: battery_level}
        return {}

    @property
    def unique_id(self) -> str:
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:battery"

    @staticmethod
    def parse_battery_level(battery_data: dict) -> int:
        """
        Parses the battery level data and returns the battery level as a percentage.

        If the 'percent' attribute is present in the battery data, it is used as the battery level.
        Otherwise, if the 'mv' attribute is present, the battery level is calculated as a percentage
        based on the millivolts, assuming that 2x1.5V AA batteries are used. Note that AA batteries can
        range from 1.2V to 1.7V depending on their chemistry, so the calculation may not be accurate
        for all types of batteries. YMMV

        Args:
        ----
        battery_data (dict): A dictionary containing the battery data.

        Returns:
        -------
        float: The battery level as a percentage.

        """  # noqa: D401, E501
        if not isinstance(battery_data, dict):
            _LOGGER.warning("Unexpected battery data, returning 0: %s", battery_data)
            return 0

        battery_level = battery_data.get("percent", 0)
        if "mv" in battery_data and "percent" not in battery_data:
            battery_level = min(battery_data.get("mv", 0) / 3000 * 100, 100)
        return int(battery_level)


class BHyveZoneHistorySensor(BHyveCoordinatorEntity, SensorEntity):
    """Define a BHyve zone history sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: BHyveDataUpdateCoordinator,
        device: BHyveDevice,
        zone: dict,
        zone_name: str,
    ) -> None:
        """Initialize the sensor."""
        self._zone = zone
        self._zone_id = zone.get("station")

        name = f"{zone_name} zone history"
        _LOGGER.info("Creating history sensor: %s", name)

        super().__init__(coordinator, device, name, "history")

    @property
    def native_value(self) -> str | None:
        """Return the state of the entity."""
        history = self._get_device_history()
        if not history:
            return None

        for history_item in history:
            zone_irrigation = list(
                filter(
                    lambda i: i.get("station") == self._zone_id,
                    history_item.get(ATTR_IRRIGATION, []),
                )
            )
            if zone_irrigation:
                # This is a bit crude - assumes the list is ordered by time.
                latest_irrigation = zone_irrigation[-1]
                start_time = latest_irrigation.get("start_time")
                if start_time:
                    local_time = orbit_time_to_local_time(start_time)
                    if local_time:
                        return local_time.isoformat()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device state attributes."""
        history = self._get_device_history()
        if not history:
            return {}

        for history_item in history:
            zone_irrigation = list(
                filter(
                    lambda i: i.get("station") == self._zone_id,
                    history_item.get(ATTR_IRRIGATION, []),
                )
            )
            if zone_irrigation:
                # This is a bit crude - assumes the list is ordered by time.
                latest_irrigation = zone_irrigation[-1]

                gallons = latest_irrigation.get("water_volume_gal")
                litres = round(gallons * 3.785, 2) if gallons else None

                return {
                    ATTR_BUDGET: latest_irrigation.get(ATTR_BUDGET),
                    ATTR_PROGRAM: latest_irrigation.get(ATTR_PROGRAM),
                    ATTR_PROGRAM_NAME: latest_irrigation.get(ATTR_PROGRAM_NAME),
                    ATTR_RUN_TIME: latest_irrigation.get(ATTR_RUN_TIME),
                    ATTR_STATUS: latest_irrigation.get(ATTR_STATUS),
                    ATTR_CONSUMPTION_GALLONS: gallons,
                    ATTR_CONSUMPTION_LITRES: litres,
                    ATTR_START_TIME: latest_irrigation.get(ATTR_START_TIME),
                }
        return {}

    def _get_device_history(self) -> list:
        """Get device history from coordinator."""
        return (
            self.coordinator.data.get("devices", {})
            .get(self._device_id, {})
            .get("history", [])
        )

    @property
    def unique_id(self) -> str:
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:{self._zone_id}:history"


class BHyveStateSensor(BHyveCoordinatorEntity, SensorEntity):
    """Define a BHyve state sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: BHyveDataUpdateCoordinator, device: BHyveDevice
    ) -> None:
        """Initialize the sensor."""
        name = f"{device.get('name')} state"
        _LOGGER.info("Creating state sensor: %s", name)
        super().__init__(coordinator, device, name, "information")

    @property
    def native_value(self) -> str:
        """Return the state of the entity."""
        status = self.device_data.get("status", {})
        return status.get("run_mode", "unavailable")

    @property
    def unique_id(self) -> str:
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:state"


class BHyveTemperatureSensor(BHyveCoordinatorEntity, SensorEntity):
    """Define a BHyve temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self, coordinator: BHyveDataUpdateCoordinator, device: BHyveDevice
    ) -> None:
        """Initialize the sensor."""
        name = f"{device.get('name')} temperature sensor"
        _LOGGER.info("Creating temperature sensor: %s", name)
        super().__init__(
            coordinator, device, name, "thermometer", SensorDeviceClass.TEMPERATURE
        )

    @property
    def native_value(self) -> float | None:
        """Return temperature value from coordinator."""
        status = self.device_data.get("status", {})
        temp = status.get("temp_f")
        return float(temp) if temp is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device state attributes."""
        device = self.device_data
        status = device.get("status", {})
        return {
            "location": device.get("location_name"),
            "rssi": status.get("rssi"),
            "temperature_alarm": status.get("temp_alarm_status"),
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available and self.native_value is not None

    @property
    def unique_id(self) -> str:
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:temp"
