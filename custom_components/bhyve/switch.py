"""Support for Orbit BHyve switch (toggle zone)."""
import datetime
import logging

from homeassistant.components.switch import DEVICE_CLASS_SWITCH, SwitchDevice

from . import BHyveEntity
from .const import DOMAIN
from .pybhyve.errors import BHyveError

_LOGGER = logging.getLogger(__name__)


def zone_update_callback(device, zone_id):
    """Update callback for rain delay binary sensor."""
    state = False
    attrs = {}

    status = device["status"]
    watering_status = status["watering_status"]

    _LOGGER.info("watering_status: %s", watering_status)

    zones = device["zones"]
    zone = next(filter(lambda x: x.get("station") == zone_id, zones))

    zone = None
    for z in zones:
        if z.get("station") == zone_id:
            zone = z
            break

    if zone is not None:
        is_watering = (
            watering_status is not None
            and watering_status["current_station"] == zone_id
        )
        state = is_watering
        attrs = {
            "smart_watering_enabled": zone["smart_watering_enabled"],
            "sprinkler_type": zone["sprinkler_type"],
            "image_url": zone["image_url"],
        }

        if is_watering:
            attrs["started_watering_station_at"] = watering_status[
                "started_watering_station_at"
            ]

    return state, attrs


SENSOR_TYPES = {
    "zone": {
        "name": "Zone",
        "icon": "water-pump",
        "update_callback": zone_update_callback,
    }
}


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    """Set up BHyve binary sensors based on a config entry."""
    bhyve = hass.data[DOMAIN]

    switches = []
    devices = await bhyve.client.api.devices
    for device in devices:
        if device.get("type") == "sprinkler_timer":
            sensor_type = SENSOR_TYPES["zone"]
            for zone in device.get("zones"):
                _LOGGER.info("ZONE: %s", zone)
                name = "{0} Zone".format(zone["name"])
                _LOGGER.info("Creating switch: %s", name)
                switches.append(
                    BHyveSwitch(
                        bhyve,
                        device,
                        zone,
                        name,
                        sensor_type["icon"],
                        sensor_type["update_callback"],
                    )
                )

    async_add_entities(switches, True)


class BHyveSwitch(BHyveEntity, SwitchDevice):
    """Define a BHyve switch."""

    def __init__(self, bhyve, device, zone, name, icon, update_callback):
        """Initialize the switch."""
        super().__init__(
            bhyve, device, name, icon, update_callback, DEVICE_CLASS_SWITCH
        )

        self._zone = zone
        self._zone_id = zone.get("station")
        self._entity_picture = zone.get("image_url")

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_type}:zone:{self._zone_id}"

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self._state is True

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        try:
            now = datetime.datetime.now()
            iso_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            payload = {
                "event": "change_mode",
                "mode": "manual",
                "device_id": self._device_id,
                "timestamp": iso_time,
                "stations": [{"station": self._zone_id, "run_time": 1.0}],
            }
            _LOGGER.info("Starting watering")
            await self._bhyve.client.api.websocket.send(payload)

        except BHyveError as err:
            _LOGGER.warning("Failed to connect to BHyve servers. %s", err)
            raise (err)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""

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
            state, attrs = self._update_callback(device, self._zone_id)
            self._attrs = attrs
            self._state = state

        except BHyveError as err:
            _LOGGER.warning("Failed to connect to BHyve servers. %s", err)
            self._available = False
