"""Support for Orbit BHyve irrigation devices."""
import json
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
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
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
    DATA_BHYVE,
    DOMAIN,
    EVENT_PROGRAM_CHANGED,
    EVENT_RAIN_DELAY,
    EVENT_SET_MANUAL_PRESET_TIME,
    MANUFACTURER,
    SIGNAL_UPDATE_DEVICE,
    SIGNAL_UPDATE_PROGRAM,
)
from .util import anonymize
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
        program_id = None

        if event == EVENT_PROGRAM_CHANGED:
            device_id = data.get("program", {}).get("device_id")
            program_id = data.get("program", {}).get("id")
        else:
            device_id = data.get("device_id")

        if device_id is not None:
            async_dispatcher_send(
                hass, SIGNAL_UPDATE_DEVICE.format(device_id), device_id, data
            )
        if program_id is not None:
            async_dispatcher_send(
                hass, SIGNAL_UPDATE_PROGRAM.format(program_id), program_id, data
            )

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
        devices = [anonymize(device) for device in await bhyve.devices]
        programs = await bhyve.timer_programs

        _LOGGER.debug("Devices: {}".format(json.dumps(devices)))
        _LOGGER.debug("Programs: {}".format(json.dumps(programs)))

        hass.data[DATA_BHYVE] = bhyve
    except WebsocketError as err:
        _LOGGER.error("Config entry failed: %s", err)
        raise ConfigEntryNotReady

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, bhyve.stop())

    return True


def get_entity_from_domain(hass, domains, entity_id):
    domains = domains if isinstance(domains, list) else [domains]
    for domain in domains:
        component = hass.data.get(domain)
        if component is None:
            raise HomeAssistantError("{} component not set up".format(domain))
        entity = component.get_entity(entity_id)
        if entity is not None:
            return entity
    raise HomeAssistantError("{} not found in {}".format(entity_id, ",".join(domains)))


class BHyveEntity(Entity):
    """Define a base BHyve entity."""

    def __init__(
        self, hass, bhyve, name, icon, device_class=None,
    ):
        """Initialize the sensor."""
        self._hass = hass
        self._bhyve: Client = bhyve
        self._device_class = device_class

        self._name = name
        self._icon = "mdi:{}".format(icon)
        self._state = None
        self._available = False
        self._attrs = {}

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

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
    def device_info(self):
        """Return device registry information for this entity."""
        return {
            "name": self._name,
            "manufacturer": MANUFACTURER,
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
        }


class BHyveWebsocketEntity(BHyveEntity):
    """An entity which responds to websocket events."""

    def __init__(
        self, hass, bhyve, name, icon, device_class=None,
    ):
        self._async_unsub_dispatcher_connect = None
        self._ws_unprocessed_events = []
        super().__init__(hass, bhyve, name, icon, device_class)

    def _on_ws_data(self, data):
        pass

    def _should_handle_event(self, event_name):
        """True if the websocket event should be handled"""
        return True

    async def async_update(self):
        """Retrieve latest state."""
        ws_updates = list(self._ws_unprocessed_events)
        self._ws_unprocessed_events[:] = []

        for ws_event in ws_updates:
            self._on_ws_data(ws_event)


class BHyveDeviceEntity(BHyveWebsocketEntity):
    """Define a base BHyve entity with a device."""

    def __init__(
        self, hass, bhyve, device, name, icon, device_class=None,
    ):
        """Initialize the sensor."""

        self._mac_address = device.get("mac_address")
        self._device_id = device.get("id")
        self._device_type = device.get("type")
        self._device_name = device.get("name")

        super().__init__(hass, bhyve, name, icon, device_class)

        self._setup(device)

    def _setup(self, device):
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
            raise (err)

    async def _fetch_device_history(self, force_update=False):
        try:
            return await self._bhyve.get_device_history(self._device_id, force_update)

        except BHyveError as err:
            _LOGGER.warning("Failed to connect to BHyve servers. %s", err)
            raise (err)

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
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        raise HomeAssistantError(
            "{} does not define a unique_id".format(self.__class__.__name__)
        )

    async def async_added_to_hass(self):
        """Register callbacks."""

        @callback
        def update(device_id, data):
            """Update the state."""
            event = data.get("event")
            if event == "device_disconnected":
                self._available = False
            elif event == "device_connected":
                self._available = True
            if self._should_handle_event(event):
                _LOGGER.info(
                    "Callback update: {} - {} - {}".format(
                        self.name, self._device_id, str(data)[:160]
                    )
                )
                self._ws_unprocessed_events.append(data)
                self.async_schedule_update_ha_state(True)

        self._async_unsub_dispatcher_connect = async_dispatcher_connect(
            self.hass, SIGNAL_UPDATE_DEVICE.format(self._device_id), update
        )

    async def async_will_remove_from_hass(self):
        """Disconnect dispatcher listener when removed."""
        if self._async_unsub_dispatcher_connect:
            self._async_unsub_dispatcher_connect()

    async def set_manual_preset_runtime(self, minutes: int):
        # {event: "set_manual_preset_runtime", device_id: "abc", seconds: 900}
        payload = {
            "event": EVENT_SET_MANUAL_PRESET_TIME,
            "device_id": self._device_id,
            "seconds": minutes * 60,
        }
        _LOGGER.info("Setting manual preset runtime: {}".format(payload))
        await self._bhyve.send_message(payload)

    async def enable_rain_delay(self, hours: int = 24):
        await self._set_rain_delay(hours)

    async def disable_rain_delay(self):
        await self._set_rain_delay(0)

    async def _set_rain_delay(self, hours):
        try:
            # {event: "rain_delay", device_id: "abc", delay: 48}
            payload = {
                "event": EVENT_RAIN_DELAY,
                "device_id": self._device_id,
                "delay": hours,
            }
            _LOGGER.info("Setting rain delay: {}".format(payload))
            await self._bhyve.send_message(payload)

        except BHyveError as err:
            _LOGGER.warning("Failed to send to BHyve websocket message %s", err)
            raise (err)
