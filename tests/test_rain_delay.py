"""
Test rain delay end times (#447).

Orbit reports a rain delay as a length in hours (rain_delay) counted from
rain_delay_started_at, not as the hours remaining, and moves the start forward
when it re-evaluates a weather delay. These tests pin the end-time arithmetic
and how the switch, sensor and coordinator use it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.sensor import SENSOR_TYPES_SPRINKLER, BHyveSensor
from custom_components.bhyve.switch import (
    BHyveRainDelaySwitch,
    BHyveSwitchEntityDescription,
)
from custom_components.bhyve.util import (
    next_watering_time,
    rain_delay_active,
    rain_delay_end,
    rain_delay_remaining_hours,
)

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

NOW = datetime(2026, 10, 13, 9, 21, tzinfo=UTC)
DEVICE_ID = "sprinkler-1"


@pytest.fixture(autouse=True)
def frozen_now(freezer: FrozenDateTimeFactory) -> None:
    """Freeze time so end times and remaining hours are exact."""
    freezer.move_to(NOW)


def status(hours: float, started: datetime | None) -> dict[str, Any]:
    """Build a device status with a rain delay."""
    result: dict[str, Any] = {"rain_delay": hours}
    if started is not None:
        result["rain_delay_started_at"] = started.isoformat().replace("+00:00", "Z")
    return result


class TestEndTime:
    """The delay ends `rain_delay` hours after it started."""

    def test_end_is_start_plus_delay(self) -> None:
        """A 24h delay that started 2h ago ends in 22h."""
        start = NOW - timedelta(hours=2)

        assert rain_delay_end(status(24, start)) == start + timedelta(hours=24)
        assert rain_delay_active(status(24, start)) is True
        assert rain_delay_remaining_hours(status(24, start)) == 22

    def test_rebaselined_weather_delay(self) -> None:
        """
        Live data from an automatic delay: delay=21 from a start Orbit moved.

        The delay field is not the time left; the end is start + delay.
        """
        start = datetime(2026, 10, 13, 8, 45, 3, tzinfo=UTC)  # 19:45 Sydney

        end = rain_delay_end(status(21, start))

        assert end == datetime(2026, 10, 14, 5, 45, 3, tzinfo=UTC)
        assert rain_delay_remaining_hours(status(21, start)) == 21  # 20h24m left

    def test_remaining_hours_round_up(self) -> None:
        """Any part of an hour left counts as an hour."""
        start = NOW - timedelta(hours=23, minutes=59)

        assert rain_delay_remaining_hours(status(24, start)) == 1

    def test_expired_delay_is_not_active(self) -> None:
        """Regression for #447: a delay past its end is over, whatever Orbit says."""
        start = NOW - timedelta(hours=30)

        assert rain_delay_active(status(24, start)) is False
        assert rain_delay_remaining_hours(status(24, start)) is None

    def test_no_delay(self) -> None:
        """A zero delay has no end and is not active."""
        assert rain_delay_end(status(0, NOW)) is None
        assert rain_delay_active(status(0, NOW)) is False
        assert rain_delay_active({}) is False

    def test_unknown_start_keeps_delay_active(self) -> None:
        """Without a start time the delay is trusted, as before."""
        assert rain_delay_end(status(24, None)) is None
        assert rain_delay_active(status(24, None)) is True
        assert rain_delay_remaining_hours(status(24, None)) is None

    def test_next_watering_shows_again_after_delay_ends(self) -> None:
        """An expired delay no longer hides the next watering time."""
        next_start = (NOW + timedelta(hours=3)).isoformat()
        expired = status(24, NOW - timedelta(hours=30))
        running = status(24, NOW - timedelta(hours=2))

        assert next_watering_time({**expired, "next_start_time": next_start})
        assert next_watering_time({**running, "next_start_time": next_start}) is None


def make_coordinator(device_status: dict[str, Any]) -> MagicMock:
    """Create a coordinator holding one sprinkler with the given status."""
    coordinator = MagicMock(spec=BHyveDataUpdateCoordinator)
    coordinator.data = {
        "devices": {
            DEVICE_ID: {
                "device": {
                    "id": DEVICE_ID,
                    "name": "Garden Timer",
                    "type": "sprinkler_timer",
                    "mac_address": "aabbccddeeff",
                    "is_connected": True,
                    "status": device_status,
                }
            }
        },
        "programs": {},
    }
    return coordinator


class TestEntities:
    """The switch and sensor report when the delay ends."""

    def test_switch_reports_end_and_remaining(self) -> None:
        """The switch keeps `delay` and adds when the delay really ends."""
        start = NOW - timedelta(hours=2)
        coordinator = make_coordinator(
            {**status(24, start), "rain_delay_cause": "auto"}
        )
        device = coordinator.data["devices"][DEVICE_ID]["device"]
        switch = BHyveRainDelaySwitch(
            coordinator,
            device,
            BHyveSwitchEntityDescription(key="rain_delay", name="Rain delay"),
        )

        attrs = switch.extra_state_attributes

        assert switch.is_on is True
        assert attrs["delay"] == 24
        assert attrs["ends_at"] == start + timedelta(hours=24)
        assert attrs["remaining_hours"] == 22

    def test_switch_off_once_delay_has_ended(self) -> None:
        """The switch turns off when the end passes, before Orbit catches up."""
        coordinator = make_coordinator(status(24, NOW - timedelta(hours=30)))
        device = coordinator.data["devices"][DEVICE_ID]["device"]
        switch = BHyveRainDelaySwitch(
            coordinator,
            device,
            BHyveSwitchEntityDescription(key="rain_delay", name="Rain delay"),
        )

        assert switch.is_on is False
        assert switch.extra_state_attributes == {}

    @pytest.mark.parametrize(
        ("started_hours_ago", "expected"),
        [(2, NOW + timedelta(hours=22)), (30, None)],
    )
    def test_rain_delay_end_sensor(
        self, started_hours_ago: int, expected: datetime | None
    ) -> None:
        """The sensor shows the end of a running delay, and nothing otherwise."""
        description = next(
            d for d in SENSOR_TYPES_SPRINKLER if d.key == "rain_delay_end"
        )
        coordinator = make_coordinator(
            status(24, NOW - timedelta(hours=started_hours_ago))
        )
        device = coordinator.data["devices"][DEVICE_ID]["device"]

        sensor = BHyveSensor(coordinator, device, description)

        assert sensor.native_value == expected


class TestRainDelayEvent:
    """A rain_delay event restarts the clock on the delay."""

    async def test_event_records_when_delay_started(self, hass: HomeAssistant) -> None:
        """A new delay runs from the event, not from the previous delay's start."""
        coordinator = BHyveDataUpdateCoordinator(hass, MagicMock(), MagicMock())
        coordinator.data = make_coordinator(
            {**status(24, NOW - timedelta(days=5)), "rain_delay": 0}
        ).data

        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator.async_handle_device_event(
                {
                    "event": "rain_delay",
                    "device_id": DEVICE_ID,
                    "delay": 48,
                    "timestamp": "2026-10-13T09:20:00.000Z",
                }
            )

        device_status = coordinator.data["devices"][DEVICE_ID]["device"]["status"]
        assert device_status["rain_delay"] == 48
        assert device_status["rain_delay_started_at"] == "2026-10-13T09:20:00.000Z"
        assert rain_delay_active(device_status) is True
        assert rain_delay_remaining_hours(device_status) == 48

    async def test_event_without_timestamp_uses_now(self, hass: HomeAssistant) -> None:
        """Without a timestamp the delay is taken to start when it arrives."""
        coordinator = BHyveDataUpdateCoordinator(hass, MagicMock(), MagicMock())
        coordinator.data = make_coordinator({}).data

        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator.async_handle_device_event(
                {"event": "rain_delay", "device_id": DEVICE_ID, "delay": 24}
            )

        device_status = coordinator.data["devices"][DEVICE_ID]["device"]["status"]
        assert rain_delay_end(device_status) == NOW + timedelta(hours=24)

    async def test_cancelling_event_turns_delay_off(self, hass: HomeAssistant) -> None:
        """A zero delay cancels the delay."""
        coordinator = BHyveDataUpdateCoordinator(hass, MagicMock(), MagicMock())
        coordinator.data = make_coordinator(status(24, NOW)).data

        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator.async_handle_device_event(
                {"event": "rain_delay", "device_id": DEVICE_ID, "delay": 0}
            )

        device_status = coordinator.data["devices"][DEVICE_ID]["device"]["status"]
        assert rain_delay_active(device_status) is False
