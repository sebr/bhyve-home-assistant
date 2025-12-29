"""DataUpdateCoordinator for B-hyve integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEVICE_SPRINKLER, DOMAIN
from .pybhyve.errors import AuthenticationError, BHyveError

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .pybhyve import BHyveClient
    from .pybhyve.typings import BHyveDevice, BHyveTimerProgram

_LOGGER = logging.getLogger(__name__)


class BHyveDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching B-hyve data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: BHyveClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),  # Poll every 5 minutes
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API (periodic polling)."""
        try:
            # Fetch devices
            devices: list[BHyveDevice] = await self.client.devices

            # Build data structure
            data: dict[str, Any] = {
                "devices": {},
                "programs": {},
                "client": self.client,  # Reference for entity actions
            }

            # Process each device - fetch history and landscapes in parallel per device
            for device in devices:
                device_id = device.get("id")
                device_type = device.get("type")
                if not device_id:
                    continue

                # Only fetch history and landscapes for sprinkler_timer devices
                # Flood sensors and other device types don't have these features
                if device_type == DEVICE_SPRINKLER:
                    # Fetch history and landscapes in parallel for this device
                    history_task = self._fetch_device_history(device_id)
                    landscapes_task = self._fetch_landscapes(device_id, device)

                    history, landscapes = await asyncio.gather(
                        history_task,
                        landscapes_task,
                        return_exceptions=True,
                    )

                    # Handle exceptions from parallel tasks
                    if isinstance(history, Exception):
                        _LOGGER.debug(
                            "Error fetching history for device %s: %s",
                            device_id,
                            history,
                        )
                        history = []
                    if isinstance(landscapes, Exception):
                        _LOGGER.debug(
                            "Error fetching landscapes for device %s: %s",
                            device_id,
                            landscapes,
                        )
                        landscapes = {}
                else:
                    # Non-sprinkler devices don't have history or landscapes
                    history = []
                    landscapes = {}

                data["devices"][device_id] = {
                    "device": device,
                    "history": history,
                    "landscapes": landscapes,
                }

            # Fetch programs
            programs: list[BHyveTimerProgram] = await self.client.timer_programs
            for program in programs:
                program_id = program.get("id")
                if program_id:
                    data["programs"][program_id] = program

            return data  # noqa: TRY300

        except AuthenticationError as err:
            msg = "Authentication failed"
            raise UpdateFailed(msg) from err
        except BHyveError as err:
            msg = f"Error communicating with API: {err}"
            raise UpdateFailed(msg) from err

    async def _fetch_device_history(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch watering history for a device."""
        try:
            history = await self.client.get_device_history(device_id)
        except BHyveError as err:
            _LOGGER.debug("Could not fetch history for device %s: %s", device_id, err)
            return []
        else:
            return history if isinstance(history, list) else []

    async def _fetch_landscapes(
        self, device_id: str, device: BHyveDevice
    ) -> dict[str, dict[str, Any]]:
        """Fetch landscape information for all zones on a device in parallel."""
        landscapes: dict[str, dict[str, Any]] = {}
        zones = device.get("zones", [])

        if not zones:
            return landscapes

        # Fetch all zone landscapes in parallel
        async def fetch_zone_landscape(
            zone: dict[str, Any],
        ) -> tuple[str | None, dict | None]:
            """Fetch landscape for a single zone."""
            zone_id = zone.get("station")
            if not zone_id:
                return None, None

            try:
                landscape = await self.client.get_landscape(device_id, zone_id)
                return str(zone_id), landscape if landscape else None
            except BHyveError as err:
                _LOGGER.debug(
                    "Could not fetch landscape for device %s zone %s: %s",
                    device_id,
                    zone_id,
                    err,
                )
                return str(zone_id), None

        # Gather all landscape fetches in parallel
        results = await asyncio.gather(
            *[fetch_zone_landscape(zone) for zone in zones],
            return_exceptions=True,
        )

        # Process results
        for result in results:
            if isinstance(result, Exception):
                _LOGGER.debug(
                    "Exception fetching landscape for device %s: %s",
                    device_id,
                    result,
                )
                continue

            # Type checker doesn't know result is tuple after Exception filter
            if isinstance(result, tuple):
                zone_id, landscape = result
                if zone_id and landscape:
                    landscapes[zone_id] = landscape

        return landscapes

    async def async_handle_device_event(self, event_data: dict[str, Any]) -> None:  # noqa: PLR0912
        """Handle WebSocket device events."""
        if not self.data:
            _LOGGER.debug("Coordinator data not initialized, ignoring event")
            return

        device_id = event_data.get("device_id")
        event = event_data.get("event")

        if not device_id or device_id not in self.data["devices"]:
            _LOGGER.debug(
                "Device %s not found in coordinator data, ignoring event %s",
                device_id,
                event,
            )
            return

        # Update specific device data based on event type
        device_data = self.data["devices"][device_id]["device"]

        if event == "battery_status":
            # Update battery information
            if "battery" in event_data:
                device_data["battery"] = event_data["battery"]

        elif event == "change_mode":
            # Update device status with mode change data
            if "status" not in device_data:
                device_data["status"] = {}
            device_data["status"].update(event_data)

        elif event == "device_idle":
            # Device went idle, update status
            if "status" not in device_data:
                device_data["status"] = {}
            device_data["status"]["run_mode"] = "off"
            if "watering_status" in device_data["status"]:
                del device_data["status"]["watering_status"]

        elif event == "watering_in_progress_notification":
            # Update watering status
            if "status" not in device_data:
                device_data["status"] = {}
            device_data["status"]["watering_status"] = event_data.get("program", {})
            device_data["status"]["run_mode"] = event_data.get("mode", "manual")

        elif event == "watering_complete":
            # Clear watering status
            if "status" in device_data and "watering_status" in device_data["status"]:
                del device_data["status"]["watering_status"]
            device_data["status"]["run_mode"] = "off"

        elif event == "rain_delay":
            # Update rain delay info
            if "status" not in device_data:
                device_data["status"] = {}
            device_data["status"]["rain_delay"] = event_data.get("delay", 0)

        elif event == "fs_status_update":
            # Update flood sensor status
            if "status" not in device_data:
                device_data["status"] = {}
            device_data["status"].update(event_data)

        elif event == "set_manual_preset_runtime":
            # Update manual preset runtime
            if "status" not in device_data:
                device_data["status"] = {}
            device_data["status"]["manual_preset_runtime"] = event_data.get("runtime")

        # Notify all listening entities
        self.async_set_updated_data(self.data)

    async def async_handle_program_event(self, event_data: dict[str, Any]) -> None:
        """Handle WebSocket program events."""
        if not self.data:
            _LOGGER.debug("Coordinator data not initialized, ignoring event")
            return

        program_id = event_data.get("program_id")

        if not program_id:
            # Some program events have program in a different structure
            program = event_data.get("program", {})
            program_id = program.get("id") if isinstance(program, dict) else None

        if not program_id or program_id not in self.data["programs"]:
            _LOGGER.debug(
                "Program %s not found in coordinator data, ignoring event",
                program_id,
            )
            return

        # Update program data
        program_data = event_data.get("program")
        if isinstance(program_data, dict):
            self.data["programs"][program_id].update(program_data)
        # If no program data provided, just update enabled status
        elif "enabled" in event_data:
            self.data["programs"][program_id]["enabled"] = event_data["enabled"]

        # Notify all listening entities
        self.async_set_updated_data(self.data)
