"""Support for Orbit BHyve binary sensors ()."""
import logging

from homeassistant.components.binary_sensor import BinarySensorDevice

from . import BHyveEntity
from .const import DOMAIN
from .pybhyve.errors import BHyveError

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {"rain_delay": {"name": "Rain Delay", "icon": "weather-pouring"}}


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    """Set up BHyve binary sensors based on a config entry."""
    bhyve = hass.data[DOMAIN]

    binary_sensors = []
    devices = await bhyve.devices
    for device in devices:
        if device.get("type") == "sprinkler_timer":
            for _, sensor_type in SENSOR_TYPES.items():
                name = "{0} {1}".format(sensor_type["name"], device.get("name"))
                _LOGGER.info("Creating binary_sensor: %s", name)
                binary_sensors.append(
                    BHyveBinarySensor(bhyve, device, name, sensor_type["icon"])
                )

    async_add_entities(binary_sensors, True)


class BHyveBinarySensor(BHyveEntity, BinarySensorDevice):
    """Define a BHyve binary sensor."""

    def _setup(self, device):
        self._state = None
        self._attrs = {}
        self._available = device.get("is_connected", False)

        device_status = device["status"]
        rain_delay = device_status["rain_delay"]

        self._extract_rain_delay(rain_delay, device_status)

    def _on_ws_data(self, data):
        """
            {'event': 'rain_delay', 'device_id': 'id', 'delay': 0, 'timestamp': '2020-01-14T12:10:10.000Z'}
        """
        event = data.get("event")
        if event is None:
            _LOGGER.warning("No event on ws data {}".format(data))
            return
        elif event == "rain_delay":
            self._extract_rain_delay(data.get("delay"), {})

    def _extract_rain_delay(self, rain_delay, device_status=None):
        if rain_delay is not None and rain_delay > 0:
            self._state = True
            self._attrs = {"delay": rain_delay}
            if device_status is not None:
                self._attrs.update(
                    {
                        "cause": device_status.get("rain_delay_cause", None),
                        "weather_type": device_status.get(
                            "rain_delay_weather_type", None
                        ),
                        "started_at": device_status.get("rain_delay_started_at", None),
                    }
                )
        else:
            self._state = False
            self._attrs = {}

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self._state is True
