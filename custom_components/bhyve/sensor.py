"""Support for Orbit BHyve sensors."""
import logging

from homeassistant.const import ATTR_BATTERY_LEVEL, DEVICE_CLASS_BATTERY
from homeassistant.helpers.icon import icon_for_battery_level

from . import BHyveEntity
from .const import DOMAIN
from .pybhyve.errors import BHyveError

_LOGGER = logging.getLogger(__name__)


def battery_callback(device):
    """Update callback for battery sensor."""
    state = None
    attrs = {}
    battery = device["battery"]

    if battery is not None:
        state = battery["percent"]
        attrs[ATTR_BATTERY_LEVEL] = battery["percent"]

    return state, attrs


SENSOR_TYPES = {
    "battery_level": {
        "name": "Battery Level",
        "icon": "battery",
        "unit": "%",
        "device_class": DEVICE_CLASS_BATTERY,
        "update_callback": battery_callback,
    }
}


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    """Set up BHyve sensors based on a config entry."""
    bhyve = hass.data[DOMAIN]

    sensors = []
    devices = await bhyve.client.api.devices
    for device in devices:
        if device.get("type") == "sprinkler_timer":
            for _, sensor_type in SENSOR_TYPES.items():
                name = "{0} {1}".format(sensor_type.get("name"), device.get("name"))
                _LOGGER.info("Creating sensor: %s", name)
                sensors.append(
                    BHyveSensor(
                        bhyve,
                        device,
                        name,
                        sensor_type["icon"],
                        sensor_type["unit"],
                        sensor_type["update_callback"],
                        sensor_type["device_class"],
                    )
                )

    async_add_entities(sensors, True)


class BHyveSensor(BHyveEntity):
    """Define a BHyve sensor."""

    def __init__(self, bhyve, device, name, icon, unit, update_callback, device_class):
        """Initialize the sensor."""
        super().__init__(
            bhyve, device, name, icon, update_callback, device_class
        )

        self._unit = unit

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Returns the unit of measurement for the sensor."""
        return self._unit

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        if self._device_class == DEVICE_CLASS_BATTERY and self._state is not None:
            return icon_for_battery_level(
                battery_level=int(self._state), charging=False
            )
        return self._icon

    async def async_update(self):
        """Retrieve latest state."""
        try:
            device_id = self._device_id

            device = await self._bhyve.client.api.get_device(device_id)
            if not device:
                _LOGGER.info("No device found with id %s", device_id)
                self._available = False
                return

            self._available = device["is_connected"]
            state, attrs = self._update_callback(device)
            self._attrs = attrs
            self._state = state

        except BHyveError as err:
            _LOGGER.warning("Failed to connect to BHyve servers. %s", err)
            self._available = False
