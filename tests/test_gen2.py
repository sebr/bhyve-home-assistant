"""
Gen 2 hose timers (HT25A-0001 behind a BH1G2 Wi-Fi hub) and auto-adding devices.

The fixtures are a real account's /v1/devices and /v1/sprinkler_timer_programs
(2026-10-28), scrubbed: fake ids and names, no MACs, locations, user or
weather ids. Two Gen 2 timers ("Hedge", "Flower Bed") sit next to five
Gen 1 timers. What the Gen 2 timers do differently, from that data:

- status has no ``next_start_time`` / ``next_start_programs`` at all, so the
  "Next watering" sensor stayed unknown;
- an idle timer reports ``watering_status: {"clear_on_idle": true}``, not null;
- they were added after the integration was set up, and the device options
  never offered them, so Home Assistant only showed their hub.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from aiohttp import WSMsgType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.bhyve import async_remove_config_entry_device
from custom_components.bhyve.const import (
    CONF_AUTO_ADD,
    CONF_DEVICES,
    CONF_KNOWN_DEVICES,
    DOMAIN,
)
from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.pybhyve import BHyveClient
from custom_components.bhyve.sensor import _next_watering_attributes
from custom_components.bhyve.util import (
    NextWatering,
    new_leaf_device_ids,
    next_program_start,
    next_watering,
    options_with_known_devices_seeded,
    options_with_new_devices,
    watering_in_progress,
)
from custom_components.bhyve.valve import BHyveZoneValve

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

FIXTURES = Path(__file__).parent / "fixtures"
PACIFIC = ZoneInfo("America/Los_Angeles")

HEDGE = "timer-hedge-09"
BED = "timer-flower-bed-11"
VEGGIE = "timer-vegetable-garden-08"
GEN2_HUB = "hub-gen2-10"
GEN1_TIMERS = [
    "timer-patio-03",
    "timer-side-yard-05",
    "timer-back-yard-06",
    "timer-front-yard-07",
    VEGGIE,
]


def orbit_devices() -> list[dict[str, Any]]:
    """Return the account's devices, fresh copy."""
    return json.loads((FIXTURES / "orbit_devices.json").read_text())


def orbit_programs() -> list[dict[str, Any]]:
    """Return the account's programs, fresh copy."""
    return json.loads((FIXTURES / "orbit_programs.json").read_text())


def device(device_id: str) -> dict[str, Any]:
    """One device from the fixture."""
    return next(d for d in orbit_devices() if d["id"] == device_id)


def at(text: str) -> datetime:
    """Return a Pacific wall-clock time."""
    return datetime.fromisoformat(text).replace(tzinfo=PACIFIC)


# --------------------------------------------------------------------------
# Next watering, computed from the programs
# --------------------------------------------------------------------------


class TestNextProgramStart:
    """next_program_start: the timer's next run from its enabled programs."""

    def test_interval_program_counts_from_its_start_date(self) -> None:
        """Hedge: every 3 days from May 11 at 06:00 -> Oct 29 06:00."""
        result = next_program_start(
            device(HEDGE), orbit_programs(), at("2026-10-28T09:40")
        )
        assert result[:2] == (at("2026-10-29T06:00"), ["a"])

    def test_interval_program_runs_today_when_the_time_is_ahead(self) -> None:
        """On a run day before 06:00 the run is today."""
        result = next_program_start(
            device(HEDGE), orbit_programs(), at("2026-10-29T05:59")
        )
        assert result[:2] == (at("2026-10-29T06:00"), ["a"])

    def test_interval_program_skips_a_run_already_started(self) -> None:
        """At 06:00 exactly the run has started: the next is 3 days later."""
        result = next_program_start(
            device(HEDGE), orbit_programs(), at("2026-10-29T06:00")
        )
        assert result[:2] == (at("2026-11-01T06:00"), ["a"])

    def test_disabled_program_and_one_without_a_letter_are_ignored(self) -> None:
        """Hedge's old "Trees" program (disabled, program null) never counts."""
        programs = [p for p in orbit_programs() if p["name"] == "Trees"]
        assert (
            next_program_start(device(HEDGE), programs, at("2026-10-28T09:40")).start
            is None
        )

    def test_even_days(self) -> None:
        """Flower Bed: even days at 04:00; 28th is past -> the 30th."""
        result = next_program_start(
            device(BED), orbit_programs(), at("2026-10-28T09:40")
        )
        assert result[:2] == (at("2026-10-30T04:00"), ["a"])

    def test_even_days_across_the_dst_change(self) -> None:
        """Nov 1 2026 is the fall-back day; Nov 2 04:00 is PST (-08:00)."""
        result = next_program_start(
            device(BED), orbit_programs(), at("2026-10-31T07:00")
        )
        assert result.start == at("2026-11-02T04:00")
        assert result.start.utcoffset().total_seconds() == -8 * 3600

    def test_odd_days(self) -> None:
        """Odd days are calendar parity, like the B-hyve app's label."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["frequency"] = {"type": "odd"}
        result = next_program_start(device(BED), [bed], at("2026-10-28T09:40"))
        assert result[:2] == (at("2026-10-29T04:00"), ["a"])

    def test_week_days_zero_is_sunday(self) -> None:
        """days: [0] (Sunday) from Wednesday Oct 28 -> Sunday Nov 1."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["frequency"] = {"type": "days", "days": [0]}
        result = next_program_start(device(BED), [bed], at("2026-10-28T09:40"))
        assert result[:2] == (at("2026-11-01T04:00"), ["a"])

    def test_earliest_start_time_of_several(self) -> None:
        """Several start times: the first one still ahead."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["start_times"] = ["21:30", "04:00"]
        result = next_program_start(device(BED), [bed], at("2026-10-28T09:40"))
        assert result[:2] == (at("2026-10-28T21:30"), ["a"])

    def test_program_not_started_yet(self) -> None:
        """Nothing before program_start_date."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["program_start_date"] = "2026-11-05T00:00:00-08:00"
        result = next_program_start(device(BED), [bed], at("2026-10-28T09:40"))
        assert result[:2] == (at("2026-11-06T04:00"), ["a"])

    def test_program_already_ended(self) -> None:
        """Nothing after program_end_date."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["program_end_date"] = "2026-10-29T00:00:00-07:00"
        assert (
            next_program_start(device(BED), [bed], at("2026-10-28T09:40")).start is None
        )

    def test_no_run_time_means_no_watering(self) -> None:
        """A program whose stations all run 0 minutes waters nothing."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["run_times"] = [{"station": 1, "run_time": 0}]
        assert (
            next_program_start(device(BED), [bed], at("2026-10-28T09:40")).start is None
        )

    def test_two_programs_same_time_both_named(self) -> None:
        """Two programs starting together are both listed, in letter order."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        second = {**copy.deepcopy(bed), "id": "prog-b", "program": "b"}
        result = next_program_start(device(BED), [second, bed], at("2026-10-28T09:40"))
        assert result[:2] == (at("2026-10-30T04:00"), ["a", "b"])

    def test_other_devices_programs_do_not_count(self) -> None:
        """Only the timer's own programs."""
        programs = [p for p in orbit_programs() if p["device_id"] != BED]
        assert (
            next_program_start(device(BED), programs, at("2026-10-28T09:40")).start
            is None
        )

    def test_smart_program_is_not_guessed(self) -> None:
        """Smart (weather-driven) programs: no guess, the sensor stays unknown."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["is_smart_program"] = True
        result = next_program_start(device(BED), [bed], at("2026-10-28T09:40"))
        assert result.start is None
        assert result.computable is False

    def test_unknown_frequency_is_not_guessed(self) -> None:
        """A frequency this code doesn't know gives no time rather than a wrong one."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["frequency"] = {"type": "interval_hours", "interval_hours": 6}
        result = next_program_start(device(BED), [bed], at("2026-10-28T09:40"))
        assert result.start is None
        assert result.computable is False

    def test_program_starting_months_ahead(self) -> None:
        """A start date beyond the ~32-day scan is still found (review, #510)."""
        programs = orbit_programs()
        bed = next(p for p in programs if p["device_id"] == BED)
        bed["program_start_date"] = "2027-03-01T00:00:00-08:00"
        result = next_program_start(device(BED), [bed], at("2026-10-28T09:40"))
        assert result[:2] == (at("2027-03-02T04:00"), ["a"])

    def test_interval_first_run_months_ahead(self) -> None:
        """An interval whose first day is far off is found too."""
        programs = orbit_programs()
        hedge = next(p for p in programs if p["device_id"] == HEDGE and p["enabled"])
        hedge["frequency"]["interval_start_time"] = "2027-02-10T00:00:00-08:00"
        result = next_program_start(device(HEDGE), [hedge], at("2026-10-28T09:40"))
        assert result[:2] == (at("2027-02-10T06:00"), ["a"])

    def test_interval_without_a_usable_anchor_is_not_computable(self) -> None:
        """No parseable interval start and no program start: can't compute."""
        programs = orbit_programs()
        hedge = next(p for p in programs if p["device_id"] == HEDGE and p["enabled"])
        hedge["frequency"]["interval_start_time"] = "not a time"
        hedge["program_start_date"] = None
        result = next_program_start(device(HEDGE), [hedge], at("2026-10-28T09:40"))
        assert result.start is None
        assert result.computable is False

    def test_a_program_that_does_not_water_is_still_computable(self) -> None:
        """Disabled programs don't make the timer "not computable"."""
        programs = [p for p in orbit_programs() if p["name"] == "Trees"]
        result = next_program_start(device(HEDGE), programs, at("2026-10-28T09:40"))
        assert result.computable is True


# --------------------------------------------------------------------------
# Coordinator: fill in next_start_time only where Orbit leaves it out
# --------------------------------------------------------------------------


def make_coordinator(
    hass: HomeAssistant, options: dict | None = None
) -> BHyveDataUpdateCoordinator:
    """Return a coordinator over a client that serves the fixture."""
    client = MagicMock()
    devices, programs = orbit_devices(), orbit_programs()

    async def _devices() -> list:
        return devices

    async def _programs() -> list:
        return programs

    type(client).devices = property(lambda _self: _devices())
    type(client).timer_programs = property(lambda _self: _programs())
    client.get_device_history = AsyncMock(return_value=[])
    client.get_landscape = AsyncMock(return_value=None)
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = options or {CONF_KNOWN_DEVICES: []}
    entry.state = ConfigEntryState.LOADED
    coordinator = BHyveDataUpdateCoordinator(hass, client, entry)
    coordinator.fixture_devices = devices  # type: ignore[attr-defined]
    return coordinator


def upcoming(coordinator: BHyveDataUpdateCoordinator, device_id: str) -> NextWatering:
    """Next watering for a device, as its sensor reads it now."""
    return next_watering(
        coordinator.data["devices"][device_id]["device"],
        coordinator.data["programs"].values(),
    )


class TestNextWatering:
    """
    next_watering: Orbit's time, else one worked out from the programs.

    Worked out when read, from the current status and programs, never stored.
    """

    async def test_gen2_timers_get_a_computed_time(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """Both Gen 2 timers get a time and programs, marked as computed."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        coordinator = make_coordinator(hass)
        coordinator.data = await coordinator._async_update_data()
        assert upcoming(coordinator, HEDGE) == NextWatering(
            at("2026-10-29T06:00"), ["a"], computed=True
        )
        assert upcoming(coordinator, BED).start == at("2026-10-30T04:00")
        # Nothing is written into the client's cached device dicts.
        status = coordinator.data["devices"][HEDGE]["device"]["status"]
        assert "next_start_time" not in status

    async def test_orbit_reported_time_is_used(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """Gen 1 timers: Orbit's own value, not marked."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        coordinator = make_coordinator(hass)
        coordinator.data = await coordinator._async_update_data()
        veggie = upcoming(coordinator, VEGGIE)
        assert veggie.start == at("2026-10-30T04:00")
        assert veggie.computed is False

    @pytest.mark.parametrize("sent", [None, "2106-02-07T06:28:15.000Z", "garbage"])
    def test_unusable_orbit_time_is_computed(self, freezer: Any, sent: Any) -> None:
        """Orbit's null, its 2106 placeholder or junk: computed (review, #510)."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        bed = device(BED)
        bed["status"]["next_start_time"] = sent
        result = next_watering(bed, orbit_programs())
        assert result == NextWatering(at("2026-10-30T04:00"), ["a"], computed=True)

    async def test_mode_change_shows_at_once(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """Off, then back on, by websocket: no wait for a poll (review, #510)."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        coordinator = make_coordinator(hass)
        coordinator.data = await coordinator._async_update_data()
        await coordinator.async_handle_device_event(
            {"event": "change_mode", "device_id": BED, "mode": "off"}
        )
        assert upcoming(coordinator, BED) == NextWatering(
            None, [], computed=True, unavailable="timer_off"
        )
        await coordinator.async_handle_device_event(
            {"event": "change_mode", "device_id": BED, "mode": "auto"}
        )
        assert upcoming(coordinator, BED).start == at("2026-10-30T04:00")

    async def test_run_starting_moves_to_the_next(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """Once a run starts, the next one shows, not "unknown" until a poll."""
        freezer.move_to(at("2026-10-29T05:00").astimezone(UTC))
        coordinator = make_coordinator(hass)
        coordinator.data = await coordinator._async_update_data()
        assert upcoming(coordinator, HEDGE).start == at("2026-10-29T06:00")
        freezer.move_to(at("2026-10-29T06:00:30").astimezone(UTC))
        assert upcoming(coordinator, HEDGE).start == at("2026-11-01T06:00")

    async def test_watering_ending_keeps_the_time(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """A watering ending doesn't blank the next watering."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        coordinator = make_coordinator(hass)
        coordinator.data = await coordinator._async_update_data()
        await coordinator.async_handle_device_event(
            {"event": "watering_complete", "device_id": BED}
        )
        assert upcoming(coordinator, BED).start == at("2026-10-30T04:00")

    async def test_program_change_moves_it(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """A program edit in the B-hyve app moves the computed time."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        coordinator = make_coordinator(hass)
        coordinator.data = await coordinator._async_update_data()
        program_id = next(p["id"] for p in orbit_programs() if p["device_id"] == BED)
        await coordinator.async_handle_program_event(
            {
                "event": "program_changed",
                "device_id": BED,
                "program_id": program_id,
                "lifecycle_phase": "update",
                "program": {"start_times": ["19:15"]},
            }
        )
        assert upcoming(coordinator, BED).start == at("2026-10-28T19:15")


# --------------------------------------------------------------------------
# Idle Gen 2 timers report watering_status {"clear_on_idle": true}
# --------------------------------------------------------------------------


class TestIdleSentinel:
    """``{"clear_on_idle": true}`` means idle, not watering."""

    def test_watering_in_progress(self) -> None:
        """Only a status naming a station (or stations) is watering."""
        assert not watering_in_progress({})
        assert not watering_in_progress({"watering_status": None})
        assert not watering_in_progress({"watering_status": {"clear_on_idle": True}})
        assert watering_in_progress(
            {"watering_status": {"clear_on_idle": True, "current_station": 1}}
        )
        assert watering_in_progress(
            {"watering_status": {"stations": [{"station": 1, "run_time": 5}]}}
        )

    async def test_stale_manual_mode_is_corrected_when_idle(
        self, hass: HomeAssistant
    ) -> None:
        """
        A poll reporting "manual" for an idle Gen 2 timer reverts to its mode.

        The truthy idle dict used to read as "still watering", keeping the
        stale "manual".
        """
        coordinator = make_coordinator(hass)
        coordinator._remember_mode(BED, {"run_mode": "auto"})
        polled = device(BED)
        polled["status"]["run_mode"] = "manual"
        assert polled["status"]["watering_status"] == {"clear_on_idle": True}
        coordinator._reconcile_polled_mode(BED, polled)
        assert polled["status"]["run_mode"] == "auto"

    def test_idle_gen2_valve_is_closed(self, hass: HomeAssistant) -> None:
        """The valve of an idle Gen 2 timer reads closed."""
        coordinator = make_coordinator(hass)
        bed = device(BED)
        coordinator.data = {"devices": {BED: {"device": bed}}, "programs": {}}
        valve = BHyveZoneValve(coordinator, bed, bed["zones"][0], "Flower Bed", [])
        assert bed["status"]["watering_status"] == {"clear_on_idle": True}
        assert valve.is_closed is True
        bed["status"]["watering_status"] = {
            "clear_on_idle": True,
            "current_station": 1,
        }
        assert valve.is_closed is False


# --------------------------------------------------------------------------
# Auto-adding devices new to the account
# --------------------------------------------------------------------------


class TestNewDeviceIds:
    """Which account devices are new since the options were last chosen."""

    def test_unrecorded_known_devices_add_nothing(self) -> None:
        """Until the account's devices are recorded, nothing counts as new."""
        options = {CONF_DEVICES: GEN1_TIMERS, CONF_AUTO_ADD: True}
        assert new_leaf_device_ids(options, orbit_devices()) == []

    def test_seeding_records_every_device_once(self) -> None:
        """A migrated entry: the account's devices become known, no hubs."""
        options = {CONF_DEVICES: GEN1_TIMERS, CONF_AUTO_ADD: True}
        seeded = options_with_known_devices_seeded(options, orbit_devices())
        assert seeded is not None
        assert set(seeded[CONF_KNOWN_DEVICES]) == {*GEN1_TIMERS, HEDGE, BED}
        assert seeded[CONF_DEVICES] == GEN1_TIMERS
        assert options_with_known_devices_seeded(seeded, orbit_devices()) is None

    def test_auto_add_off_adds_nothing(self) -> None:
        """The user said no."""
        options = {
            CONF_DEVICES: GEN1_TIMERS,
            CONF_AUTO_ADD: False,
            CONF_KNOWN_DEVICES: GEN1_TIMERS,
        }
        assert new_leaf_device_ids(options, orbit_devices()) == []

    def test_new_timers_are_found_hubs_never(self) -> None:
        """The two Gen 2 timers are new; their hub isn't a choosable device."""
        options = {
            CONF_DEVICES: GEN1_TIMERS,
            CONF_AUTO_ADD: True,
            CONF_KNOWN_DEVICES: GEN1_TIMERS,
        }
        assert new_leaf_device_ids(options, orbit_devices()) == [HEDGE, BED]

    def test_deselected_device_stays_deselected(self) -> None:
        """Known but not selected: the user turned it off; leave it off."""
        known = [*GEN1_TIMERS, HEDGE, BED]
        options = {
            CONF_DEVICES: GEN1_TIMERS,
            CONF_AUTO_ADD: True,
            CONF_KNOWN_DEVICES: known,
        }
        assert new_leaf_device_ids(options, orbit_devices()) == []

    def test_options_with_new_devices(self) -> None:
        """New ids join both the selection and the known list."""
        options = {
            CONF_DEVICES: ["x"],
            CONF_AUTO_ADD: True,
            CONF_KNOWN_DEVICES: ["x", "y"],
        }
        assert options_with_new_devices(options, ["z"]) == {
            CONF_DEVICES: ["x", "z"],
            CONF_AUTO_ADD: True,
            CONF_KNOWN_DEVICES: ["x", "y", "z"],
        }


# --------------------------------------------------------------------------
# Whole-integration tests with a fake Orbit cloud behind the real client
# --------------------------------------------------------------------------


class FakeResponse:
    """aiohttp response stand-in."""

    def __init__(self, payload: Any) -> None:
        """Hold the JSON payload."""
        self._payload = payload

    def raise_for_status(self) -> None:
        """Succeed: always 200."""

    async def json(self, content_type: str | None = None) -> Any:  # noqa: ARG002
        """Return the payload."""
        return copy.deepcopy(self._payload)

    async def __aenter__(self) -> Self:
        """Enter."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit."""


class FakeWsMessage:
    """aiohttp WSMessage stand-in."""

    def __init__(self, msg_type: Any, data: str = "") -> None:
        """Hold type and data."""
        self.type = msg_type
        self.data = data


class FakeOrbitWebsocket:
    """Orbit's event stream: records what the client sends, closes on demand."""

    def __init__(self, cloud: FakeOrbitCloud) -> None:
        """Start open."""
        self.cloud = cloud
        self.closed = False
        self._inbox: asyncio.Queue = asyncio.Queue()

    def exception(self) -> None:
        """No error."""

    async def send_str(self, text: str) -> None:
        """Record an outgoing message."""
        self.cloud.ws_sent.append(json.loads(text))

    async def receive(self) -> FakeWsMessage:
        """Next pushed event (or the close)."""
        return await self._inbox.get()

    async def close(self) -> None:
        """Close from our side."""
        self.closed = True
        await self._inbox.put(FakeWsMessage(WSMsgType.CLOSED))

    async def drop(self) -> None:
        """Orbit drops the connection (forces a reconnect)."""
        await self._inbox.put(FakeWsMessage(WSMsgType.CLOSE))

    async def __aenter__(self) -> Self:
        """Enter."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit."""
        self.closed = True


class FakeOrbitCloud:
    """The aiohttp session the real BHyveClient talks to; records every request."""

    def __init__(self, devices: list | None = None) -> None:
        """Serve the fixture."""
        self.devices = devices if devices is not None else orbit_devices()
        self.programs = orbit_programs()
        self.requests: list[tuple[str, str]] = []
        self.ws_sent: list[dict] = []
        self.sockets: list[FakeOrbitWebsocket] = []

    def request(self, method: str, url: str, **_kwargs: Any) -> FakeResponse:
        """Answer a REST call."""
        path = url.split("api.orbitbhyve.com", 1)[-1]
        self.requests.append((method.upper(), path))
        if path == "/v1/session":
            return FakeResponse({"orbit_api_key": "fake-session"})
        if path == "/v1/devices":
            return FakeResponse(self.devices)
        if path == "/v1/sprinkler_timer_programs":
            return FakeResponse(self.programs)
        if path.startswith("/v1/watering_events/"):
            return FakeResponse([])
        if path.startswith("/v1/landscape_descriptions/"):
            return FakeResponse([])
        return FakeResponse({})

    def ws_connect(self, *_args: Any, **_kwargs: Any) -> FakeOrbitWebsocket:
        """Open Orbit's event stream."""
        ws = FakeOrbitWebsocket(self)
        self.sockets.append(ws)
        return ws

    def writes(self) -> list[tuple[str, str]]:
        """Every REST call except the login and reads."""
        return [(m, p) for m, p in self.requests if m != "GET" and p != "/v1/session"]

    def ws_commands(self) -> list[dict]:
        """Every websocket message except the session hello and keepalives."""
        return [
            m for m in self.ws_sent if m.get("event") not in ("app_connection", "ping")
        ]


def patched_client(cloud: FakeOrbitCloud) -> Any:
    """Return the real BHyveClient, bound to the fake cloud instead of aiohttp."""

    def factory(username: str, password: str, session: Any = None) -> BHyveClient:  # noqa: ARG001
        return BHyveClient(username, password, session=cloud)

    return factory


def entry_with(options: dict, minor_version: int = 2) -> MockConfigEntry:
    """Return a bhyve config entry with these options (1: from before auto-add)."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        unique_id="user@example.com",
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "password"},
        options=options,
        version=1,
        minor_version=minor_version,
    )


async def set_up(
    hass: HomeAssistant, entry: MockConfigEntry, cloud: FakeOrbitCloud
) -> None:
    """Set up the entry against the fake cloud."""
    entry.add_to_hass(hass)
    with patch("custom_components.bhyve.BHyveClient", patched_client(cloud)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.usefixtures("enable_custom_integrations")
class TestSetup:
    """The integration end to end against the fake cloud."""

    async def test_auto_add_brings_in_new_gen2_timers(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """Gen 2 timers new since the options were chosen appear with all entities."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        entry = entry_with(
            {
                CONF_DEVICES: GEN1_TIMERS,
                CONF_AUTO_ADD: True,
                CONF_KNOWN_DEVICES: GEN1_TIMERS,
            }
        )
        cloud = FakeOrbitCloud()
        await set_up(hass, entry, cloud)

        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, HEDGE, BED]
        assert entry.options[CONF_KNOWN_DEVICES] == [*GEN1_TIMERS, HEDGE, BED]

        ids = {
            e.entity_id
            for e in er.async_entries_for_config_entry(
                er.async_get(hass), entry.entry_id
            )
        }
        for expected in (
            "valve.hedge_zone",
            "sensor.hedge_next_watering",
            "sensor.hedge_battery_level",
            "sensor.hedge_zone_history",
            "sensor.hedge_state",
            "switch.hedge_rain_delay",
            "switch.hedge_smart_watering",
            "switch.hedge_hedge_program",
            "switch.hedge_trees_program",
            "select.hedge_device_mode",
            "binary_sensor.hedge_fault",
            "valve.flower_bed_zone",
            "sensor.flower_bed_next_watering",
            "sensor.flower_bed_battery_level",
            "switch.flower_bed_program_a_program",
            "binary_sensor.gen_2_hub_connected",
        ):
            assert expected in ids, expected

        assert hass.states.get("valve.hedge_zone").state == "closed"
        assert hass.states.get("valve.flower_bed_zone").state == "closed"
        assert hass.states.get("sensor.hedge_battery_level").state == "43"
        assert hass.states.get("sensor.flower_bed_battery_level").state == "76"
        assert hass.states.get("sensor.hedge_state").state == "auto"
        assert hass.states.get("switch.hedge_hedge_program").state == "on"
        assert hass.states.get("switch.hedge_trees_program").state == "off"
        assert hass.states.get("switch.flower_bed_program_a_program").state == "on"
        assert hass.states.get("binary_sensor.gen_2_hub_connected").state == "on"

        nxt = hass.states.get("sensor.hedge_next_watering")
        assert datetime.fromisoformat(nxt.state) == at("2026-10-29T06:00")
        assert nxt.attributes["programs"] == ["a"]
        assert nxt.attributes["computed_from_program"] is True
        bed = hass.states.get("sensor.flower_bed_next_watering")
        assert datetime.fromisoformat(bed.state) == at("2026-10-30T04:00")

        # Gen 1 timers are untouched: Orbit's own next watering, not marked.
        veggie = hass.states.get("sensor.vegetable_garden_next_watering")
        assert datetime.fromisoformat(veggie.state) == at("2026-10-30T04:00")
        assert "computed_from_program" not in veggie.attributes

        # The Gen 2 timers hang off the Gen 2 hub in the device registry.
        registry = dr.async_get(hass)
        hub = registry.async_get_device_by_identifier(
            (DOMAIN, GEN2_HUB), entry.entry_id
        )
        hedge = registry.async_get_device_by_identifier((DOMAIN, HEDGE), entry.entry_id)
        assert hedge.via_device_id == hub.id
        assert hedge.model == "HT25A-0001"

    async def test_entry_from_before_auto_add_is_migrated(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """
        An existing setup gets auto-add without opening the options (review, #510).

        Devices already on the account keep the user's choice; one added to
        the account afterwards appears.
        """
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        without_bed = [d for d in orbit_devices() if d["id"] != BED]
        cloud = FakeOrbitCloud(devices=without_bed)
        entry = entry_with({CONF_DEVICES: GEN1_TIMERS}, minor_version=1)
        await set_up(hass, entry, cloud)

        assert entry.minor_version == 2
        assert entry.options[CONF_AUTO_ADD] is True
        assert set(entry.options[CONF_KNOWN_DEVICES]) == {*GEN1_TIMERS, HEDGE}
        assert entry.options[CONF_DEVICES] == GEN1_TIMERS
        assert hass.states.get("valve.hedge_zone") is None
        assert hass.states.get("valve.vegetable_garden_zone") is not None

        cloud.devices = orbit_devices()
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        coordinator.client._last_poll_devices = 0
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, BED]
        assert hass.states.get("valve.flower_bed_zone") is not None
        assert hass.states.get("valve.hedge_zone") is None

    async def test_new_timer_while_running_appears_without_a_reload(
        self, hass: HomeAssistant, freezer: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        A timer added to the account later appears after the next poll.

        Only its entities are added: same login, same websocket, the other
        entities never drop out (review, #510).
        """
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        without_bed = [d for d in orbit_devices() if d["id"] != BED]
        cloud = FakeOrbitCloud(devices=without_bed)
        known = [*GEN1_TIMERS, HEDGE]
        entry = entry_with(
            {CONF_DEVICES: known, CONF_AUTO_ADD: True, CONF_KNOWN_DEVICES: known}
        )
        await set_up(hass, entry, cloud)
        assert hass.states.get("valve.flower_bed_zone") is None
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        logins = cloud.requests.count(("POST", "/v1/session"))

        seen: list[str] = []
        hass.bus.async_listen(
            "state_changed",
            lambda event: (
                seen.append(event.data["entity_id"])
                if event.data["new_state"] is None
                or event.data["new_state"].state == "unavailable"
                else None
            ),
        )

        cloud.devices = orbit_devices()
        coordinator.client._last_poll_devices = 0
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert BED in entry.options[CONF_DEVICES]
        assert entry.state is ConfigEntryState.LOADED
        assert hass.data[DOMAIN][entry.entry_id]["coordinator"] is coordinator
        assert cloud.requests.count(("POST", "/v1/session")) == logins
        assert len(cloud.sockets) == 1
        assert seen == []
        assert hass.states.get("valve.flower_bed_zone").state == "closed"
        nxt = hass.states.get("sensor.flower_bed_next_watering")
        assert datetime.fromisoformat(nxt.state) == at("2026-10-30T04:00")
        assert hass.states.get("switch.flower_bed_program_a_program").state == "on"
        # Nothing already there was created a second time.
        assert "already exists" not in caplog.text
        assert hass.states.get("switch.hedge_hedge_program_2") is None
        registry = dr.async_get(hass)
        hub = registry.async_get_device_by_identifier(
            (DOMAIN, GEN2_HUB), entry.entry_id
        )
        bed = registry.async_get_device_by_identifier((DOMAIN, BED), entry.entry_id)
        assert bed.via_device_id == hub.id

    async def test_new_timer_on_a_new_hub_reloads(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """A new hub has to be registered first, so that case still reloads."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        gen1_only = [
            d for d in orbit_devices() if d["id"] not in (HEDGE, BED, GEN2_HUB)
        ]
        cloud = FakeOrbitCloud(devices=gen1_only)
        entry = entry_with(
            {
                CONF_DEVICES: GEN1_TIMERS,
                CONF_AUTO_ADD: True,
                CONF_KNOWN_DEVICES: GEN1_TIMERS,
            }
        )
        await set_up(hass, entry, cloud)
        assert hass.states.get("valve.hedge_zone") is None

        cloud.devices = orbit_devices()
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        coordinator.client._last_poll_devices = 0
        with patch("custom_components.bhyve.BHyveClient", patched_client(cloud)):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert hass.states.get("valve.hedge_zone") is not None
        assert hass.states.get("binary_sensor.gen_2_hub_connected") is not None

    async def test_setup_refresh_and_reconnect_never_write(
        self, hass: HomeAssistant
    ) -> None:
        """
        Setup, polling and a websocket reconnect only read.

        The only non-GET request is the login (POST /v1/session); the only
        websocket messages are the session hello and keepalive pings. No
        program PUT, no device PUT, no landscape PUT, no watering or mode
        command — those happen only from explicit service calls.
        """
        entry = entry_with(
            {
                CONF_DEVICES: GEN1_TIMERS,
                CONF_AUTO_ADD: True,
                CONF_KNOWN_DEVICES: GEN1_TIMERS,
            }
        )
        cloud = FakeOrbitCloud()
        with patch("custom_components.bhyve.pybhyve.websocket.RECONNECT_DELAY", 0):
            await set_up(hass, entry, cloud)
            coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
            for _ in range(3):
                coordinator.client._last_poll_devices = 0
                coordinator.client._last_poll_programs = 0
                await coordinator.async_refresh()
            await hass.async_block_till_done()
            # Orbit drops the event stream; the client reconnects.
            await cloud.sockets[-1].drop()
            for _ in range(20):
                await asyncio.sleep(0.05)
                if len(cloud.sockets) > 1:
                    break
            await hass.async_block_till_done()

        assert len(cloud.sockets) >= 2, "the websocket reconnected"
        assert ("POST", "/v1/session") in cloud.requests
        assert cloud.writes() == []
        assert cloud.ws_commands() == []
        hellos = [m for m in cloud.ws_sent if m.get("event") == "app_connection"]
        assert len(hellos) == len(cloud.sockets)

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


# --------------------------------------------------------------------------
# Config and options flows record what the user was shown
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
class TestFlows:
    """known_devices = everything offered; auto-add defaults on."""

    async def test_options_flow_records_known_devices_and_auto_add(
        self, hass: HomeAssistant
    ) -> None:
        """Submitting the options remembers every device it offered."""
        entry = entry_with({CONF_DEVICES: GEN1_TIMERS})
        cloud = FakeOrbitCloud()
        await set_up(hass, entry, cloud)

        with patch("custom_components.bhyve.BHyveClient", patched_client(cloud)):
            result = await hass.config_entries.options.async_init(entry.entry_id)
            assert result["type"] is FlowResultType.FORM
            schema = result["data_schema"].schema
            offered = next(k for k in schema if k == CONF_DEVICES)
            assert set(schema[offered].options) == {*GEN1_TIMERS, HEDGE, BED}
            auto = next(k for k in schema if k == CONF_AUTO_ADD)
            assert auto.default() is True

            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                {CONF_DEVICES: [*GEN1_TIMERS, HEDGE, BED], CONF_AUTO_ADD: True},
            )
            await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, HEDGE, BED]
        assert entry.options[CONF_AUTO_ADD] is True
        assert set(entry.options[CONF_KNOWN_DEVICES]) == {*GEN1_TIMERS, HEDGE, BED}
        assert hass.states.get("valve.hedge_zone") is not None

    async def test_options_form_ticks_devices_not_added_yet(
        self, hass: HomeAssistant
    ) -> None:
        """
        A device new to the account that no poll has added yet starts ticked.

        Submitting the form as shown must not turn it off for good (review, #510).
        """
        without_bed = [d for d in orbit_devices() if d["id"] != BED]
        cloud = FakeOrbitCloud(devices=without_bed)
        known = [*GEN1_TIMERS, HEDGE]
        entry = entry_with(
            {CONF_DEVICES: GEN1_TIMERS, CONF_AUTO_ADD: True, CONF_KNOWN_DEVICES: known}
        )
        await set_up(hass, entry, cloud)
        cloud.devices = orbit_devices()
        hass.data[DOMAIN][entry.entry_id]["client"]._last_poll_devices = 0

        result = await hass.config_entries.options.async_init(entry.entry_id)
        schema = result["data_schema"].schema
        ticked = next(k for k in schema if k == CONF_DEVICES).default()
        # Hedge was offered before and left unticked: it stays unticked.
        assert set(ticked) == {*GEN1_TIMERS, BED}

    async def test_options_form_ticks_nothing_new_with_auto_add_off(
        self, hass: HomeAssistant
    ) -> None:
        """With auto-add off, only the saved selection is ticked."""
        known = [*GEN1_TIMERS, HEDGE]
        entry = entry_with(
            {CONF_DEVICES: GEN1_TIMERS, CONF_AUTO_ADD: False, CONF_KNOWN_DEVICES: known}
        )
        await set_up(hass, entry, FakeOrbitCloud())
        result = await hass.config_entries.options.async_init(entry.entry_id)
        schema = result["data_schema"].schema
        ticked = next(k for k in schema if k == CONF_DEVICES).default()
        assert set(ticked) == set(GEN1_TIMERS)

    async def test_config_flow_records_known_devices(self, hass: HomeAssistant) -> None:
        """A new entry starts with auto-add on and everything offered known."""
        cloud = FakeOrbitCloud()
        await async_setup_component(hass, "persistent_notification", {})
        with (
            patch(
                "custom_components.bhyve.config_flow.BHyveClient", patched_client(cloud)
            ),
            patch("custom_components.bhyve.BHyveClient", patched_client(cloud)),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "user"}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "password"},
            )
            assert result["step_id"] == "device"
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_DEVICES: [HEDGE], CONF_AUTO_ADD: True}
            )
            await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        options = result["result"].options
        assert options[CONF_DEVICES] == [HEDGE]
        assert options[CONF_AUTO_ADD] is True
        assert set(options[CONF_KNOWN_DEVICES]) == {*GEN1_TIMERS, HEDGE, BED}


# --------------------------------------------------------------------------
# A device gone from the account can be deleted in Home Assistant
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_gone_from_account_can_be_deleted(hass: HomeAssistant) -> None:
    """
    The old Gen 1 "Old Timer" left an empty device behind.

    Home Assistant may delete a device the account no longer has; one the
    account still has stays.
    """
    entry = entry_with({CONF_DEVICES: GEN1_TIMERS})
    cloud = FakeOrbitCloud()
    await set_up(hass, entry, cloud)
    registry = dr.async_get(hass)
    gone = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "timer-flower-bed-old")},
        name="Old Timer",
    )
    present = registry.async_get_device_by_identifier((DOMAIN, VEGGIE), entry.entry_id)
    assert await async_remove_config_entry_device(hass, entry, gone) is True
    assert await async_remove_config_entry_device(hass, entry, present) is False

    # Its data failed to load on the last poll: still on the account, so it
    # still can't be deleted (review, #510).
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    del coordinator.data["devices"][VEGGIE]
    assert await async_remove_config_entry_device(hass, entry, present) is False


class TestNextWateringAttributes:
    """What the Next watering sensor says about where its time came from."""

    def test_computed_time(self) -> None:
        """A computed time: its programs, and that it was computed."""
        assert _next_watering_attributes(
            NextWatering(at("2026-10-29T06:00"), ["a"], computed=True)
        ) == {"programs": ["a"], "computed_from_program": True}

    def test_no_time_says_why(self) -> None:
        """
        Mark an uncomputed time, so nobody reads it as "the timer says none due".

        "unknown" alone doesn't tell a switched-off timer from one with
        nothing scheduled.
        """
        assert _next_watering_attributes(
            NextWatering(None, [], computed=True, unavailable="timer_off")
        ) == {"computed_from_program": True, "next_watering_unavailable": "timer_off"}

    def test_orbit_time_is_unmarked(self) -> None:
        """Gen 1: Orbit's own time, no mark; nothing when Orbit has none."""
        assert _next_watering_attributes(
            NextWatering(at("2026-10-30T04:00"), ["a"])
        ) == {"programs": ["a"]}
        assert _next_watering_attributes(NextWatering(None, [])) == {}


class TestWhyNoNextWatering:
    """When a Gen 2 timer has no computed time, next_watering says why."""

    def test_timer_off(self, freezer: Any) -> None:
        """The timer is off: timer_off."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        bed = device(BED)
        bed["status"]["run_mode"] = "off"
        assert next_watering(bed, orbit_programs()).unavailable == "timer_off"

    def test_rain_delay(self, freezer: Any) -> None:
        """A rain delay in force: rain_delay."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        bed = device(BED)
        bed["status"]["rain_delay"] = 24
        assert next_watering(bed, orbit_programs()).unavailable == "rain_delay"

    def test_smart_program_is_not_computable(self, freezer: Any) -> None:
        """A smart program (or a frequency the code doesn't know): not_computable."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        programs = orbit_programs()
        next(p for p in programs if p["device_id"] == BED)["is_smart_program"] = True
        assert next_watering(device(BED), programs).unavailable == "not_computable"

    def test_program_ended_is_no_upcoming_run(self, freezer: Any) -> None:
        """Every program known and none runs again: no_upcoming_run."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        programs = orbit_programs()
        next(p for p in programs if p["device_id"] == BED)["program_end_date"] = (
            "2026-10-01T00:00:00-07:00"
        )
        assert next_watering(device(BED), programs).unavailable == "no_upcoming_run"

    def test_computed_time_has_no_reason(self, freezer: Any) -> None:
        """A computed time carries no reason."""
        freezer.move_to(at("2026-10-28T09:40").astimezone(UTC))
        assert next_watering(device(BED), orbit_programs()).unavailable is None
