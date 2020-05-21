"""Support for Orbit BHyve binary sensors ()."""
import logging

try:
    from homeassistant.components.binary_sensor import BinarySensorEntity
except ImportError:
    from homeassistant.components.binary_sensor import (
        BinarySensorDevice as BinarySensorEntity,
    )

from homeassistant.helpers.event import async_call_later

from . import BHyveEntity
from .const import DOMAIN
from .util import orbit_time_to_local_time
from .pybhyve.errors import BHyveError

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {"rain_delay": {"name": "Rain Delay", "icon": "weather-pouring"}}

ATTR_CAUSE = "cause"
ATTR_DELAY = "delay"
ATTR_WEATHER_TYPE = "weather_type"
ATTR_STARTED_AT = "started_at"


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
                    BHyveRainDelayBinarySensor(
                        hass, bhyve, device, name, sensor_type["icon"]
                    )
                )

    async_add_entities(binary_sensors, True)


class BHyveRainDelayBinarySensor(BHyveEntity, BinarySensorEntity):
    """Define a BHyve binary sensor."""

    def _setup(self, device):
        self._state = None
        self._attrs = {}
        self._available = device.get("is_connected", False)

        device_status = device.get("status", {})
        rain_delay = device_status.get("rain_delay")

        self._update_device_cb = None
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
            self._extract_rain_delay(
                data.get("delay"), {"rain_delay_started_at": data.get("timestamp")}
            )
            # The REST API returns more data about a rain delay (eg cause/weather_type)
            self._update_device_soon()

    def _update_device_soon(self):
        if self._update_device_cb is not None:
            self._update_device_cb()  # unsubscribe
        self._update_device_cb = async_call_later(self._hass, 1, self._update_device)

    async def _update_device(self, time):
        await self._refetch_device(force_update=True)
        self.async_schedule_update_ha_state()

    def _extract_rain_delay(self, rain_delay, device_status=None):
        if rain_delay is not None and rain_delay > 0:
            self._state = True
            self._attrs = {ATTR_DELAY: rain_delay}
            if device_status is not None:
                self._attrs.update(
                    {
                        ATTR_CAUSE: device_status.get("rain_delay_cause"),
                        ATTR_WEATHER_TYPE: device_status.get("rain_delay_weather_type"),
                        ATTR_STARTED_AT: orbit_time_to_local_time(
                            device_status.get("rain_delay_started_at")
                        ),
                    }
                )
        else:
            self._state = False
            self._attrs = {}

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self._state is True
