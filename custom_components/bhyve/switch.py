"""Support for Orbit BHyve switch (toggle zone)."""

from __future__ import annotations

import datetime
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.const import EntityCategory

from . import BHyveCoordinatorEntity
from .const import (
    DEVICE_SPRINKLER,
    DOMAIN,
    EVENT_CHANGE_MODE,
)
from .pybhyve.errors import BHyveError
from .util import orbit_time_to_local_time

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import BHyveDataUpdateCoordinator
    from .pybhyve.typings import BHyveDevice, BHyveTimerProgram

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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the BHyve switch platform from a config entry."""
    coordinator: BHyveDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    devices: list[BHyveDevice] = hass.data[DOMAIN][entry.entry_id]["devices"]

    switches = []
    device_by_id = {}

    # Create rain delay switches for sprinkler devices
    for device in devices:
        device_id = device.get("id")
        device_by_id[device_id] = device
        if device.get("type") == DEVICE_SPRINKLER:
            if not device.get("status"):
                _LOGGER.warning(
                    "Unable to configure device %s: the 'status' attribute is missing. "
                    "Has it been paired with the wifi hub?",
                    device.get("name"),
                )
                continue

            switches.append(BHyveRainDelaySwitch(coordinator, device))

    # Create program switches
    for program in coordinator.data.get("programs", {}).values():
        program_device = device_by_id.get(program.get("device_id"))
        if program_device is not None:
            _LOGGER.info("Creating switch: Program %s", program.get("name"))
            switches.append(BHyveProgramSwitch(coordinator, program_device, program))

    async_add_entities(switches)


class BHyveProgramSwitch(BHyveCoordinatorEntity, SwitchEntity):
    """Define a BHyve program switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: BHyveDataUpdateCoordinator,
        device: BHyveDevice,
        program: BHyveTimerProgram,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, device)

        device_name = device.get("name", "Unknown switch")
        program_name = program.get("name", "unknown")

        self._attr_name = f"{device_name} {program_name} program"
        self._attr_icon = "mdi:bulletin-board"
        self._program_id = program.get("id", "0")

    @property
    def program_data(self) -> dict[str, Any]:
        """Get program data from coordinator."""
        return self.coordinator.data.get("programs", {}).get(self._program_id, {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device state attributes."""
        program = self.program_data
        return {
            "device_id": self._device_id,
            "is_smart_program": program.get("is_smart_program", False),
            "frequency": program.get("frequency"),
            "start_times": program.get("start_times"),
            "budget": program.get("budget"),
            "program": program.get("program"),
            "run_times": program.get("run_times"),
        }

    @property
    def is_on(self) -> bool:
        """Return the status of the sensor."""
        return self.program_data.get("enabled") is True

    @property
    def unique_id(self) -> str:
        """Return the unique id for the switch program."""
        return f"bhyve:program:{self._program_id}"

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the switch on."""
        program = dict(self.program_data)
        program["enabled"] = True
        await self.coordinator.client.update_program(self._program_id, program)
        # Coordinator updates via WebSocket event

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the switch off."""
        program = dict(self.program_data)
        program["enabled"] = False
        await self.coordinator.client.update_program(self._program_id, program)
        # Coordinator updates via WebSocket event

    async def start_program(self) -> None:
        """Begins running a program."""
        program_payload = self.program_data.get("program")
        if program_payload:
            await self._send_program_message(program_payload)

    async def _send_program_message(self, station_payload: Any) -> None:
        try:
            now = datetime.datetime.now()  # noqa: DTZ005
            iso_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            payload = {
                "event": EVENT_CHANGE_MODE,
                "mode": "manual",
                "device_id": self._device_id,
                "timestamp": iso_time,
                "program": station_payload,
            }
            _LOGGER.debug(payload)
            await self.coordinator.client.send_message(payload)

        except BHyveError as err:
            _LOGGER.warning("Failed to send to BHyve websocket message %s", err)
            raise


class BHyveRainDelaySwitch(BHyveCoordinatorEntity, SwitchEntity):
    """Define a BHyve rain delay switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: BHyveDataUpdateCoordinator, device: BHyveDevice
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, device)

        name = f"{device.get('name')} rain delay"
        _LOGGER.info("Creating switch: %s", name)

        self._attr_name = name
        self._attr_icon = "mdi:weather-pouring"

    @property
    def is_on(self) -> bool:
        """Return the status of the sensor."""
        status = self.device_data.get("status", {})
        rain_delay = status.get("rain_delay", 0)
        return rain_delay is not None and rain_delay > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device state attributes."""
        status = self.device_data.get("status", {})
        rain_delay = status.get("rain_delay", 0)

        if rain_delay is not None and rain_delay > 0:
            attrs: dict[str, Any] = {ATTR_DELAY: rain_delay}
            attrs.update(
                {
                    ATTR_CAUSE: status.get("rain_delay_cause", "Unknown"),
                    ATTR_WEATHER_TYPE: status.get("rain_delay_weather_type", "Unknown"),
                    ATTR_STARTED_AT: orbit_time_to_local_time(
                        status.get("rain_delay_started_at", "")
                    ),
                }
            )
            return attrs
        return {}

    @property
    def unique_id(self) -> str:
        """Return a unique, unchanging string that represents this sensor."""
        return f"{self._mac_address}:{self._device_id}:rain_delay"

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the switch on."""
        await self._enable_rain_delay()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the switch off."""
        await self._disable_rain_delay()

    async def _enable_rain_delay(self, hours: int = 24) -> None:
        """Enable rain delay."""
        await self._set_rain_delay(hours)

    async def _disable_rain_delay(self) -> None:
        """Disable rain delay."""
        await self._set_rain_delay(0)

    async def _set_rain_delay(self, hours: int) -> None:
        """Set rain delay hours."""
        try:
            payload = {
                "event": "rain_delay",
                "device_id": self._device_id,
                "delay": hours,
            }
            _LOGGER.info("Setting rain delay: %s", payload)
            await self.coordinator.client.send_message(payload)
            # Coordinator updates via WebSocket event

        except BHyveError as err:
            _LOGGER.warning("Failed to send to BHyve websocket message %s", err)
            raise
