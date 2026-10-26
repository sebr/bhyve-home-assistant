"""
Test that device mode, state and program switches report what the device does.

Live data from a hose timer in auto mode showed the State sensor reading "off"
for five minutes after every watering and after the device_idle Orbit sends
about every four hours, until the next poll restored "auto".
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bhyve.const import CONF_DEVICES, DOMAIN
from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.select import SELECT_TYPES, BHyveSelectEntity
from custom_components.bhyve.sensor import SENSOR_TYPES_SPRINKLER, BHyveSensor
from custom_components.bhyve.switch import (
    BHyveProgramSwitch,
    BHyveSwitchEntityDescription,
)
from custom_components.bhyve.valve import BHyveZoneValve

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from collections.abc import Callable, Iterator

    from homeassistant.core import HomeAssistant

DEVICE_ID = "sprinkler-1"
MAC = "aabbccddeeff"
OTHER_DEVICE_ID = "sprinkler-2"


def device(run_mode: str | None = "auto") -> dict[str, Any]:
    """Build a one-zone sprinkler timer."""
    status: dict[str, Any] = {} if run_mode is None else {"run_mode": run_mode}
    return {
        "id": DEVICE_ID,
        "name": "Garden Timer",
        "type": "sprinkler_timer",
        "mac_address": MAC,
        "is_connected": True,
        "zones": [{"station": 1, "name": "Lawn"}],
        "status": status,
    }


def make_coordinator(hass: HomeAssistant, run_mode: str = "auto") -> Any:
    """Create a real coordinator holding one sprinkler."""
    coordinator = BHyveDataUpdateCoordinator(hass, MagicMock(), MagicMock())
    coordinator.data = {
        "devices": {DEVICE_ID: {"device": device(run_mode), "history": []}},
        "programs": {},
    }
    return coordinator


def status_of(coordinator: Any) -> dict[str, Any]:
    """Return the sprinkler's status."""
    return coordinator.data["devices"][DEVICE_ID]["device"]["status"]


async def send(coordinator: Any, *events: dict[str, Any]) -> None:
    """Feed websocket events to the coordinator."""
    with patch.object(coordinator, "async_set_updated_data"):
        for event in events:
            await coordinator.async_handle_device_event(
                {"device_id": DEVICE_ID, **event}
            )


WATERING = {
    "event": "watering_in_progress_notification",
    "current_station": 1,
    "program": "manual",
    "run_time": 5,
}


class TestRunMode:
    """run_mode follows the device instead of flipping to "off"."""

    async def test_periodic_device_idle_keeps_auto(self, hass: HomeAssistant) -> None:
        """The device_idle Orbit sends every few hours does not mean "off"."""
        coordinator = make_coordinator(hass, "auto")

        await send(coordinator, {"event": "device_idle"})

        assert status_of(coordinator)["run_mode"] == "auto"

    @pytest.mark.parametrize("end_event", ["watering_complete", "device_idle"])
    async def test_watering_end_restores_previous_mode(
        self, hass: HomeAssistant, end_event: str
    ) -> None:
        """Manual during a watering, then back to the mode it interrupted."""
        coordinator = make_coordinator(hass, "auto")

        await send(coordinator, WATERING)
        assert status_of(coordinator)["run_mode"] == "manual"

        await send(coordinator, {"event": end_event})
        assert status_of(coordinator)["run_mode"] == "auto"
        assert "watering_status" not in status_of(coordinator)

    async def test_off_device_stays_off_after_watering(
        self, hass: HomeAssistant
    ) -> None:
        """A device switched off returns to off, not auto."""
        coordinator = make_coordinator(hass, "off")

        await send(coordinator, WATERING, {"event": "watering_complete"})

        assert status_of(coordinator)["run_mode"] == "off"

    async def test_change_mode_sets_run_mode_only(self, hass: HomeAssistant) -> None:
        """change_mode updates the mode without copying the event into status."""
        coordinator = make_coordinator(hass, "auto")

        await send(
            coordinator,
            {
                "event": "change_mode",
                "mode": "off",
                "timestamp": "2026-10-14T00:00:00.000Z",
                "stations": [],
            },
        )

        assert status_of(coordinator) == {"run_mode": "off"}

    async def test_change_mode_after_watering_is_remembered(
        self, hass: HomeAssistant
    ) -> None:
        """A mode set by change_mode is the one restored after the next watering."""
        coordinator = make_coordinator(hass, "auto")

        await send(
            coordinator,
            {"event": "change_mode", "mode": "off"},
            WATERING,
            {"event": "device_idle"},
        )

        assert status_of(coordinator)["run_mode"] == "off"


class TestEntities:
    """Entities show the device's mode, and nothing made up."""

    async def test_select_shows_mode_during_watering(self, hass: HomeAssistant) -> None:
        """During a watering the select shows the mode, not "unknown"."""
        coordinator = make_coordinator(hass, "auto")
        entity = BHyveSelectEntity(
            coordinator, status_of_device(coordinator), SELECT_TYPES[0]
        )

        await send(coordinator, WATERING)

        assert status_of(coordinator)["run_mode"] == "manual"
        assert entity.current_option == "auto"

    def test_state_sensor_has_no_made_up_value(self, hass: HomeAssistant) -> None:
        """Without a run_mode the State sensor is unknown, not "unavailable"."""
        coordinator = make_coordinator(hass)
        coordinator.data["devices"][DEVICE_ID]["device"] = device(None)
        description = next(d for d in SENSOR_TYPES_SPRINKLER if d.key == "state")

        sensor = BHyveSensor(
            coordinator, coordinator.data["devices"][DEVICE_ID]["device"], description
        )

        assert sensor.native_value is None


def status_of_device(coordinator: Any) -> dict[str, Any]:
    """Return the sprinkler device dict."""
    return coordinator.data["devices"][DEVICE_ID]["device"]


class TestCommandTimestamps:
    """Commands carry the current time in UTC, as their "Z" suffix says."""

    @pytest.fixture(autouse=True)
    def sydney_process_clock(self) -> Iterator[None]:
        """
        Run with the process clock in Sydney, as on Home Assistant OS.

        The bug only shows when the process time zone is not UTC, which test
        runners and CI usually are.
        """
        previous = os.environ.get("TZ")
        os.environ["TZ"] = "Australia/Sydney"
        time.tzset()
        yield
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()

    @staticmethod
    def assert_is_now_in_utc(timestamp: str) -> None:
        """Assert a "...Z" timestamp is the current UTC time."""
        sent = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        assert abs(sent - dt_util.utcnow()) < timedelta(minutes=1), timestamp

    async def test_valve_command_timestamp_is_utc(self, hass: HomeAssistant) -> None:
        """A valve command is stamped with UTC, not Sydney time labelled UTC."""
        coordinator = make_coordinator(hass)
        coordinator.client = MagicMock()
        coordinator.client.send_message = AsyncMock()
        sprinkler = status_of_device(coordinator)
        valve = BHyveZoneValve(
            coordinator, sprinkler, sprinkler["zones"][0], "Lawn", []
        )

        await valve._send_station_message([])

        self.assert_is_now_in_utc(
            coordinator.client.send_message.call_args.args[0]["timestamp"]
        )

    async def test_program_command_timestamp_is_utc(self, hass: HomeAssistant) -> None:
        """Starting a program is stamped with UTC."""
        coordinator = make_coordinator(hass)
        coordinator.client = MagicMock()
        coordinator.client.send_message = AsyncMock()
        program = {"id": "program-a", "device_id": DEVICE_ID, "program": "a"}
        coordinator.data["programs"] = {"program-a": program}
        switch = BHyveProgramSwitch(
            coordinator,
            status_of_device(coordinator),
            program,
            BHyveSwitchEntityDescription(key="program"),
        )

        await switch.start_program()

        self.assert_is_now_in_utc(
            coordinator.client.send_message.call_args.args[0]["timestamp"]
        )


class FakeClient:
    """Stand-in for BHyveClient serving two sprinklers and their programs."""

    programs: list[dict[str, Any]] = []  # noqa: RUF012

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Accept and ignore the real client's arguments."""

    async def login(self) -> bool:
        """Report a successful login."""
        return True

    def listen(self, loop: AbstractEventLoop, async_callback: Callable) -> None:
        """Do not open a websocket."""

    async def stop(self, *args: Any, **kwargs: Any) -> None:
        """Nothing to stop."""

    @property
    async def devices(self) -> list[dict[str, Any]]:
        """Return the sprinklers."""
        return [
            device(),
            {
                **device(),
                "id": OTHER_DEVICE_ID,
                "name": "Front Timer",
                "mac_address": "112233445566",
            },
        ]

    @property
    async def timer_programs(self) -> list[dict[str, Any]]:
        """Return the canned programs."""
        return FakeClient.programs

    async def get_device_history(self, *_args: Any, **_kwargs: Any) -> list:
        """Return no history."""
        return []

    async def get_landscape(self, *_args: Any, **_kwargs: Any) -> None:
        """Return no landscape."""


def program(program_id: str, name: str, device_id: str = DEVICE_ID) -> dict[str, Any]:
    """Build a manual program for a sprinkler."""
    return {
        "id": program_id,
        "device_id": device_id,
        "name": name,
        "program": "a",
        "enabled": True,
        "is_smart_program": False,
        "run_times": [{"station": 1, "run_time": 10}],
    }


async def setup_integration(hass: HomeAssistant) -> MockConfigEntry:
    """Set up the integration for the sprinkler."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        options={CONF_DEVICES: [DEVICE_ID, OTHER_DEVICE_ID]},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.bhyve.BHyveClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def program_switch(hass: HomeAssistant, program_id: str) -> str | None:
    """Return the entity id of a program's switch, if registered."""
    return er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"bhyve:program:{program_id}"
    )


@pytest.mark.usefixtures("enable_custom_integrations")
class TestDeletedPrograms:
    """A program deleted in the B-hyve app does not leave its switch behind."""

    async def test_program_deleted_while_running(self, hass: HomeAssistant) -> None:
        """A program_changed delete removes the switch straight away."""
        FakeClient.programs = [program("p1", "Morning"), program("p2", "Evening")]
        entry = await setup_integration(hass)
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        assert program_switch(hass, "p1") is not None

        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator.async_handle_program_event(
                {"program_id": "p1", "lifecycle_phase": "destroy"}
            )
        await hass.async_block_till_done()

        assert program_switch(hass, "p1") is None
        assert program_switch(hass, "p2") is not None

    async def test_program_deleted_while_stopped(self, hass: HomeAssistant) -> None:
        """A switch whose program is gone at startup is removed."""
        registry = er.async_get(hass)
        FakeClient.programs = [program("p1", "Morning"), program("p2", "Evening")]
        entry = await setup_integration(hass)
        assert await hass.config_entries.async_unload(entry.entry_id)

        FakeClient.programs = [program("p2", "Evening")]
        with patch("custom_components.bhyve.BHyveClient", FakeClient):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert program_switch(hass, "p1") is None
        assert program_switch(hass, "p2") is not None
        assert registry.async_get(program_switch(hass, "p2")) is not None

    async def test_empty_program_list_keeps_switches(self, hass: HomeAssistant) -> None:
        """An empty program list may be a glitch, so nothing is removed."""
        FakeClient.programs = [program("p1", "Morning")]
        entry = await setup_integration(hass)

        FakeClient.programs = []
        with patch("custom_components.bhyve.BHyveClient", FakeClient):
            await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()

        assert program_switch(hass, "p1") is not None

    async def test_device_missing_from_program_list_keeps_switches(
        self, hass: HomeAssistant
    ) -> None:
        """A device whose programs are all missing may be a glitch."""
        FakeClient.programs = [
            program("p1", "Morning"),
            program("p2", "Evening"),
            program("p3", "Front", OTHER_DEVICE_ID),
        ]
        entry = await setup_integration(hass)

        FakeClient.programs = [program("p2", "Evening")]
        with patch("custom_components.bhyve.BHyveClient", FakeClient):
            await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()

        assert program_switch(hass, "p1") is None
        assert program_switch(hass, "p2") is not None
        assert program_switch(hass, "p3") is not None


class PollingClient:
    """A client whose next poll returns the given sprinkler status."""

    def __init__(self) -> None:
        """Start with the device in auto, not watering."""
        self.status: dict[str, Any] = {"run_mode": "auto"}
        self.get_device_history = AsyncMock(return_value=[])
        self.get_landscape = AsyncMock(return_value=None)

    @property
    async def devices(self) -> list[dict[str, Any]]:
        """Return the sprinkler with the current status."""
        return [{**device(), "status": dict(self.status)}]

    @property
    async def timer_programs(self) -> list[dict[str, Any]]:
        """Return no programs."""
        return []


class TestPolledMode:
    """A poll's stale "manual" does not undo the mode restored by events."""

    async def test_stale_manual_after_watering_is_corrected(
        self, hass: HomeAssistant
    ) -> None:
        """
        Live sequence: the watering ends, then a poll still says "manual".

        Without a watering in progress, "manual" is stale and the mode the
        device was in before the watering is kept.
        """
        client = PollingClient()
        coordinator = BHyveDataUpdateCoordinator(hass, client, MagicMock())
        await coordinator.async_refresh()
        assert status_of(coordinator)["run_mode"] == "auto"

        await send(coordinator, WATERING, {"event": "watering_complete"})
        assert status_of(coordinator)["run_mode"] == "auto"

        client.status = {"run_mode": "manual", "watering_status": None}
        await coordinator.async_refresh()

        assert status_of(coordinator)["run_mode"] == "auto"

    async def test_polled_watering_keeps_manual(self, hass: HomeAssistant) -> None:
        """A poll during a watering shows "manual"."""
        client = PollingClient()
        coordinator = BHyveDataUpdateCoordinator(hass, client, MagicMock())
        await coordinator.async_refresh()

        client.status = {
            "run_mode": "manual",
            "watering_status": {"current_station": 1, "run_time": 5},
        }
        await coordinator.async_refresh()

        assert status_of(coordinator)["run_mode"] == "manual"

    async def test_polled_off_is_remembered(self, hass: HomeAssistant) -> None:
        """A mode seen only in a poll is the one restored after a watering."""
        client = PollingClient()
        client.status = {"run_mode": "off"}
        coordinator = BHyveDataUpdateCoordinator(hass, client, MagicMock())
        await coordinator.async_refresh()

        client.status = {"run_mode": "manual"}
        await coordinator.async_refresh()

        assert status_of(coordinator)["run_mode"] == "off"

    async def test_unknown_previous_mode_keeps_manual(
        self, hass: HomeAssistant
    ) -> None:
        """With nothing to restore, Orbit's value is shown as reported."""
        client = PollingClient()
        client.status = {"run_mode": "manual"}
        coordinator = BHyveDataUpdateCoordinator(hass, client, MagicMock())

        await coordinator.async_refresh()

        assert status_of(coordinator)["run_mode"] == "manual"
