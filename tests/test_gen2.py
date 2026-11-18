"""
Gen 2 hose timers (HT25A-0001 behind a BH1G2 Wi-Fi hub) and auto-adding devices.

The fixtures are cut down from a real account's /v1/devices and
/v1/sprinkler_timer_programs, with placeholder ids, names, MACs and
timestamps. Two Gen 2 timers ("Hedge", "Flower Bed") sit next to two Gen 1
timers. What the Gen 2 timers do differently, from that data:

- status has no ``next_start_time`` / ``next_start_programs`` at all, so the
  "Next watering" sensor stayed unknown;
- they were added after the integration was set up, and the device options
  never offered them, so Home Assistant only showed their hub.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.bhyve import async_remove_config_entry_device
from custom_components.bhyve.const import (
    CONF_AUTO_ADD,
    CONF_DEVICES,
    CONF_KNOWN_DEVICES,
    DOMAIN,
)
from custom_components.bhyve.util import (
    NextWatering,
    next_program_start,
    next_watering,
    watering_in_progress,
)

from .fake_orbit import PASSWORD, USERNAME, FakeOrbitCloud

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

FIXTURES = Path(__file__).parent / "fixtures"
PACIFIC = ZoneInfo("America/Los_Angeles")

HEDGE = "timer-hedge-09"
BED = "timer-flower-bed-11"
GEN2_HUB = "hub-gen2-10"
LAWN = "timer-lawn-03"
RAISED_BED = "timer-raised-bed-08"
GEN1_TIMERS = [LAWN, RAISED_BED]
GEN2 = (HEDGE, BED, GEN2_HUB)


def orbit_devices(*, without: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Return the account's devices, fresh copy."""
    devices = json.loads((FIXTURES / "orbit_devices.json").read_text())
    return [d for d in devices if d["id"] not in without]


def orbit_programs() -> list[dict[str, Any]]:
    """Return the account's programs, fresh copy."""
    return json.loads((FIXTURES / "orbit_programs.json").read_text())


def device(device_id: str) -> dict[str, Any]:
    """One device from the fixture."""
    return next(d for d in orbit_devices() if d["id"] == device_id)


def program_of(timer: str, /, **changes: Any) -> dict[str, Any]:
    """Return the device's enabled program, with these fields changed."""
    program = next(
        p for p in orbit_programs() if p["device_id"] == timer and p["enabled"]
    )
    return {**program, **changes}


def at(text: str) -> datetime:
    """Return a Pacific wall-clock time."""
    return datetime.fromisoformat(text).replace(tzinfo=PACIFIC)


NOW = at("2026-10-28T09:40")  # a Wednesday


class TestNextProgramStart:
    """next_program_start: the timer's next run from its enabled programs."""

    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            # Hedge: every 3 days from May 11 at 06:00.
            ("2026-10-28T09:40", "2026-10-29T06:00"),
            # On a run day before 06:00 the run is today.
            ("2026-10-29T05:59", "2026-10-29T06:00"),
            # At 06:00 exactly the run has started: the next is 3 days later.
            ("2026-10-29T06:00", "2026-11-01T06:00"),
        ],
    )
    def test_interval_program_counts_from_its_start_date(
        self, now: str, expected: str
    ) -> None:
        """An interval program runs every N days from its anchor."""
        result = next_program_start(device(HEDGE), orbit_programs(), at(now))
        assert result == NextWatering(at(expected), ["a"], computed=True)

    @pytest.mark.parametrize(
        ("changes", "expected"),
        [
            # Flower Bed as it is: even days at 04:00; the 28th has passed.
            ({}, "2026-10-30T04:00"),
            # Odd days are calendar parity, like the B-hyve app's label.
            ({"frequency": {"type": "odd"}}, "2026-10-29T04:00"),
            # Day 0 is Sunday.
            ({"frequency": {"type": "days", "days": [0]}}, "2026-11-01T04:00"),
            # Several start times: the first one still ahead.
            ({"start_times": ["21:30", "04:00"]}, "2026-10-28T21:30"),
            # Nothing before program_start_date, however far off it is.
            ({"program_start_date": "2026-11-05T00:00:00-08:00"}, "2026-11-06T04:00"),
            ({"program_start_date": "2027-03-01T00:00:00-08:00"}, "2027-03-02T04:00"),
        ],
    )
    def test_fixed_schedules(self, changes: dict[str, Any], expected: str) -> None:
        """Each frequency this code knows gives the next start."""
        result = next_program_start(device(BED), [program_of(BED, **changes)], NOW)
        assert result == NextWatering(at(expected), ["a"], computed=True)

    def test_interval_first_run_months_ahead(self) -> None:
        """An interval whose first day is far off is found too."""
        frequency = {
            "type": "interval",
            "interval": 3,
            "interval_start_time": "2027-02-10T00:00:00-08:00",
        }
        hedge = program_of(HEDGE, frequency=frequency)
        result = next_program_start(device(HEDGE), [hedge], NOW)
        assert result.start == at("2027-02-10T06:00")

    def test_even_days_across_the_dst_change(self) -> None:
        """Nov 1 2026 is the fall-back day; Nov 2 04:00 is PST (-08:00)."""
        result = next_program_start(
            device(BED), orbit_programs(), at("2026-10-31T07:00")
        )
        assert result.start == at("2026-11-02T04:00")
        assert result.start.utcoffset() == timedelta(hours=-8)

    def test_start_in_the_repeated_hour_is_not_reported_once_past(self) -> None:
        """01:45 PDT has passed by the second 01:30 (PST) of the fall-back day."""
        second_pass = datetime(2026, 11, 1, 1, 30, tzinfo=PACIFIC, fold=1)
        bed = program_of(BED, frequency={"type": "odd"}, start_times=["01:45"])
        result = next_program_start(device(BED), [bed], second_pass)
        assert result.start == at("2026-11-03T01:45")

    def test_two_programs_same_time_both_named(self) -> None:
        """Two programs starting together are both listed, in letter order."""
        second = program_of(BED, id="prog-b", program="b")
        result = next_program_start(device(BED), [second, program_of(BED)], NOW)
        assert result == NextWatering(at("2026-10-30T04:00"), ["a", "b"], computed=True)

    @pytest.mark.parametrize(
        "changes",
        [
            {"program_end_date": "2026-10-01T00:00:00-07:00"},
            {"run_times": [{"station": 1, "run_time": 0}]},
            {"enabled": False},
            {"program": None},
            {"device_id": "another-timer"},
        ],
    )
    def test_no_upcoming_run(self, changes: dict[str, Any]) -> None:
        """A program that has ended, waters nothing or isn't the timer's."""
        result = next_program_start(device(BED), [program_of(BED, **changes)], NOW)
        assert result == NextWatering(
            None, [], computed=True, unavailable="no_upcoming_run"
        )

    @pytest.mark.parametrize(
        "changes",
        [
            {"is_smart_program": True},
            {"frequency": {"type": "interval_hours", "interval_hours": 6}},
            {"frequency": {"type": "interval", "interval": 3}, "program_start_date": 0},
            {"frequency": {"type": "interval", "interval": 5000}},
            {"start_times": []},
        ],
    )
    def test_not_computable(self, changes: dict[str, Any]) -> None:
        """A smart program or a schedule this code can't read is not guessed."""
        result = next_program_start(device(BED), [program_of(BED, **changes)], NOW)
        assert result == NextWatering(
            None, [], computed=True, unavailable="not_computable"
        )

    def test_one_unreadable_program_hides_the_others(self) -> None:
        """A smart program may run first, so a fixed one's time isn't shown."""
        smart = program_of(BED, id="prog-smart", program="e", is_smart_program=True)
        result = next_program_start(device(BED), [program_of(BED), smart], NOW)
        assert result.start is None
        assert result.unavailable == "not_computable"


@pytest.fixture
def now(freezer: FrozenDateTimeFactory) -> None:
    """Freeze the clock at NOW."""
    freezer.move_to(NOW.astimezone(UTC))


@pytest.mark.usefixtures("now")
class TestNextWatering:
    """next_watering: Orbit's time, else one worked out from the programs."""

    def test_gen2_timer_gets_a_computed_time(self) -> None:
        """Orbit sends a Gen 2 timer no time at all."""
        assert "next_start_time" not in device(HEDGE)["status"]
        assert next_watering(device(HEDGE), orbit_programs()) == NextWatering(
            at("2026-10-29T06:00"), ["a"], computed=True
        )

    def test_orbit_reported_time_is_used(self) -> None:
        """Gen 1 timers: Orbit's own value, not marked as computed."""
        assert next_watering(device(RAISED_BED), orbit_programs()) == NextWatering(
            at("2026-10-30T04:00"), ["a"]
        )

    @pytest.mark.parametrize("sent", [None, "2106-02-07T06:28:15.000Z", "garbage"])
    def test_unusable_orbit_time_is_computed(self, sent: Any) -> None:
        """Orbit's null, its 2106 placeholder or junk counts as no time."""
        bed = device(BED)
        bed["status"]["next_start_time"] = sent
        assert next_watering(bed, orbit_programs()) == NextWatering(
            at("2026-10-30T04:00"), ["a"], computed=True
        )

    @pytest.mark.parametrize(
        ("status", "reason"),
        [({"run_mode": "off"}, "timer_off"), ({"rain_delay": 24}, "rain_delay")],
    )
    def test_timer_off_or_delayed_says_why(
        self, status: dict[str, Any], reason: str
    ) -> None:
        """No time while the timer is off or a rain delay is in force."""
        bed = device(BED)
        bed["status"].update(status)
        assert next_watering(bed, orbit_programs()) == NextWatering(
            None, [], computed=True, unavailable=reason
        )

    def test_unexpected_program_data_is_not_an_error(self) -> None:
        """A field of a type Orbit hasn't sent before gives no time, no crash."""
        bed = program_of(BED, run_times=[{"station": 1, "run_time": "45"}])
        assert next_watering(device(BED), [bed]).unavailable == "not_computable"


def test_watering_in_progress() -> None:
    """``{"clear_on_idle": true}`` means idle; a station means watering."""
    assert not watering_in_progress({})
    assert not watering_in_progress({"watering_status": None})
    assert not watering_in_progress({"watering_status": {"clear_on_idle": True}})
    assert watering_in_progress(
        {"watering_status": {"clear_on_idle": True, "current_station": 1}}
    )
    assert watering_in_progress(
        {"watering_status": {"stations": [{"station": 1, "run_time": 5}]}}
    )


# End to end: the real client, coordinator and entities against a fake cloud.


@pytest.fixture
def cloud() -> FakeOrbitCloud:
    """Return a fake Orbit cloud serving the fixture account."""
    return FakeOrbitCloud(devices=orbit_devices(), programs=orbit_programs())


@pytest.fixture
async def connected(
    hass: HomeAssistant,
    cloud: FakeOrbitCloud,
    now: None,  # noqa: ARG001
    enable_custom_integrations: None,  # noqa: ARG001
) -> AsyncIterator[None]:
    """Route the integration's HTTP session to the fake cloud."""
    with (
        patch("custom_components.bhyve.async_get_clientsession", return_value=cloud),
        patch(
            "custom_components.bhyve.config_flow.async_get_clientsession",
            return_value=cloud,
        ),
    ):
        yield
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_unload(entry.entry_id)
        await settle(hass)


async def settle(hass: HomeAssistant) -> None:
    """Let HA jobs and the websocket's own task process pending messages."""
    for _ in range(3):
        await hass.async_block_till_done(wait_background_tasks=True)
        await asyncio.sleep(0)


async def poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Move the clock past the next poll."""
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await settle(hass)


async def set_up(
    hass: HomeAssistant,
    devices: list[str],
    *,
    known: list[str] | None = None,
    auto_add: bool | None = True,
    minor_version: int = 2,
) -> MockConfigEntry:
    """Set up an entry with these devices selected (known: same, unless given)."""
    options: dict[str, Any] = {
        CONF_DEVICES: devices,
        CONF_KNOWN_DEVICES: devices if known is None else known,
    }
    if auto_add is not None:
        options[CONF_AUTO_ADD] = auto_add
    if minor_version == 1:
        options = {CONF_DEVICES: devices}
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=USERNAME,
        data={CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD},
        options=options,
        minor_version=minor_version,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    return entry


def next_watering_state(hass: HomeAssistant, name: str) -> datetime | None:
    """Return a Next watering sensor's time."""
    state = hass.states.get(f"sensor.{name}_next_watering")
    assert state is not None
    return None if state.state == "unknown" else datetime.fromisoformat(state.state)


@pytest.mark.usefixtures("connected")
class TestGen2Timers:
    """Gen 2 timers once they are in Home Assistant."""

    async def test_next_watering_and_devices(self, hass: HomeAssistant) -> None:
        """Computed for Gen 2, Orbit's own for Gen 1; timers hang off their hub."""
        entry = await set_up(hass, [*GEN1_TIMERS, HEDGE, BED])

        hedge = hass.states.get("sensor.hedge_next_watering")
        assert datetime.fromisoformat(hedge.state) == at("2026-10-29T06:00")
        assert hedge.attributes["programs"] == ["a"]
        assert hedge.attributes["computed_from_program"] is True
        valve = hass.states.get("valve.hedge_zone")
        assert valve.state == "closed"
        assert datetime.fromisoformat(valve.attributes["next_start_time"]) == at(
            "2026-10-29T06:00"
        )
        assert valve.attributes["next_start_programs"] == ["a"]

        gen1 = hass.states.get("sensor.raised_bed_next_watering")
        assert datetime.fromisoformat(gen1.state) == at("2026-10-30T04:00")
        assert "computed_from_program" not in gen1.attributes

        registry = dr.async_get(hass)
        hub = registry.async_get_device_by_identifier(
            (DOMAIN, GEN2_HUB), entry.entry_id
        )
        timer = registry.async_get_device_by_identifier((DOMAIN, HEDGE), entry.entry_id)
        assert timer.via_device_id == hub.id
        assert timer.model == "HT25A-0001"

    async def test_mode_change_shows_at_once(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud
    ) -> None:
        """Off, then back on, by websocket: no wait for a poll."""
        await set_up(hass, [BED])
        assert next_watering_state(hass, "flower_bed") == at("2026-10-30T04:00")

        cloud.socket.push({"event": "change_mode", "device_id": BED, "mode": "off"})
        await settle(hass)
        state = hass.states.get("sensor.flower_bed_next_watering")
        assert state.state == "unknown"
        assert state.attributes["next_watering_unavailable"] == "timer_off"

        cloud.socket.push({"event": "change_mode", "device_id": BED, "mode": "auto"})
        await settle(hass)
        assert next_watering_state(hass, "flower_bed") == at("2026-10-30T04:00")

    async def test_program_change_moves_it(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud
    ) -> None:
        """A program edit in the B-hyve app moves the computed time."""
        await set_up(hass, [BED])
        cloud.socket.push(
            {
                "event": "program_changed",
                "device_id": BED,
                "program_id": program_of(BED)["id"],
                "lifecycle_phase": "update",
                "program": {"start_times": ["19:15"]},
            }
        )
        await settle(hass)
        assert next_watering_state(hass, "flower_bed") == at("2026-10-28T19:15")

    async def test_stale_manual_mode_is_corrected_when_idle(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
    ) -> None:
        """
        A poll reporting "manual" for an idle timer reverts to its own mode.

        The idle marker ``{"clear_on_idle": true}`` used to read as "still
        watering", which kept the stale "manual".
        """
        await set_up(hass, [BED])
        assert hass.states.get("sensor.flower_bed_state").state == "auto"
        status = cloud.device(BED)["status"]
        assert status["watering_status"] == {"clear_on_idle": True}
        status["run_mode"] = "manual"
        await poll(hass, freezer)
        assert hass.states.get("sensor.flower_bed_state").state == "auto"


@pytest.mark.usefixtures("connected")
class TestAutoAdd:
    """Devices added to the account after the integration was set up."""

    async def test_new_timers_are_added_at_setup(self, hass: HomeAssistant) -> None:
        """Timers the user was never offered are selected and loaded."""
        entry = await set_up(hass, GEN1_TIMERS)
        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, HEDGE, BED]
        assert entry.options[CONF_KNOWN_DEVICES] == [*GEN1_TIMERS, HEDGE, BED]
        assert hass.states.get("valve.hedge_zone") is not None
        assert hass.states.get("valve.flower_bed_zone") is not None

    async def test_entry_from_before_auto_add_is_migrated(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
    ) -> None:
        """
        An existing setup gets auto-add without opening the options.

        Devices already on the account keep the user's choice; one added to
        the account afterwards appears.
        """
        cloud.devices = orbit_devices(without=(BED,))
        entry = await set_up(hass, GEN1_TIMERS, minor_version=1)

        assert entry.minor_version == 2
        assert entry.options == {
            CONF_DEVICES: GEN1_TIMERS,
            CONF_AUTO_ADD: True,
            CONF_KNOWN_DEVICES: [*GEN1_TIMERS, HEDGE],
        }
        assert hass.states.get("valve.hedge_zone") is None
        assert hass.states.get("valve.raised_bed_zone") is not None

        cloud.devices = orbit_devices()
        await poll(hass, freezer)
        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, BED]
        assert hass.states.get("valve.flower_bed_zone") is not None
        assert hass.states.get("valve.hedge_zone") is None

    async def test_options_saved_by_an_older_version_still_auto_add(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
    ) -> None:
        """After a downgrade the old options form drops the new keys."""
        cloud.devices = orbit_devices(without=(BED,))
        entry = await set_up(hass, GEN1_TIMERS, known=[], auto_add=None)
        entry_options = dict(entry.options)
        del entry_options[CONF_KNOWN_DEVICES]
        hass.config_entries.async_update_entry(entry, options=entry_options)
        await poll(hass, freezer)
        assert entry.options[CONF_KNOWN_DEVICES] == [*GEN1_TIMERS, HEDGE]

        cloud.devices = orbit_devices()
        await poll(hass, freezer)
        assert hass.states.get("valve.flower_bed_zone") is not None

    async def test_new_timer_appears_without_a_reload(
        self,
        hass: HomeAssistant,
        cloud: FakeOrbitCloud,
        freezer: FrozenDateTimeFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """
        A timer added to the account later appears after the next poll.

        Only its entities are added: same login, same websocket, and the
        other entities never drop out.
        """
        cloud.devices = orbit_devices(without=(BED,))
        entry = await set_up(hass, [*GEN1_TIMERS, HEDGE])
        assert hass.states.get("valve.flower_bed_zone") is None
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

        dropped: list[str] = []
        hass.bus.async_listen(
            "state_changed",
            lambda event: (
                dropped.append(event.data["entity_id"])
                if event.data["new_state"] is None
                or event.data["new_state"].state == "unavailable"
                else None
            ),
        )

        cloud.devices = orbit_devices()
        await poll(hass, freezer)

        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, HEDGE, BED]
        assert entry.state is ConfigEntryState.LOADED
        assert hass.data[DOMAIN][entry.entry_id]["coordinator"] is coordinator
        assert cloud.logins == 1
        assert len(cloud.sockets) == 1
        assert dropped == []
        assert hass.states.get("valve.flower_bed_zone").state == "closed"
        assert next_watering_state(hass, "flower_bed") == at("2026-10-30T04:00")
        assert hass.states.get("switch.flower_bed_mornings_program").state == "on"
        # Nothing already there was created a second time.
        assert "already exists" not in caplog.text
        assert hass.states.get("switch.hedge_hedge_program_2") is None
        registry = dr.async_get(hass)
        hub = registry.async_get_device_by_identifier(
            (DOMAIN, GEN2_HUB), entry.entry_id
        )
        bed = registry.async_get_device_by_identifier((DOMAIN, BED), entry.entry_id)
        assert bed.via_device_id == hub.id

    @pytest.mark.parametrize("arriving", [GEN2, (GEN2_HUB,)])
    async def test_new_hub_reloads(
        self,
        hass: HomeAssistant,
        cloud: FakeOrbitCloud,
        freezer: FrozenDateTimeFactory,
        arriving: tuple[str, ...],
    ) -> None:
        """A hub has to be registered before its timers, so that case reloads."""
        cloud.devices = orbit_devices(without=GEN2)
        entry = await set_up(hass, GEN1_TIMERS)

        cloud.devices = orbit_devices(without=tuple(set(GEN2) - set(arriving)))
        await poll(hass, freezer)

        assert entry.state is ConfigEntryState.LOADED
        assert cloud.logins == 2
        assert hass.states.get("binary_sensor.gen_2_hub_connected") is not None
        assert (hass.states.get("valve.hedge_zone") is not None) == (HEDGE in arriving)

    async def test_timer_not_paired_yet_waits_for_its_status(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
    ) -> None:
        """A timer first seen with no status is added once it has one, complete."""
        cloud.devices = orbit_devices(without=(BED,))
        entry = await set_up(hass, [*GEN1_TIMERS, HEDGE])

        cloud.devices = orbit_devices()
        status = cloud.device(BED).pop("status")
        await poll(hass, freezer)
        assert BED in entry.options[CONF_DEVICES]
        assert hass.states.get("sensor.flower_bed_battery_level") is None

        cloud.device(BED)["status"] = status
        await poll(hass, freezer)
        assert hass.states.get("valve.flower_bed_zone") is not None
        assert hass.states.get("switch.flower_bed_rain_delay") is not None

    async def test_auto_add_off_adds_nothing(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
    ) -> None:
        """The user said no."""
        cloud.devices = orbit_devices(without=(BED,))
        entry = await set_up(hass, [*GEN1_TIMERS, HEDGE], auto_add=False)
        cloud.devices = orbit_devices()
        await poll(hass, freezer)
        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, HEDGE]
        assert hass.states.get("valve.flower_bed_zone") is None

    async def test_device_gone_from_the_account_can_be_deleted_and_come_back(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
    ) -> None:
        """
        Home Assistant may delete a device the account no longer has.

        One the account still has can't be deleted, even if its data failed
        to load on the last poll. A deleted one that returns to the account
        gets its entities again.
        """
        entry = await set_up(hass, [*GEN1_TIMERS, HEDGE, BED])
        registry = dr.async_get(hass)
        bed = registry.async_get_device_by_identifier((DOMAIN, BED), entry.entry_id)
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        del coordinator.data["devices"][BED]
        assert await async_remove_config_entry_device(hass, entry, bed) is False

        cloud.devices = orbit_devices(without=(BED,))
        await poll(hass, freezer)
        assert await async_remove_config_entry_device(hass, entry, bed) is True
        registry.async_remove_device(bed.id)
        await settle(hass)
        assert hass.states.get("valve.flower_bed_zone") is None

        cloud.devices = orbit_devices()
        await poll(hass, freezer)
        assert hass.states.get("valve.flower_bed_zone") is not None


@pytest.mark.usefixtures("connected")
class TestFlows:
    """The config and options flows record what the user was offered."""

    async def test_config_flow_records_known_devices(self, hass: HomeAssistant) -> None:
        """A new entry starts with auto-add on and everything offered known."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD}
        )
        assert result["step_id"] == "device"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICES: [HEDGE], CONF_AUTO_ADD: True}
        )
        await settle(hass)

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["result"].options == {
            CONF_DEVICES: [HEDGE],
            CONF_AUTO_ADD: True,
            CONF_KNOWN_DEVICES: [LAWN, RAISED_BED, HEDGE, BED],
        }

    async def test_deselected_device_stays_out(
        self, hass: HomeAssistant, freezer: FrozenDateTimeFactory
    ) -> None:
        """A device deselected in the options is removed and not added back."""
        entry = await set_up(hass, [*GEN1_TIMERS, HEDGE, BED])
        assert hass.states.get("valve.hedge_zone") is not None

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_DEVICES: [*GEN1_TIMERS, BED], CONF_AUTO_ADD: True},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await settle(hass)
        await poll(hass, freezer)

        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, BED]
        assert HEDGE in entry.options[CONF_KNOWN_DEVICES]
        assert hass.states.get("valve.hedge_zone") is None
        assert hass.states.get("valve.flower_bed_zone") is not None

    @pytest.mark.parametrize(
        ("auto_add", "selected"),
        [(True, [*GEN1_TIMERS, BED]), (False, GEN1_TIMERS)],
    )
    async def test_options_form_selects_devices_not_added_yet(
        self,
        hass: HomeAssistant,
        cloud: FakeOrbitCloud,
        freezer: FrozenDateTimeFactory,
        *,
        auto_add: bool,
        selected: list[str],
    ) -> None:
        """
        A device new to the account that no poll has added yet starts selected.

        Submitting the form as shown must not leave it out for good. Hedge was
        offered before and deselected, so it stays deselected. With auto-add
        off, only the saved selection is selected.
        """
        cloud.devices = orbit_devices(without=(BED,))
        entry = await set_up(
            hass, GEN1_TIMERS, known=[*GEN1_TIMERS, HEDGE], auto_add=auto_add
        )
        cloud.devices = orbit_devices()
        # Past the client's cache of the device list, but no poll has run yet.
        freezer.tick(timedelta(minutes=6))

        result = await hass.config_entries.options.async_init(entry.entry_id)
        schema = result["data_schema"].schema
        devices = next(k for k in schema if k == CONF_DEVICES)
        assert set(schema[devices].options) == {*GEN1_TIMERS, HEDGE, BED}
        assert devices.default() == selected
        assert next(k for k in schema if k == CONF_AUTO_ADD).default() is auto_add

    async def test_device_added_while_the_form_is_open_is_kept(
        self, hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
    ) -> None:
        """A poll auto-adds a timer between the form opening and its submit."""
        cloud.devices = orbit_devices(without=(BED,))
        entry = await set_up(hass, [*GEN1_TIMERS, HEDGE])
        result = await hass.config_entries.options.async_init(entry.entry_id)

        cloud.devices = orbit_devices()
        await poll(hass, freezer)
        assert hass.states.get("valve.flower_bed_zone") is not None

        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_DEVICES: [*GEN1_TIMERS, HEDGE], CONF_AUTO_ADD: True},
        )
        await settle(hass)
        assert entry.options[CONF_DEVICES] == [*GEN1_TIMERS, HEDGE, BED]
        assert hass.states.get("valve.flower_bed_zone") is not None


def test_fixture_programs_are_what_the_tests_assume() -> None:
    """The fixture keeps a disabled program with no letter on a Gen 2 timer."""
    old = next(p for p in orbit_programs() if p["name"] == "Old Schedule")
    assert (old["device_id"], old["enabled"], old["program"]) == (HEDGE, False, None)
    assert copy.deepcopy(device(LAWN))["status"]["watering_status"] == {
        "clear_on_idle": True
    }
