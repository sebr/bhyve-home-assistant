"""Support for Orbit BHyve sensors."""
import logging

from homeassistant.const import ATTR_BATTERY_LEVEL, DEVICE_CLASS_BATTERY
from homeassistant.helpers.icon import icon_for_battery_level

from . import BHyveDeviceEntity
from .const import (
    DATA_BHYVE,
    DEVICE_SPRINKLER,
    EVENT_CHANGE_MODE,
    EVENT_DEVICE_IDLE,
)
from .pybhyve.errors import BHyveError
from .util import orbit_time_to_local_time

_LOGGER = logging.getLogger(__name__)

ATTR_BUDGET = "budget"
ATTR_IRRIGATION = "irrigation"
ATTR_PROGRAM = "program"
ATTR_PROGRAM_NAME = "program_name"
ATTR_RUN_TIME = "run_time"
ATTR_STATUS = "status"
ATTR_CONSUMPTION_GALLONS = "consumption_gallons"
ATTR_CONSUMPTION_LITRES = "consumption_litres"


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    """Set up BHyve sensors based on a config entry."""
    bhyve = hass.data[DATA_BHYVE]

    sensors = []
    devices = await bhyve.devices
    for device in devices:
        if device.get("type") == DEVICE_SPRINKLER:
            sensors.append(BHyveBatterySensor(hass, bhyve, device))
            sensors.append(BHyveStateSensor(hass, bhyve, device))
            for zone in device.get("zones"):
                sensors.append(BHyveZoneHistorySensor(hass, bhyve, device, zone))

    async_add_entities(sensors, True)


class BHyveBatterySensor(BHyveDeviceEntity):
    """Define a BHyve sensor."""

    def __init__(self, hass, bhyve, device):
        """Initialize the sensor."""
        name = "{} battery level".format(device.get("name"))
        _LOGGER.info("Creating battery sensor: %s", name)
        super().__init__(
            hass, bhyve, device, name, "battery", DEVICE_CLASS_BATTERY,
        )

        self._unit = "%"

    def _setup(self, device):
        self._state = None
        self._attrs = {}
        self._available = device.get("is_connected", False)

        battery = device.get("battery")

        if battery is not None:
            self._state = battery["percent"]
            self._attrs[ATTR_BATTERY_LEVEL] = battery["percent"]

    @property
    def state(self):
        """Return the state of the entity"""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement for the sensor."""
        return self._unit

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        if self._device_class == DEVICE_CLASS_BATTERY and self._state is not None:
            return icon_for_battery_level(
                battery_level=int(self._state), charging=False
            )
        return self._icon

    @property
    def should_poll(self):
        """Enable polling."""
        return True

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:battery"

    def _should_handle_event(self, event_name, data):
        return event_name in [EVENT_CHANGE_MODE]

    async def async_update(self):
        """Retrieve latest state."""
        self._ws_unprocessed_events[:] = []  # We don't care about these

        await self._refetch_device()


class BHyveZoneHistorySensor(BHyveDeviceEntity):
    """Define a BHyve sensor."""

    def __init__(self, hass, bhyve, device, zone):
        """Initialize the sensor."""
        self._zone = zone
        self._zone_id = zone.get("station")

        name = "{0} zone history".format(zone.get("name", "Unknown"))
        _LOGGER.info("Creating history sensor: %s", name)

        super().__init__(
            hass, bhyve, device, name, "history",
        )

    def _setup(self, device):
        self._state = None
        self._attrs = {}
        self._available = device.get("is_connected", False)

    @property
    def state(self):
        """Return the state of the entity"""
        return self._state

    def should_poll(self):
        """Enable polling."""
        return True

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:{self._zone_id}:history"

    def _should_handle_event(self, event_name, data):
        return event_name in [EVENT_DEVICE_IDLE]

    async def async_update(self):
        """Retrieve latest state."""
        force_update = True if list(self._ws_unprocessed_events) else False
        self._ws_unprocessed_events[:] = []  # We don't care about these

        try:
            history = await self._fetch_device_history(force_update=force_update) or []
            self._history = history

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

                    self._state = orbit_time_to_local_time(
                        latest_irrigation.get("start_time")
                    )
                    self._attrs = {
                        ATTR_BUDGET: latest_irrigation.get(ATTR_BUDGET),
                        ATTR_PROGRAM: latest_irrigation.get(ATTR_PROGRAM),
                        ATTR_PROGRAM_NAME: latest_irrigation.get(ATTR_PROGRAM_NAME),
                        ATTR_RUN_TIME: latest_irrigation.get(ATTR_RUN_TIME),
                        ATTR_STATUS: latest_irrigation.get(ATTR_STATUS),
                        ATTR_CONSUMPTION_GALLONS: gallons,
                        ATTR_CONSUMPTION_LITRES: litres,
                    }
                    break

        except BHyveError as err:
            self._available = False
            raise (err)


class BHyveStateSensor(BHyveDeviceEntity):
    """Define a BHyve sensor."""

    def __init__(self, hass, bhyve, device):
        """Initialize the sensor."""
        name = "{0} state".format(device.get("name"))
        _LOGGER.info("Creating state sensor: %s", name)
        super().__init__(hass, bhyve, device, name, "information")

    def _setup(self, device):
        self._attrs = {}
        self._state = device.get("status", {}).get("run_mode")
        self._available = device.get("is_connected", False)
        _LOGGER.debug(
            f"State sensor {self._name} setup: State: {self._state} | Available: {self._available}"
        )

    @property
    def state(self):
        """Return the state of the entity"""
        return self._state

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:state"

    def _on_ws_data(self, data):
        """
            {'event': 'change_mode', 'mode': 'auto', 'device_id': 'id', 'timestamp': '2020-01-09T20:30:00.000Z'}
        """
        event = data.get("event")
        if event == EVENT_CHANGE_MODE:
            self._state = data.get("mode")

    def _should_handle_event(self, event_name, data):
        return event_name in [EVENT_CHANGE_MODE]
