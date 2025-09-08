"""Support for Orbit BHyve sensors."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor.const import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEVICE_FLOOD,
    DEVICE_SPRINKLER,
    DOMAIN,
)
from .coordinator import BHyveUpdateCoordinator
from .entities import BHyveDeviceEntity
from .pybhyve.typings import BHyveDevice, BHyveZone
from .util import filter_configured_devices, orbit_time_to_local_time

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

SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the BHyve sensor platform from a config entry."""
    coordinator: BHyveUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []
    devices = filter_configured_devices(entry, coordinator.data.devices)

    for device in devices:
        device_name = device.get("name")
        if device.get("type") == DEVICE_SPRINKLER:
            sensors.append(
                BHyveStateSensor(
                    coordinator=coordinator,
                    entity_description=BHyveSensorDescription(
                        key="state",
                        name=f"{device_name} state",
                        icon="mdi:information",
                        entity_category=EntityCategory.DIAGNOSTIC,
                    ),
                    device=device,
                )
            )
            all_zones: list[BHyveZone] = device.get("zones")
            for zone in all_zones:
                # if the zone doesn't have a name, set it to the device's name if
                # there is only one (eg a hose timer)
                zone_name = zone.get("name", None)
                if zone_name is None:
                    zone_name = device_name if len(all_zones) == 1 else "Unnamed Zone"
                sensors.append(
                    BHyveZoneHistorySensor(
                        coordinator=coordinator,
                        entity_description=BHyveSensorDescription(
                            key="history",
                            name=f"{zone_name} zone history",
                            device_class=SensorDeviceClass.TIMESTAMP,
                            entity_category=EntityCategory.DIAGNOSTIC,
                            icon="mdi:history",
                        ),
                        device=device,
                        zone=zone,
                    )
                )

        if device.get("type") == DEVICE_FLOOD:
            sensors.append(
                BHyveTemperatureSensor(
                    coordinator=coordinator,
                    entity_description=BHyveSensorDescription(
                        key="temperature",
                        name=f"{device_name} temperature",
                        device_class=SensorDeviceClass.TEMPERATURE,
                    ),
                    device=device,
                )
            )

        if device.get("battery", None) is not None:
            sensors.append(
                BHyveBatterySensor(
                    coordinator=coordinator,
                    entity_description=BHyveSensorDescription(
                        key="battery",
                        name=f"{device.get("name")} battery",
                        device_class=SensorDeviceClass.BATTERY,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        state_class=SensorStateClass.MEASUREMENT,
                    ),
                    device=device,
                )
            )

    async_add_entities(sensors)


@dataclass(frozen=True, kw_only=True)
class BHyveSensorDescription(SensorEntityDescription):
    """Describes sensor entities."""


class BHyveSensorEntity(BHyveDeviceEntity, SensorEntity):
    """Define a BHyve sensor."""


class BHyveBatterySensor(BHyveSensorEntity):
    """Define a BHyve battery sensor."""

    _state: int | None = None
    _attr_native_unit_of_measurement: str = PERCENTAGE

    def _update_attrs(self, device: BHyveDevice) -> None:
        battery = device.get("battery")
        self._attr_native_value = (
            self.parse_battery_level(battery) if battery is not None else None
        )
        super()._update_attrs(device)

    """
    # def _should_handle_event(self, event_name: str, _data: dict) -> bool:
    #     return event_name in [EVENT_BATTERY_STATUS, EVENT_CHANGE_MODE]

    # def _on_ws_data(self, data: dict) -> None:
    #     # {'event': 'battery_status', 'mv': 3311, 'charging': false ... }
    #     #
    #     event: str = data.get("event", "")
    #     if event in (EVENT_BATTERY_STATUS):
    #         battery_level = self.parse_battery_level(data)

    #         self._state = battery_level
    #         self._attrs[ATTR_BATTERY_LEVEL] = battery_level
    """

    @staticmethod
    def parse_battery_level(battery_data: dict) -> float | None:
        """
        Parses the battery level data and returns the battery level as a percentage.

        If the 'percent' attribute is present in the battery data, it is used as the battery level.
        Otherwise, if the 'mv' attribute is present, the battery level is calculated as a percentage
        based on the millivolts, assuming that 2x1.5V AA batteries are used. Note that AA batteries can
        range from 1.2V to 1.7V depending on their chemistry, so the calculation may not be accurate
        for all types of batteries. YMMV

        Args:
        battery_data (dict): A dictionary containing the battery data.

        Returns:
        float: The battery level as a percentage.

        """  # noqa: D401, E501
        if not isinstance(battery_data, dict):
            _LOGGER.warning("Unexpected battery data, returning 0: %s", battery_data)
            return 0

        if "percent" in battery_data:
            return float(battery_data.get("percent", 0))

        if "mv" in battery_data:
            return min(battery_data.get("mv", 0) / 3000 * 100, 100)

        return None


class BHyveZoneHistorySensor(BHyveSensorEntity):
    """Define a BHyve sensor."""

    def __init__(
        self,
        coordinator: BHyveUpdateCoordinator,
        entity_description: BHyveSensorDescription,
        device: BHyveDevice,
        zone: BHyveZone,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator, entity_description=entity_description, device=device
        )
        self._history = None
        self._zone = zone
        self._zone_id = zone.get("station")

    def _update_attrs(self, device: BHyveDevice) -> None:
        """Return the state of the entity."""
        history = self.coordinator.data.get_history(device.get("id")) or []

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

                value = orbit_time_to_local_time(latest_irrigation.get("start_time"))
                if value:
                    self._attr_native_value = value.isoformat()

                    self._attr_extra_state_attributes[ATTR_BUDGET] = (
                        latest_irrigation.get(ATTR_BUDGET)
                    )
                    self._attr_extra_state_attributes[ATTR_PROGRAM] = (
                        latest_irrigation.get(ATTR_PROGRAM)
                    )
                    self._attr_extra_state_attributes[ATTR_PROGRAM_NAME] = (
                        latest_irrigation.get(ATTR_PROGRAM_NAME)
                    )
                    self._attr_extra_state_attributes[ATTR_RUN_TIME] = (
                        latest_irrigation.get(ATTR_RUN_TIME)
                    )
                    self._attr_extra_state_attributes[ATTR_STATUS] = (
                        latest_irrigation.get(ATTR_STATUS)
                    )
                    self._attr_extra_state_attributes[ATTR_CONSUMPTION_GALLONS] = (
                        gallons
                    )
                    self._attr_extra_state_attributes[ATTR_CONSUMPTION_LITRES] = litres
                    self._attr_extra_state_attributes[ATTR_START_TIME] = (
                        latest_irrigation.get(ATTR_START_TIME)
                    )

                break

    """
    # def _should_handle_event(self, event_name: str, _data: dict) -> bool:
    #     return event_name in [EVENT_DEVICE_IDLE]

    # async def async_update(self) -> None:
    #     force_update = bool(list(self._ws_unprocessed_events))
    #     self._ws_unprocessed_events[:] = []  # We don't care about these

    #     try:


    #     except BHyveError as err:
    #         _LOGGER.warning("Unable to retreive data for %s: %s", self._name, err)
    """


class BHyveStateSensor(BHyveSensorEntity):
    """Define a BHyve sensor."""

    def _update_attrs(self, device: BHyveDevice) -> None:
        """Return the state of the entity."""
        self._attr_native_value = device.get("status", {}).get(
            "run_mode", "unavailable"
        )
        super()._update_attrs(device)

    """
    # def _on_ws_data(self, data: dict) -> None:
    #     #
    #     # {'event': 'change_mode', 'mode': 'auto', 'device_id': 'id', 'timestamp': '2020-01-09T20:30:00.000Z'}  # noqa: E501, ERA001
    #     #
    #     event = data.get("event")
    #     if event == EVENT_CHANGE_MODE:
    #         self._state = data.get("mode", "unavailable")

    # def _should_handle_event(self, event_name: str, _data: dict) -> bool:
    #     return event_name in [EVENT_CHANGE_MODE]
    """  # noqa: E501


class BHyveTemperatureSensor(BHyveSensorEntity):
    """Define a BHyve sensor."""

    _attr_native_value: str | None
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _state_class = SensorStateClass.MEASUREMENT

    def _update_attrs(self, device: BHyveDevice) -> None:
        status = device.get("status", {})
        self._attr_native_value = status.get("temp_f")
        self._attr_extra_state_attributes["location"] = self.device.get("location_name")
        self._attr_extra_state_attributes["rssi"] = status.get("rssi")
        self._attr_extra_state_attributes["temperature_alarm"] = status.get(
            "temp_alarm_status"
        )
        super()._update_attrs(device)

    """
    # def _on_ws_data(self, data: dict) -> None:
    #     #
    #     # {"last_flood_alarm_at":"2021-08-29T16:32:35.585Z","rssi":-60,"onboard_complete":true,"temp_f":75.2,"provisioned":true,"phy":"le_1m_1000","event":"fs_status_update","temp_alarm_status":"ok","status_updated_at":"2021-08-29T16:33:17.089Z","identify_enabled":false,"device_id":"612ad9134f0c6c9c9faddbba","timestamp":"2021-08-29T16:33:17.089Z","flood_alarm_status":"ok","last_temp_alarm_at":null}  # noqa: E501, ERA001
    #     #
    #     _LOGGER.info("Received program data update %s", data)
    #     event = data.get("event")
    #     if event == EVENT_FS_ALARM:
    #         self._state = data.get("temp_f", "unavailable")
    #         self._attrs["rssi"] = data.get("rssi")
    #         self._attrs["temperature_alarm"] = data.get("temp_alarm_status")

    # def _should_handle_event(self, event_name: str, _data: dict) -> bool:
    #     return event_name in [EVENT_FS_ALARM]
    """
