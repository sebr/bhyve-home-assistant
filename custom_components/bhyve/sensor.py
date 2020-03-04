"""Support for Orbit BHyve sensors."""
import logging

from homeassistant.const import ATTR_BATTERY_LEVEL, DEVICE_CLASS_BATTERY
from homeassistant.helpers.icon import icon_for_battery_level

from . import BHyveEntity
from .const import DOMAIN
from .pybhyve.errors import BHyveError

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    """Set up BHyve sensors based on a config entry."""
    bhyve = hass.data[DOMAIN]

    sensors = []
    devices = await bhyve.devices
    for device in devices:
        if device.get("type") == "sprinkler_timer":
            device_name = device.get("name")
            name = "Battery level {}".format(device_name)
            _LOGGER.info("Creating sensor: %s", name)
            sensors.append(
                BHyveBatterySensor(
                    hass, bhyve, device, name, "battery", "%", DEVICE_CLASS_BATTERY,
                )
            )
            for zone in device.get("zones"):
                name = "{0} Zone State".format(zone.get("name", "Unknown"))
                _LOGGER.info("Creating sensor: %s", name)
                sensors.append(
                    BHyveStateSensor(hass, bhyve, device, name, "information",)
                )

    async_add_entities(sensors, True)


class BHyveBatterySensor(BHyveEntity):
    """Define a BHyve sensor."""

    def __init__(self, hass, bhyve, device, name, icon, unit, device_class):
        """Initialize the sensor."""
        super().__init__(hass, bhyve, device, name, icon, device_class)

        self._unit = unit

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

    async def async_update(self):
        """Retrieve latest state."""
        self._ws_unprocessed_events[:] = []  # We don't care about these

        await self._refetch_device()


class BHyveStateSensor(BHyveEntity):
    """Define a BHyve sensor."""

    def __init__(self, hass, bhyve, device, name, icon):
        """Initialize the sensor."""
        super().__init__(hass, bhyve, device, name, icon)

    def _setup(self, device):
        self._attrs = {}
        self._state = device.get("status", {}).get("run_mode")
        self._available = device.get("is_connected", False)

    @property
    def state(self):
        """Return the state of the entity"""
        return self._state

    def _on_ws_data(self, data):
        """
            {'event': 'change_mode', 'mode': 'auto', 'device_id': 'id', 'timestamp': '2020-01-09T20:30:00.000Z'}
        """
        event = data.get("event")
        if event == "change_mode":
            self._state = data.get("mode")
