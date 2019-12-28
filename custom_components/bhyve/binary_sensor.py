"""Support for Orbit BHyve binary sensors ()."""
import logging

from homeassistant.components.binary_sensor import BinarySensorDevice

from . import BHyveEntity
from .const import DOMAIN
from .pybhyve.errors import BHyveError

_LOGGER = logging.getLogger(__name__)


def rain_delay_callback(device):
    """Update callback for rain delay binary sensor."""
    state = False
    attrs = {}

    device_status = device["status"]
    rain_delay = device_status["rain_delay"]

    if rain_delay is not None and rain_delay > 0:
        state = True
        attrs = {
            "delay": rain_delay,
            "cause": device_status["rain_delay_cause"],
            "weather_type": device_status["rain_delay_weather_type"],
            "started_at": device_status["rain_delay_started_at"],
        }

    return state, attrs


SENSOR_TYPES = {
    "rain_delay": {
        "name": "Rain Delay",
        "icon": "weather-pouring",
        "update_callback": rain_delay_callback,
    }
}


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    """Set up BHyve binary sensors based on a config entry."""
    bhyve = hass.data[DOMAIN]

    binary_sensors = []
    devices = await bhyve.client.api.devices
    for device in devices:
        if device.get("type") == "sprinkler_timer":
            for _, sensor_type in SENSOR_TYPES.items():
                name = "{0} {1}".format(sensor_type["name"], device.get("name"))
                _LOGGER.info("Creating binary_sensor: %s", name)
                binary_sensors.append(
                    BHyveBinarySensor(
                        bhyve,
                        device,
                        name,
                        sensor_type["icon"],
                        sensor_type["update_callback"],
                    )
                )

    async_add_entities(binary_sensors, True)


class BHyveBinarySensor(BHyveEntity, BinarySensorDevice):
    """Define a BHyve binary sensor."""

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self._state is True

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
