import logging

import voluptuous as vol

from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.components.binary_sensor import BinarySensorDevice
from . import CONF_ATTRIBUTION, DATA_BHYVE, DEFAULT_BRAND

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ["bhyve"]


def rain_delay_hydrater(device):
    state = False
    attrs = {}

    device_status = device.attribute("status")
    rain_delay = device_status["rain_delay"]

    if rain_delay != None and rain_delay > 0:
        state = True
        attrs = {
            "delay": rain_delay,
            "cause": device_status["rain_delay_cause"],
            "weather_type": device_status["rain_delay_weather_type"],
            "started_at": device_status["rain_delay_started_at"],
        }

    return state, attrs


# sensor_type [ description, device_class, icon, attribute ]
SENSOR_TYPES = {
    "rain_delay": {
        "name": "Rain Delay",
        "icon": "weather-pouring",
        "cb": rain_delay_hydrater,
    }
}


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    bhyve = hass.data.get(DATA_BHYVE)
    if not bhyve:
        return

    sensors = []
    for device in bhyve.devices:
        if device.device_type == "sprinkler_timer":
            for key, sensor_type in SENSOR_TYPES.items():
                name = "{0} {1}".format(sensor_type["name"], device.name)
                _LOGGER.info("Creating binary_sensor: %s", name)
                sensors.append(BHyveBinarySensor(bhyve, name, device, sensor_type))

    async_add_entities(sensors, True)


class BHyveBinarySensor(BinarySensorDevice):
    def __init__(self, bhyve, name, device, sensor_type):
        self._bhyve = bhyve
        self._name = name
        self._unique_id = self._name.lower().replace(" ", "_")
        self._device = device
        self._sensor_type = sensor_type
        self._icon = "mdi:{}".format(sensor_type["icon"])
        self._available = False
        self._state = None
        self._attrs = {}
        self._do_update(device)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._state is True

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def device_class(self):
        """Return the device class of the binary_sensor."""
        return None

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        return self._attrs

    async def async_update(self):
        """Retrieve latest state."""
        try:
            device_id = self._device.device_id

            device = self._bhyve.get_device(device_id)
            if not device:
                _LOGGER.info("No device found with id %s", device_id)
                self._available = False
                return

            self._do_update(device)
        except:
            _LOGGER.warning("Failed to connect to BHyve servers.")
            self._available = False

    def _do_update(self, device):
        if not device:
            return

        base_attrs = {}
        base_attrs[ATTR_ATTRIBUTION] = CONF_ATTRIBUTION
        base_attrs["brand"] = DEFAULT_BRAND
        base_attrs["friendly_name"] = self._name

        state, attrs = self._sensor_type["cb"](device)

        self._attrs = {**base_attrs, **attrs}
        self._state = state

        self._available = device.attribute("is_connected")
