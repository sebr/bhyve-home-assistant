"""Support for Orbit BHyve valve (toggle zone)."""

import datetime
import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.components.valve.const import (
    DOMAIN as VALVE_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt

from custom_components.bhyve.pybhyve.client import BHyveClient
from custom_components.bhyve.pybhyve.typings import (
    BHyveDevice,
    BHyveTimerProgram,
    BHyveZone,
)

from . import BHyveDeviceEntity
from .const import (
    CONF_CLIENT,
    DEVICE_SPRINKLER,
    DOMAIN,
    EVENT_CHANGE_MODE,
    EVENT_DEVICE_IDLE,
    EVENT_PROGRAM_CHANGED,
    EVENT_SET_MANUAL_PRESET_TIME,
    EVENT_WATERING_COMPLETE,
    EVENT_WATERING_IN_PROGRESS,
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

START_WATERING_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {
        vol.Required(ATTR_MINUTES): cv.positive_int,
    }
)

SET_PRESET_RUNTIME_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {
        vol.Required(ATTR_MINUTES): cv.positive_int,
    }
)

SET_SMART_WATERING_SOIL_MOISTURE_SCHEMA = SERVICE_BASE_SCHEMA.extend(
    {
        vol.Required(ATTR_PERCENTAGE): cv.positive_int,
    }
)

SERVICE_ENABLE_RAIN_DELAY = "enable_rain_delay"
SERVICE_DISABLE_RAIN_DELAY = "disable_rain_delay"
SERVICE_START_WATERING = "start_watering"
SERVICE_STOP_WATERING = "stop_watering"
SERVICE_SET_MANUAL_PRESET_RUNTIME = "set_manual_preset_runtime"
SERVICE_SET_SMART_WATERING_SOIL_MOISTURE = "set_smart_watering_soil_moisture"
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
    SERVICE_START_WATERING: {
        "method": "start_watering",
        "schema": START_WATERING_SCHEMA,
    },
    SERVICE_STOP_WATERING: {"method": "stop_watering", "schema": SERVICE_BASE_SCHEMA},
    SERVICE_SET_MANUAL_PRESET_RUNTIME: {
        "method": "set_manual_preset_runtime",
        "schema": SET_PRESET_RUNTIME_SCHEMA,
    },
    SERVICE_SET_SMART_WATERING_SOIL_MOISTURE: {
        "method": "set_smart_watering_soil_moisture",
        "schema": SET_SMART_WATERING_SOIL_MOISTURE_SCHEMA,
    },
    SERVICE_START_PROGRAM: {
        "method": "start_program",
        "schema": SERVICE_BASE_SCHEMA,
    },
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the BHyve valve platform from a config entry."""
    bhyve = hass.data[DOMAIN][entry.entry_id][CONF_CLIENT]

    valves = []
    devices = filter_configured_devices(entry, await bhyve.devices)
    programs = await bhyve.timer_programs

    device_by_id = {}

    for device in devices:
        device_id = device.get("id")
        device_by_id[device_id] = device
        if device.get("type") == DEVICE_SPRINKLER:
            if not device.get("status"):
                _LOGGER.warning(
                    "Unable to configure device %s: the 'status' attribute is missing. Has it been paired with the wifi hub?",  # noqa: E501
                    device.get("name"),
                )
                continue

            # Filter out any programs which are not for this device
            device_programs = [
                program for program in programs if program.get("device_id") == device_id
            ]

            all_zones = device.get("zones")
            for zone in all_zones:
                zone_name = zone.get("name")
                # if the zone doesn't have a name, set it to the device's name if there is only one (eg a hose timer)  # noqa: E501
                if zone_name is None:
                    zone_name = (
                        device.get("name") if len(all_zones) == 1 else "Unnamed Zone"
                    )
                valves.append(
                    BHyveZoneValve(
                        hass,
                        bhyve,
                        device,
                        zone,
                        zone_name,
                        device_programs,
                        "water-pump",
                    )
                )

    async_add_entities(valves, True)  # noqa: FBT003

    async def async_service_handler(service: Any) -> None:
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
        component = hass.data.get(VALVE_DOMAIN)
        if entity_ids and component is not None:
            target_vales = [component.get_entity(entity) for entity in entity_ids]
        else:
            return

        method_name = method["method"]
        _LOGGER.debug("Service handler: %s %s", method_name, params)

        for entity in target_vales:
            if not hasattr(entity, method_name):
                _LOGGER.error("Service not implemented: %s", method_name)
                return
            await getattr(entity, method_name)(**params)

    for service, details in SERVICE_TO_METHOD.items():
        schema = details["schema"]
        hass.services.async_register(
            DOMAIN, service, async_service_handler, schema=schema
        )


class BHyveZoneValve(BHyveDeviceEntity, ValveEntity):
    """Define a BHyve zone valve."""

    def __init__(
        self,
        hass: HomeAssistant,
        bhyve: BHyveClient,
        device: BHyveDevice,
        zone: BHyveZone,
        zone_name: str,
        device_programs: list[BHyveTimerProgram],
        icon: str,
    ) -> None:
        """Initialize the valve."""
        self._zone: BHyveZone = zone
        self._zone_id: str = zone.get("station", "")
        self._entity_picture: str | None = zone.get("image_url")

        self._attr_is_closed: bool = True
        self._attr_reports_position = False
        self._attr_supported_features = (
            ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        )

        self._zone_name: str = zone_name
        self._smart_watering_enabled: bool = zone.get("smart_watering_enabled", False)
        self._manual_preset_runtime: int = device.get(
            "manual_preset_runtime_sec", DEFAULT_MANUAL_RUNTIME.seconds
        )

        self._initial_programs = device_programs

        name = f"{self._zone_name} zone"
        _LOGGER.info("Creating valve: %s", name)

        super().__init__(hass, bhyve, device, name, icon, ValveDeviceClass.WATER)

    def _setup(self, device: BHyveDevice) -> None:
        self._attr_is_closed = True
        self._attrs = {
            "device_name": self._device_name,
            "device_id": self._device_id,
            "zone_name": self._zone_name,
            "station": self._zone_id,
            ATTR_SMART_WATERING_ENABLED: self._smart_watering_enabled,
        }
        self._available = device.get("is_connected", False)

        status = device.get("status", {})
        watering_status = status.get("watering_status")

        _LOGGER.info("%s watering_status: %s", self.name, watering_status)

        zones = device.get("zones", [])

        zone = next(filter(lambda z: z.get("station") == self._zone_id, zones), None)

        if zone is not None:
            is_watering = (
                watering_status is not None
                and watering_status.get("current_station") == self._zone_id
            )
            self._attr_is_closed = not is_watering
            self._attrs[ATTR_MANUAL_RUNTIME] = self._manual_preset_runtime

            next_start_time = orbit_time_to_local_time(status.get("next_start_time"))
            if next_start_time is not None:
                next_start_programs = status.get("next_start_programs")
                self._attrs.update(
                    {
                        ATTR_NEXT_START_TIME: next_start_time.isoformat(),
                        ATTR_NEXT_START_PROGRAMS: next_start_programs,
                    }
                )

            sprinkler_type = zone.get("sprinkler_type")
            if sprinkler_type is not None:
                self._attrs[ATTR_SPRINKLER_TYPE] = sprinkler_type

            image_url = zone.get("image_url")
            if image_url is not None:
                self._attrs[ATTR_IMAGE_URL] = image_url

            if is_watering:
                started_watering_at = watering_status.get("started_watering_station_at")
                current_station = watering_status.get("current_station")
                current_program = watering_status.get("program", None)
                stations = watering_status.get("stations")
                current_runtime = stations[0].get("run_time") if stations else None
                self._set_watering_started(
                    started_watering_at,
                    current_station,
                    current_program,
                    current_runtime,
                )

        if self._initial_programs is not None:
            programs = self._initial_programs
            for program in programs:
                self._set_watering_program(program)
            self._initial_programs = None

    def _set_watering_started(
        self,
        timestamp: str | None,
        station: str | None,
        program: str | None,
        runtime: int | None,
    ) -> None:
        started_watering_at_timestamp = (
            orbit_time_to_local_time(timestamp) if timestamp is not None else None
        )

        self._attrs.update(
            {
                ATTR_CURRENT_STATION: station,
                ATTR_CURRENT_PROGRAM: program,
                ATTR_CURRENT_RUNTIME: runtime,
                ATTR_STARTED_WATERING_AT: started_watering_at_timestamp,
            }
        )

    def _set_watering_program(self, program: BHyveTimerProgram | None) -> None:
        if program is None:
            return

        program_name = program.get("name", "Unknown")
        program_id = program.get("program")
        program_enabled = program.get("enabled", False)

        if program_id is None:
            return

        program_attr = ATTR_PROGRAM.format(program_id)

        # Filter out any run times which are not for this valve
        active_program_run_times = list(
            filter(
                lambda x: (x.get("station") == self._zone_id),
                program.get("run_times", []),
            )
        )

        is_smart_program = program.get("is_smart_program", False)

        self._attrs[program_attr] = {
            "enabled": program_enabled,
            "name": program_name,
            "is_smart_program": is_smart_program,
        }

        if not program_enabled or not active_program_run_times:
            _LOGGER.info(
                "%s Zone: Watering program %s (%s) is not enabled, skipping",
                self._zone_name,
                program_name,
                program_id,
            )

            return

        """
        #    "name": "Backyard",
        #    "frequency": { "type": "days", "days": [1, 4] },
        #    "start_times": ["07:30"],
        #    "budget": 100,
        #    "program": "a",
        #    "run_times": [{ "run_time": 20, "station": 1 }],
        """

        if is_smart_program is True:
            upcoming_run_times = []
            for plan in program.get("watering_plan", []):
                run_times = plan.get("run_times")
                if run_times:
                    zone_times = list(
                        filter(lambda x: (x.get("station") == self._zone_id), run_times)
                    )
                    if zone_times:
                        plan_date = orbit_time_to_local_time(plan.get("date"))
                        for time in plan.get("start_times", []):
                            upcoming_time = dt.parse_time(time)
                            if upcoming_time is not None and plan_date is not None:
                                upcoming_run_times.append(
                                    plan_date
                                    + timedelta(
                                        hours=upcoming_time.hour,
                                        minutes=upcoming_time.minute,
                                    )
                                )
            self._attrs[program_attr].update(
                {ATTR_SMART_WATERING_PLAN: upcoming_run_times}
            )
        else:
            self._attrs[program_attr].update(
                {
                    "start_times": program.get("start_times", []),
                    "frequency": program.get("frequency", []),
                    "run_times": active_program_run_times,
                }
            )

    def _should_handle_event(self, event_name: str, _data: dict) -> bool:
        return event_name in [
            EVENT_CHANGE_MODE,
            EVENT_DEVICE_IDLE,
            EVENT_PROGRAM_CHANGED,
            EVENT_SET_MANUAL_PRESET_TIME,
            EVENT_WATERING_COMPLETE,
            EVENT_WATERING_IN_PROGRESS,
        ]

    def _on_ws_data(self, data: dict) -> None:
        """
        Handle websocket data.

        # {'event': 'watering_in_progress_notification', 'program': 'e', 'current_station': 1, 'run_time': 14, 'started_watering_station_at': '2020-01-09T20:29:59.000Z', 'rain_sensor_hold': False, 'device_id': 'id', 'timestamp': '2020-01-09T20:29:59.000Z'}
        # {'event': 'device_idle', 'device_id': 'id', 'timestamp': '2020-01-10T12:32:06.000Z'}
        # {'event': 'set_manual_preset_runtime', 'device_id': 'id', 'seconds': 480, 'timestamp': '2020-01-18T17:00:35.000Z'}
        # {'event': 'program_changed' }
        """  # noqa: E501
        event = data.get("event")
        if event in (EVENT_DEVICE_IDLE, EVENT_WATERING_COMPLETE) or (
            event == EVENT_CHANGE_MODE and data.get("mode") in ("off", "auto")
        ):
            self._attr_is_closed = True
            self._set_watering_started(None, None, None, None)
        elif event == EVENT_WATERING_IN_PROGRESS:
            current_station = data.get("current_station")

            # Normalize ids
            if current_station is not None and str(current_station) == str(
                self._zone_id
            ):
                # This is *my* zone running
                self._attr_is_closed = False
                started_watering_at = data.get("started_watering_station_at")
                current_program = data.get("program")
                current_runtime = data.get("run_time")

                self._set_watering_started(
                    started_watering_at,
                    current_station,
                    current_program,
                    current_runtime,
                )
            # Only turn off on watering_in_progress if another station is active
            elif current_station is not None and not self._attr_is_closed:
                if str(current_station) != str(self._zone_id):
                    _LOGGER.debug(
                        "%s: Another station (%s) is watering, marking this zone (%s) off",  # noqa: E501
                        self.name,
                        current_station,
                        self._zone_id,
                    )
                    self._attr_is_closed = True
                    self._set_watering_started(None, None, None, None)
        elif event == EVENT_SET_MANUAL_PRESET_TIME:
            manual_preset_runtime = data.get("seconds")
            if manual_preset_runtime is not None:
                self._manual_preset_runtime = manual_preset_runtime
                self._attrs[ATTR_MANUAL_RUNTIME] = manual_preset_runtime
        elif event == EVENT_PROGRAM_CHANGED:
            watering_program = data.get("program")
            lifecycle_phase = data.get("lifecycle_phase")
            if lifecycle_phase != "destroy":
                self._set_watering_program(watering_program)
            else:
                self._attrs[ATTR_SMART_WATERING_PLAN] = None

    async def _send_station_message(self, station_payload: Any) -> None:
        try:
            now = datetime.datetime.now()  # noqa: DTZ005 - be timezone aware?
            iso_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            payload = {
                "event": EVENT_CHANGE_MODE,
                "mode": "manual",
                "device_id": self._device_id,
                "timestamp": iso_time,
                "stations": station_payload,
            }
            _LOGGER.debug("Sending message %s", payload)
            await self._bhyve.send_message(payload)

        except BHyveError as err:
            _LOGGER.warning("Failed to send to BHyve websocket message %s", err)
            raise

    @property
    def entity_picture(self) -> str | None:
        """Return picture of the entity."""
        return self._entity_picture

    @property
    def unique_id(self) -> str:
        """Return a unique, unchanging string that represents this valve."""
        return f"{self._mac_address}:{self._device_id}:{self._zone_id}:valve"

    async def set_smart_watering_soil_moisture(self, percentage: float) -> None:
        """Set the soil moisture percentage for the zone."""
        if self._smart_watering_enabled:
            landscape = None
            try:
                landscape = await self._bhyve.get_landscape(
                    self._device_id, self._zone_id
                )

            except BHyveError as err:
                _LOGGER.warning(
                    "Unable to retreive current soil data for %s: %s", self.name, err
                )

            if landscape is not None:
                _LOGGER.debug("Landscape data %s", landscape)

                # Define the minimum landscape update json payload
                landscape_update = {
                    "current_water_level": 0,
                    "device_id": "",
                    "id": "",
                    "station": 0,
                }

                # B-hyve computed value for 0% moisture
                landscape_moisture_level_0 = landscape["replenishment_point"]

                # B-hyve computed value for 100% moisture
                landscape_moisture_level_100 = landscape["field_capacity_depth"]

                # Set property to computed user desired soil moisture level
                landscape_update["current_water_level"] = landscape_moisture_level_0 + (
                    (
                        percentage
                        * (landscape_moisture_level_100 - landscape_moisture_level_0)
                    )
                    / 100.0
                )
                # Set remaining properties
                landscape_update["device_id"] = self._device_id
                landscape_update["id"] = landscape["id"]
                landscape_update["station"] = self._zone_id

                try:
                    _LOGGER.debug("Landscape update %s", landscape_update)
                    await self._bhyve.update_landscape(landscape_update)

                except BHyveError as err:
                    _LOGGER.warning(
                        "Unable to set soil moisture level for %s: %s", self.name, err
                    )
        else:
            _LOGGER.info(
                "Zone %s isn't smart watering enabled, cannot set soil moisture.",
                self._zone_name,
            )

    async def start_watering(self, minutes: float) -> None:
        """Open the valve and starts watering."""
        station_payload = [{"station": self._zone_id, "run_time": minutes}]
        self._attr_is_closed = False
        await self._send_station_message(station_payload)

    async def stop_watering(self) -> None:
        """Close the valve and stops watering."""
        station_payload = []
        self._attr_is_closed = True
        await self._send_station_message(station_payload)

    async def async_open_valve(self) -> None:
        """Open the valve."""
        run_time = self._manual_preset_runtime / 60
        if run_time == 0:
            _LOGGER.warning(
                "Valve %s manual preset runtime is 0, watering has defaulted to %s minutes. Set the manual run time on your device or please specify number of minutes using the bhyve.start_watering service",  # noqa: E501
                self._device_name,
                int(DEFAULT_MANUAL_RUNTIME.seconds / 60),
            )
            run_time = 5

        await self.start_watering(run_time)

    async def async_close_valve(self) -> None:
        """Close the valve."""
        await self.stop_watering()
