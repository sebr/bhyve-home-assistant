"""Support for Orbit BHyve switch (toggle zone)."""
import datetime
from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import BHyveDeviceEntity, BHyveWebsocketEntity
from .const import (
    CONF_CLIENT,
    DEVICE_SPRINKLER,
    DOMAIN,
    EVENT_CHANGE_MODE,
    EVENT_PROGRAM_CHANGED,
    EVENT_RAIN_DELAY,
    SIGNAL_UPDATE_PROGRAM,
)
from .pybhyve.errors import BHyveError
from .util import filter_configured_devices, orbit_time_to_local_time

_LOGGER = logging.getLogger(__name__)

DEFAULT_MANUAL_RUNTIME = timedelta(minutes=5)

PROGRAM_SMART_WATERING = "e"
PROGRAM_MANUAL = "manual"

ATTR_MANUAL_RUNTIME = "manual_preset_runtime"
ATTR_SMART_WATERING_ENABLED = "smart_watering_enabled"
ATTR_SPRINKLER_TYPE = "sprinkler_type"
ATTR_IMAGE_URL = "image_url"
ATTR_STARTED_WATERING_AT = "started_watering_station_at"
ATTR_SMART_WATERING_PLAN = "watering_program"
ATTR_CURRENT_STATION = "current_station"
ATTR_CURRENT_PROGRAM = "current_program"
ATTR_CURRENT_RUNTIME = "current_runtime"
ATTR_NEXT_START_TIME = "next_start_time"
ATTR_NEXT_START_PROGRAMS = "next_start_programs"

# Service Attributes
ATTR_MINUTES = "minutes"
ATTR_HOURS = "hours"
ATTR_PERCENTAGE = "percentage"

# Rain Delay Attributes
ATTR_CAUSE = "cause"
ATTR_DELAY = "delay"
ATTR_WEATHER_TYPE = "weather_type"
ATTR_STARTED_AT = "started_at"

ATTR_PROGRAM = "program_{}"

SERVICE_BASE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids,
    }
)

ENABLE_RAIN_DELAY_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {
        vol.Required(ATTR_HOURS): cv.positive_int,
    }
)

SET_PRESET_RUNTIME_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {
        vol.Required(ATTR_MINUTES): cv.positive_int,
    }
)

SERVICE_ENABLE_RAIN_DELAY = "enable_rain_delay"
SERVICE_DISABLE_RAIN_DELAY = "disable_rain_delay"
SERVICE_SET_MANUAL_PRESET_RUNTIME = "set_manual_preset_runtime"
SERVICE_START_PROGRAM = "start_program"


SERVICE_TO_METHOD = {
    SERVICE_ENABLE_RAIN_DELAY: {
        "method": "enable_rain_delay",
        "schema": ENABLE_RAIN_DELAY_SCHEMA,
    },
    SERVICE_DISABLE_RAIN_DELAY: {
        "method": "disable_rain_delay",
        "schema": SERVICE_BASE_SCHEMA,
    },
    SERVICE_SET_MANUAL_PRESET_RUNTIME: {
        "method": "set_manual_preset_runtime",
        "schema": SET_PRESET_RUNTIME_SCHEMA,
    },
    SERVICE_START_PROGRAM: {
        "method": "start_program",
        "schema": SERVICE_BASE_SCHEMA,
    },
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the BHyve switch platform from a config entry."""

    bhyve = hass.data[DOMAIN][entry.entry_id][CONF_CLIENT]

    switches = []
    devices = filter_configured_devices(entry, await bhyve.devices)
    programs = await bhyve.timer_programs

    device_by_id = {}

    for device in devices:
        device_id = device.get("id")
        device_by_id[device_id] = device
        if device.get("type") == DEVICE_SPRINKLER:
            if not device.get("status"):
                _LOGGER.warning(
                    "Unable to configure device %s: the 'status' attribute is missing. Has it been paired with the wifi hub?",
                    device.get("name"),
                )
                continue

            switches.append(
                BHyveRainDelaySwitch(hass, bhyve, device, "weather-pouring")
            )

    for program in programs:
        program_device = device_by_id.get(program.get("device_id"))
        program_id = program.get("program")
        if program_device is not None and program_id is not None:
            _LOGGER.info("Creating switch: Program %s", program.get("name"))
            switches.append(
                BHyveProgramSwitch(
                    hass, bhyve, program_device, program, "bulletin-board"
                )
            )

    async_add_entities(switches, True)

    async def async_service_handler(service):
        """Map services to method of BHyve devices."""
        _LOGGER.info("%s service called", service.service)
        method = SERVICE_TO_METHOD.get(service.service)
        if not method:
            _LOGGER.warning("Unknown service method %s", service.service)
            return

        params = {
            key: value for key, value in service.data.items() if key != ATTR_ENTITY_ID
        }
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        component = hass.data.get(SWITCH_DOMAIN)
        if entity_ids:
            target_switches = [component.get_entity(entity) for entity in entity_ids]
        else:
            return

        method_name = method["method"]
        _LOGGER.debug("Service handler: %s %s", method_name, params)

        for entity in target_switches:
            if not hasattr(entity, method_name):
                _LOGGER.error("Service not implemented: %s", method_name)
                return
            await getattr(entity, method_name)(**params)

    for service, details in SERVICE_TO_METHOD.items():
        schema = details["schema"]
        hass.services.async_register(
            DOMAIN, service, async_service_handler, schema=schema
        )


class BHyveProgramSwitch(BHyveWebsocketEntity, SwitchEntity):
    """Define a BHyve program switch."""

    def __init__(self, hass, bhyve, device, program, icon):
        """Initialize the switch."""
        device_name = device.get("name", "Unknown switch")
        program_name = program.get("name", "unknown")

        name = f"{device_name} {program_name} program"

        super().__init__(hass, bhyve, device, name, icon, SwitchDeviceClass.SWITCH)

        self._program = program
        self._device_id = program.get("device_id")
        self._program_id = program.get("id")
        self._available = True

    @property
    def extra_state_attributes(self):
        """Return the device state attributes."""

        attrs = {
            "device_id": self._device_id,
            "is_smart_program": self._program.get("is_smart_program", False),
            "frequency": self._program.get("frequency"),
            "start_times": self._program.get("start_times"),
            "budget": self._program.get("budget"),
            "program": self._program.get("program"),
            "run_times": self._program.get("run_times"),
        }

        return attrs

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self._program.get("enabled") is True

    @property
    def unique_id(self):
        """Return the unique id for the switch program."""
        return f"bhyve:program:{self._program_id}"

    @property
    def entity_category(self):
        """Zone program is a configuration category."""
        return EntityCategory.CONFIG

    async def _set_state(self, is_on):
        self._program.update({"enabled": is_on})
        await self._bhyve.update_program(self._program_id, self._program)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._set_state(False)

    async def start_program(self):
        """Begins running a program."""
        program_payload = self._program["program"]
        await self._send_program_message(program_payload)

    async def _send_program_message(self, station_payload):
        try:
            now = datetime.datetime.now()
            iso_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            payload = {
                "event": EVENT_CHANGE_MODE,
                "mode": "manual",
                "device_id": self._device_id,
                "timestamp": iso_time,
                "program": station_payload,
            }
            _LOGGER.debug(payload)
            await self._bhyve.send_message(payload)

        except BHyveError as err:
            _LOGGER.warning("Failed to send to BHyve websocket message %s", err)
            raise (err)

    async def async_added_to_hass(self):
        """Register callbacks."""

        @callback
        def update(device_id, data):
            """Update the state."""
            _LOGGER.info(
                "Program update: %s - %s - %s", self.name, self._program_id, str(data)
            )
            event = data.get("event")
            if event == EVENT_PROGRAM_CHANGED:
                self._ws_unprocessed_events.append(data)
                self.async_schedule_update_ha_state(True)

        self._async_unsub_dispatcher_connect = async_dispatcher_connect(
            self.hass, SIGNAL_UPDATE_PROGRAM.format(self._program_id), update
        )

    async def async_will_remove_from_hass(self):
        """Disconnect dispatcher listener when removed."""
        if self._async_unsub_dispatcher_connect:
            self._async_unsub_dispatcher_connect()

    def _on_ws_data(self, data):
        #
        # {'event': 'program_changed' }
        #
        _LOGGER.info("Received program data update %s", data)

        event = data.get("event")
        if event is None:
            _LOGGER.warning("No event on ws data %s", data)
            return

        if event == EVENT_PROGRAM_CHANGED:
            program = data.get("program")
            if program is not None:
                self._program = program

    def _should_handle_event(self, event_name, data):
        return event_name in [EVENT_PROGRAM_CHANGED]


class BHyveRainDelaySwitch(BHyveDeviceEntity, SwitchEntity):
    """Define a BHyve rain delay switch."""

    def __init__(self, hass, bhyve, device, icon):
        """Initialize the switch."""
        name = "{} rain delay".format(device.get("name"))
        _LOGGER.info("Creating switch: %s", name)

        self._update_device_cb = None
        self._is_on = False

        super().__init__(hass, bhyve, device, name, icon, SwitchDeviceClass.SWITCH)

    def _setup(self, device):
        self._is_on = False
        self._attrs = {
            "device_id": self._device_id,
        }
        self._available = device.get("is_connected", False)

        device_status = device.get("status")
        rain_delay = device_status.get("rain_delay")

        self._update_device_cb = None
        self._extract_rain_delay(rain_delay, device_status)

    def _on_ws_data(self, data):
        #
        # {'event': 'rain_delay', 'device_id': 'id', 'delay': 0, 'timestamp': '2020-01-14T12:10:10.000Z'}
        #
        event = data.get("event")
        if event is None:
            _LOGGER.warning("No event on ws data %s", data)
            return

        if event == EVENT_RAIN_DELAY:
            self._extract_rain_delay(
                data.get("delay"), {"rain_delay_started_at": data.get("timestamp")}
            )
            # The REST API returns more data about a rain delay (eg cause/weather_type)
            self._update_device_soon()

    def _should_handle_event(self, event_name, data):
        return event_name in [EVENT_RAIN_DELAY]

    def _update_device_soon(self):
        if self._update_device_cb is not None:
            self._update_device_cb()  # unsubscribe
        self._update_device_cb = async_call_later(self._hass, 1, self._update_device)

    async def _update_device(self, time):
        await self._refetch_device(force_update=True)
        self.async_schedule_update_ha_state()

    def _extract_rain_delay(self, rain_delay, device_status=None):
        if rain_delay is not None and rain_delay > 0:
            self._is_on = True
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
            self._is_on = False
            self._attrs = {}

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self._is_on

    @property
    def unique_id(self):
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:rain_delay"

    @property
    def entity_category(self):
        """Rain delay is a configuration category."""
        return EntityCategory.CONFIG

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._is_on = True
        await self.enable_rain_delay()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._is_on = False
        await self.disable_rain_delay()
