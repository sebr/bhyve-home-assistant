"""Support for Orbit BHyve irrigation devices."""
import logging
import os
import pprint

import voluptuous as vol

from aiohttp import WSMsgType, WSMessage

from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_send,
    async_dispatcher_connect,
)
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_ATTRIBUTION,
    CONF_CONF_DIR,
    CONF_PACKET_DUMP,
    DOMAIN,
    MANUFACTURER,
    SIGNAL_UPDATE_DEVICE,
)
from .pybhyve import Client
from .pybhyve.errors import BHyveError, WebsocketError

_LOGGER = logging.getLogger(__name__)

DATA_CONFIG = "config"

DEFAULT_PACKET_DUMP = False
DEFAULT_CONF_DIR = ""

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_PACKET_DUMP, default=DEFAULT_PACKET_DUMP): cv.boolean,
                vol.Optional(CONF_CONF_DIR, default=DEFAULT_CONF_DIR): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the BHyve component."""

    hass.data[DOMAIN] = {}

    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    packet_dump = conf.get(CONF_PACKET_DUMP)
    conf_dir = conf.get(CONF_CONF_DIR)

    if conf_dir == "":
        conf_dir = hass.config.config_dir + "/.bhyve"

    # Create storage/scratch directory.
    try:
        if not os.path.exists(conf_dir):
            os.mkdir(conf_dir)
    except Exception as err:
        _LOGGER.info("Could not create storage dir: %s", err)
        pass

    async def async_update_callback(data):
        if data is not None and packet_dump:
            dump_file = conf_dir + "/" + "packets.dump"
            with open(dump_file, "a") as dump:
                dump.write(pprint.pformat(data, indent=2) + "\n")

        event = data.get("event")
        device_id = None

        if event == "program_changed":
            device_id = data.get("program", {}).get("device_id")
        else:
            device_id = data.get("device_id")

        if device_id is not None:
            async_dispatcher_send(
                hass, SIGNAL_UPDATE_DEVICE.format(device_id), device_id, data
            )
        else:
            _LOGGER.debug("No device_id present on websocket message")

    session = aiohttp_client.async_get_clientsession(hass)

    try:
        bhyve = Client(
            conf[CONF_USERNAME],
            conf[CONF_PASSWORD],
            loop=hass.loop,
            session=session,
            async_callback=async_update_callback,
        )

        await bhyve.login()
        devices = await bhyve.devices
        programs = await bhyve.timer_programs
        for device in devices:
            device["address"] = "REDACTED"
            device["full_location"] = "REDACTED"
            device["location"] = "REDACTED"

        _LOGGER.debug("Devices: {}".format(devices))
        _LOGGER.debug("Programs: {}".format(programs))

        hass.data[DOMAIN] = bhyve
    except WebsocketError as err:
        _LOGGER.error("Config entry failed: %s", err)
        raise ConfigEntryNotReady

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, bhyve.stop())

    return True


class BHyveEntity(Entity):
    """Define a base BHyve entity."""

    def __init__(
        self, hass, bhyve, device, name, icon, device_class=None,
    ):
        """Initialize the sensor."""
        self._hass = hass
        self._bhyve: Client = bhyve
        self._device_class = device_class
        self._async_unsub_dispatcher_connect = None

        self._mac_address = device.get("mac_address")
        self._device_id = device.get("id")
        self._device_type = device.get("type")
        self._device_name = device.get("name")
        self._name = name
        self._icon = "mdi:{}".format(icon)
        self._state = None
        self._available = False
        self._attrs = {}

        self._ws_unprocessed_events = []
        self._setup(device)

    def _setup(self, device):
        pass

    def _on_ws_data(self, data):
        pass

    async def _refetch_device(self, force_update=False):
        try:
            device = await self._bhyve.get_device(self._device_id, force_update)
            if not device:
                _LOGGER.info("No device found with id %s", self._device_id)
                self._available = False
                return

            self._setup(device)

        except BHyveError as err:
            _LOGGER.warning("Failed to connect to BHyve servers. %s", err)
            self._available = False

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def device_info(self):
        """Return device registry information for this entity."""
        return {
            "identifiers": {(DOMAIN, self._mac_address)},
            "name": self._device_name,
            "manufacturer": MANUFACTURER,
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
        }

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        return self._attrs

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._name}"

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def should_poll(self):
        """Disable polling."""
        return False

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_type}:{self._name}"

    async def async_added_to_hass(self):
        """Register callbacks."""

        @callback
        def update(device_id, data):
            """Update the state."""
            _LOGGER.info(
                "Callback update: {} - {} - {}".format(
                    self.name, self._device_id, str(data)[:160]
                )
            )
            event = data.get("event")
            if event == "device_disconnected":
                self._available = False
            elif event == "device_connected":
                self._available = True

            self._ws_unprocessed_events.append(data)
            self.async_schedule_update_ha_state(True)

        self._async_unsub_dispatcher_connect = async_dispatcher_connect(
            self.hass, SIGNAL_UPDATE_DEVICE.format(self._device_id), update
        )

    async def async_will_remove_from_hass(self):
        """Disconnect dispatcher listener when removed."""
        if self._async_unsub_dispatcher_connect:
            self._async_unsub_dispatcher_connect()

    async def async_update(self):
        """Retrieve latest state."""
        ws_updates = list(self._ws_unprocessed_events)
        self._ws_unprocessed_events[:] = []

        for ws_event in ws_updates:
            self._on_ws_data(ws_event)
