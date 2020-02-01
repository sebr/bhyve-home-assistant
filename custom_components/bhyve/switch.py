"""Support for Orbit BHyve switch (toggle zone)."""
import datetime
import logging

from datetime import timedelta
from homeassistant.components.switch import DEVICE_CLASS_SWITCH, SwitchDevice
from homeassistant.util import dt

from . import BHyveEntity
from .const import DOMAIN
from .pybhyve.errors import BHyveError
from .util import orbit_time_to_local_time

_LOGGER = logging.getLogger(__name__)


SENSOR_TYPES = {"zone": {"name": "Zone", "icon": "water-pump"}}
DEFAULT_MANUAL_RUNTIME = timedelta(minutes=10)

PROGRAM_SMART_WATERING = "e"
PROGRAM_MANUAL = "manual"

ATTR_MANUAL_RUNTIME = "manual_preset_runtime"
ATTR_SMART_WATERING_ENABLED = "smart_watering_enabled"
ATTR_SPRINKLER_TYPE = "sprinkler_type"
ATTR_IMAGE_URL = "image_url"
ATTR_STARTED_WATERING_AT = "started_watering_station_at"
ATTR_WATERING_PROGRAM = "watering_program"
ATTR_PROGRAM_NAME = "program_name"


async def async_setup_platform(hass, config, async_add_entities, _discovery_info=None):
    """Set up BHyve binary sensors based on a config entry."""
    bhyve = hass.data[DOMAIN]

    switches = []
    devices = await bhyve.devices
    for device in devices:
        if device.get("type") == "sprinkler_timer":
            sensor_type = SENSOR_TYPES["zone"]
            for zone in device.get("zones"):
                _LOGGER.debug("ZONE: %s", zone)
                name = "{0} Zone".format(zone.get("name", "Unknown"))
                _LOGGER.info("Creating switch: %s", name)
                switches.append(
                    BHyveSwitch(hass, bhyve, device, zone, name, sensor_type["icon"],)
                )

    async_add_entities(switches, True)


class BHyveSwitch(BHyveEntity, SwitchDevice):
    """Define a BHyve switch."""

    def __init__(self, hass, bhyve, device, zone, name, icon):
        """Initialize the switch."""
        self._zone = zone
        self._zone_id = zone.get("station")
        self._entity_picture = zone.get("image_url")
        self._manual_preset_runtime = device.get(
            "manual_preset_runtime_sec", DEFAULT_MANUAL_RUNTIME.seconds
        )

        super().__init__(hass, bhyve, device, name, icon, DEVICE_CLASS_SWITCH)

    def _setup(self, device):
        self._state = None
        self._attrs = {}
        self._available = device.get("is_connected", False)

        status = device.get("status", {})
        watering_status = status.get("watering_status")

        _LOGGER.info("{} watering_status: {}".format(self.name, watering_status))

        zones = device.get("zones", [])

        zone = None
        for z in zones:
            if z.get("station") == self._zone_id:
                zone = z
                break

        if zone is not None:
            is_watering = (
                watering_status is not None
                and watering_status.get("current_station") == self._zone_id
            )
            self._state = is_watering
            self._attrs = {ATTR_MANUAL_RUNTIME: self._manual_preset_runtime}

            smart_watering_enabled = zone.get("smart_watering_enabled")
            if smart_watering_enabled is not None:
                self._attrs[ATTR_SMART_WATERING_ENABLED] = smart_watering_enabled

            sprinkler_type = zone.get("sprinkler_type")
            if sprinkler_type is not None:
                self._attrs[ATTR_SPRINKLER_TYPE] = sprinkler_type

            image_url = zone.get("image_url")
            if image_url is not None:
                self._attrs[ATTR_IMAGE_URL] = image_url

            if is_watering:
                started_watering_at = watering_status.get("started_watering_station_at")
                self._set_watering_started(started_watering_at)

    def _set_watering_started(self, timestamp):
        _LOGGER.debug("Timestamp is {}".format(timestamp))
        if timestamp is not None:
            self._attrs[ATTR_STARTED_WATERING_AT] = orbit_time_to_local_time(timestamp)
        else:
            self._attrs[ATTR_STARTED_WATERING_AT] = None

    def _set_watering_program(self, watering_program, lifecycle_phase):
        _LOGGER.debug("Watering program {}".format(watering_program))
        if watering_program is not None and lifecycle_phase != "destroy":
            watering_plan = watering_program.get("watering_plan")
            upcoming_run_times = []
            for plan in watering_plan:
                run_times = plan.get("run_times")
                if run_times:
                    zone_times = list(
                        filter(lambda x: (x.get("station") == self._zone_id), run_times)
                    )
                    if zone_times:
                        plan_date = orbit_time_to_local_time(plan.get("date"))
                        for time in plan.get("start_times", []):
                            t = dt.parse_time(time)
                            upcoming_run_times.append(
                                plan_date + timedelta(hours=t.hour, minutes=t.minute)
                            )
            self._attrs[ATTR_WATERING_PROGRAM] = upcoming_run_times
        else:
            self._attrs[ATTR_WATERING_PROGRAM] = None
            # self._attrs[ATTR_PROGRAM_NAME] = None

    def _on_ws_data(self, data):
        """
            {'event': 'change_mode', 'mode': 'auto', 'device_id': 'id', 'timestamp': '2020-01-09T20:30:00.000Z'}
            {'event': 'watering_in_progress_notification', 'program': 'e', 'current_station': 1, 'run_time': 14, 'started_watering_station_at': '2020-01-09T20:29:59.000Z', 'rain_sensor_hold': False, 'device_id': 'id', 'timestamp': '2020-01-09T20:29:59.000Z'}
            {'event': 'device_idle', 'device_id': 'id', 'timestamp': '2020-01-10T12:32:06.000Z'}
            {'event': 'set_manual_preset_runtime', 'device_id': 'id', 'seconds': 480, 'timestamp': '2020-01-18T17:00:35.000Z'}
            {'event': 'program_changed' }
        """
        event = data.get("event")
        if event is None:
            _LOGGER.warning("No event on ws data {}".format(data))
            return
        elif event == "device_idle" or event == "watering_complete":
            self._state = False
            self._set_watering_started(None)
        elif event == "watering_in_progress_notification":
            zone = data.get("current_station")
            if zone == self._zone_id:
                self._state = True
                started_watering_at = data.get("started_watering_station_at")
                self._set_watering_started(started_watering_at)
        elif event == "change_mode":
            program = data.get("program")
            self._state = program == PROGRAM_SMART_WATERING or program == PROGRAM_MANUAL
        elif event == "set_manual_preset_runtime":
            self._manual_preset_runtime = data.get("seconds")
            self._attrs[ATTR_MANUAL_RUNTIME] = self._manual_preset_runtime
        elif event == "program_changed":
            watering_program = data.get("program")
            lifecycle_phase = data.get("lifecycle_phase")
            self._set_watering_program(watering_program, lifecycle_phase)

    async def _send_station_message(self, station_payload):
        try:
            now = datetime.datetime.now()
            iso_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            payload = {
                "event": "change_mode",
                "mode": "manual",
                "device_id": self._device_id,
                "timestamp": iso_time,
                "stations": station_payload,
            }
            _LOGGER.info("Starting watering")
            await self._bhyve.send_message(payload)

        except BHyveError as err:
            _LOGGER.warning("Failed to send to BHyve websocket message %s", err)
            raise (err)

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
        station_payload = [
            {"station": self._zone_id, "run_time": self._manual_preset_runtime}
        ]
        self._state = True
        await self._send_station_message(station_payload)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        station_payload = []
        self._state = False
        await self._send_station_message(station_payload)

