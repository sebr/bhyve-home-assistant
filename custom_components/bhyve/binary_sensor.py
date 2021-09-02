"""Support for Orbit BHyve sensors."""
import logging

from . import BHyveDeviceEntity
from .const import (
    DATA_BHYVE,
    DEVICE_FLOOD,
    EVENT_FS_ALARM,
    EVENT_DEVICE_IDLE,
)
from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_MOISTURE,
    BinarySensorEntity,
)
from .pybhyve.errors import BHyveError
from .util import orbit_time_to_local_time

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    """Set up BHyve sensors based on a config entry."""
    bhyve = hass.data[DATA_BHYVE]

    sensors = []
    devices = await bhyve.devices
    for device in devices:
        if device.get("type") == DEVICE_FLOOD:
            sensors.append(BHyveFloodSensor(hass, bhyve, device))

    async_add_entities(sensors, True)

    
class BHyveFloodSensor(BHyveDeviceEntity):
    """Define a BHyve sensor."""

    def __init__(self, hass, bhyve, device):
        """Initialize the sensor."""
        name = "{0} flood sensor".format(device.get("name"))
        _LOGGER.info("Creating flood sensor: %s", name)
        super().__init__(hass, bhyve, device, name, "water", DEVICE_CLASS_MOISTURE)

    def _setup(self, device):
        self._available = device.get("is_connected", False)
        self._state = self._parse_status(device.get("status", {}))
        self._attrs = {
            "location": device.get("location_name"),
            "shutoff": device.get("auto_shutoff"),
            "rssi": device.get("status", {}).get("rssi"),
        }
        _LOGGER.debug(
            f"Flood sensor {self._name} setup: State: {self._state} | Available: {self._available}"
        )

    def _parse_status(self, status):
        return "on" if status.get("flood_alarm_status") == "alarm" else "off"

    @property
    def state(self):
        """Return the state of the entity"""
        return self._state
    
    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self._mac_address}:{self._device_id}:water"
        
    @property
    def is_on(self):
        return self._state == "on"

    def _on_ws_data(self, data):
        """
            {"last_flood_alarm_at":"2021-08-29T16:32:35.585Z","rssi":-60,"onboard_complete":true,"temp_f":75.2,"provisioned":true,"phy":"le_1m_1000","event":"fs_status_update","temp_alarm_status":"ok","status_updated_at":"2021-08-29T16:33:17.089Z","identify_enabled":false,"device_id":"612ad9134f0c6c9c9faddbba","timestamp":"2021-08-29T16:33:17.089Z","flood_alarm_status":"ok","last_temp_alarm_at":null}
        """
        _LOGGER.info("Received program data update {}".format(data))
        event = data.get("event")
        if event == EVENT_FS_ALARM:
            self._state = self._parse_status(data)
            self._attrs['rssi'] = data.get("rssi")

    def _should_handle_event(self, event_name, data):
        return event_name in [EVENT_FS_ALARM]
