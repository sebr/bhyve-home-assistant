"""Support for Orbit BHyve Service."""
import logging

import voluptuous as vol

from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, config_validation as cv
from homeassistant.helpers.dispatcher import (  # async_dispatcher_send,
    async_dispatcher_connect,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_call_later

from .const import CONF_ATTRIBUTION, DOMAIN, MANUFACTURER, TOPIC_UPDATE
from .pybhyve import Client
from .pybhyve.errors import WebsocketError

_LOGGER = logging.getLogger(__name__)

DATA_CONFIG = "config"

DEFAULT_SOCKET_MIN_RETRY = 15
DEFAULT_WATCHDOG_SECONDS = 5 * 60

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
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

    session = aiohttp_client.async_get_clientsession(hass)

    try:
        bhyve = BHyve(hass, Client(conf[CONF_USERNAME], conf[CONF_PASSWORD], session,),)
        await bhyve.login()
        await bhyve.client.api.devices
        hass.loop.create_task(bhyve.ws_connect())
        hass.data[DOMAIN] = bhyve
    except WebsocketError as err:
        _LOGGER.error("Config entry failed: %s", err)
        raise ConfigEntryNotReady

    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP, bhyve.client.api.websocket.disconnect()
    )

    return True


class BHyve:
    """Define a class to handle the BHyve websocket."""

    def __init__(self, hass, client):
        """Initialize."""
        self._entry_setup_complete = False
        self._hass = hass
        self._watchdog_listener = None
        self._ws_reconnect_delay = DEFAULT_SOCKET_MIN_RETRY
        self.client: Client = client
        self.monitored_conditions = []
        self.devices = {}

    async def login(self):
        """Login."""
        await self.client.api.login()

    async def _attempt_connect(self):
        """Attempt to connect to the socket (retrying later on fail)."""
        try:
            await self.client.api.websocket.connect()
        except WebsocketError as err:
            _LOGGER.error("Error with the websocket connection: %s", err)
            self._ws_reconnect_delay = min(2 * self._ws_reconnect_delay, 480)
            async_call_later(self._hass, self._ws_reconnect_delay, self.ws_connect)

    async def ws_connect(self):
        """Register handlers and connect to the websocket."""

        async def _ws_reconnect(event_time):
            """Forcibly disconnect from and reconnect to the websocket."""
            _LOGGER.debug("Watchdog expired; forcing socket reconnection")
            await self.client.api.websocket.disconnect()
            await self._attempt_connect()

        def on_connect():
            """Define a handler to fire when the websocket is connected."""
            _LOGGER.info("Connected to websocket")
            _LOGGER.debug("Watchdog starting")

            if self._watchdog_listener is not None:
                self._watchdog_listener()
            self._watchdog_listener = async_call_later(
                self._hass, DEFAULT_WATCHDOG_SECONDS, _ws_reconnect
            )

        def on_message(data):
            """Define a handler to fire when the data is received."""
            _LOGGER.debug("New data received: {} - {}".format(data["event"], data["device_id"]))
            # device_id = data.device_id
            # self.devices[device_id][ATTR_LAST_DATA] = data
            # async_dispatcher_send(self._hass, TOPIC_UPDATE)

            _LOGGER.debug("Resetting watchdog")
            self._watchdog_listener()
            self._watchdog_listener = async_call_later(
                self._hass, DEFAULT_WATCHDOG_SECONDS, _ws_reconnect
            )

        def on_disconnect():
            """Define a handler to fire when the websocket is disconnected."""
            _LOGGER.info("Disconnected from websocket")

            # for station in data["devices"]:
            #     if station["macAddress"] in self.stations:
            #         continue

            #     _LOGGER.debug("New station subscription: %s", data)

            #     self.stations[station["macAddress"]] = {
            #         ATTR_LAST_DATA: station["lastData"],
            #         ATTR_LOCATION: station.get("info", {}).get("location"),
            #         ATTR_NAME: station.get("info", {}).get(
            #             "name", station["macAddress"]
            #         ),
            #     }

            # If the websocket disconnects and reconnects, the on_subscribed
            # handler will get called again; in that case, we don't want to
            # attempt forward setup of the config entry (because it will have
            # already been done):

            self._ws_reconnect_delay = DEFAULT_SOCKET_MIN_RETRY

        self.client.api.websocket.on_connect(on_connect)
        self.client.api.websocket.on_message(on_message)

        await self._attempt_connect()

    async def ws_disconnect(self):
        """Disconnect from the websocket."""
        await self.client.api.websocket.disconnect()


class BHyveEntity(Entity):
    """Define a base BHyve entity."""

    def __init__(
        self, bhyve, device, name, icon, update_callback=None, device_class=None,
    ):
        """Initialize the sensor."""
        self._bhyve: BHyve = bhyve
        self._device_class = device_class
        self._async_unsub_dispatcher_connect = None

        self._mac_address = device.get("mac_address")
        self._device_id = device.get("id")
        self._device_type = device.get("type")
        self._device_name = device.get("name")
        self._name = name
        self._icon = "mdi:{}".format(icon)
        self._update_callback = update_callback
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
    def should_poll(self):
        """Disable polling."""
        return False

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_type}"

    async def async_added_to_hass(self):
        """Register callbacks."""

        @callback
        def update():
            """Update the state."""
            self.async_schedule_update_ha_state(True)

        self._async_unsub_dispatcher_connect = async_dispatcher_connect(
            self.hass, TOPIC_UPDATE, update
        )

    async def async_will_remove_from_hass(self):
        """Disconnect dispatcher listener when removed."""
        if self._async_unsub_dispatcher_connect:
            self._async_unsub_dispatcher_connect()
