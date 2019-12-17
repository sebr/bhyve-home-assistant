import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.const import (ATTR_ATTRIBUTION, DEVICE_CLASS_BATTERY)
from homeassistant.core import callback
from homeassistant.helpers.config_validation import (PLATFORM_SCHEMA)
from homeassistant.helpers.entity import (Entity)
from homeassistant.helpers.icon import icon_for_battery_level
from . import CONF_ATTRIBUTION, DATA_BHYVE, DEFAULT_BRAND

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['bhyve']

# sensor_type [ description, unit, icon, attribute ]
SENSOR_TYPES = {
    'battery_level': ['Battery Level', '%', 'battery-50', 'battery.percent']
}

async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    bhyve = hass.data.get(DATA_BHYVE)
    _LOGGER.info('Setting up sensors')
    if not bhyve:
        return

    _LOGGER.info('Lets go!')

    sensors = []
    for device in bhyve.devices:
        if device.device_type == 'sprinkler_timer':
            for sensor_type in SENSOR_TYPES:
                name = '{0} {1}'.format(SENSOR_TYPES[sensor_type][0], device.name)
                _LOGGER.info('Creating sensor: %s', name)
                sensors.append(BHyveSensor(bhyve, name, device, sensor_type))

    async_add_entities(sensors, True)


class BHyveSensor(Entity):

    def __init__(self, bhyve, name, device, sensor_type):
        self._bhyve = bhyve
        self._name = name
        self._unique_id = self._name.lower().replace(' ', '_')
        self._device = device
        self._sensor_type = sensor_type
        self._icon = 'mdi:{}'.format(SENSOR_TYPES.get(self._sensor_type)[2])
        self._available = False
        self._state = None
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
    def state(self):
        return self._state

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        if self._sensor_type == 'battery_level' and self._state is not None:
            return icon_for_battery_level(battery_level=int(self._state), charging=False)
        return self._icon

    @property
    def unit_of_measurement(self):
        """Return the units of measurement."""
        return SENSOR_TYPES.get(self._sensor_type)[1]

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        if self._sensor_type == 'battery_level':
            return DEVICE_CLASS_BATTERY
        return None

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        attrs = {}

        attrs[ATTR_ATTRIBUTION] = CONF_ATTRIBUTION
        attrs['brand'] = DEFAULT_BRAND
        attrs['friendly_name'] = self._name

        return attrs

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

        self._available = device.attribute('is_connected')
        if self._sensor_type == 'battery_level':
            battery = device.attribute('battery')
            _LOGGER.debug("Getting battery level %s", battery)

            if battery != None:
                self._state = battery.get('percent')
