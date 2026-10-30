"""
Test that a rain_delay event sets the delay's start, and that polls keep it.

Orbit reports a rain delay as a length in hours (rain_delay) counted from
rain_delay_started_at, and re-sends a delay over the websocket with the hours
left. Live: a delay re-sent with 5 h at 11:48 and 1 h at 15:49 (AEDT). Taking
each event's time as the start keeps started_at + delay right (#447). Orbit's
REST data runs minutes behind its events, so a poll just after an event must
not bring back the old start.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

DEVICE_ID = "sprinkler-1"
NOW = datetime(2026, 10, 14, 4, 49, 42, tzinfo=UTC)
EVENT_TIME = "2026-10-14T04:49:42.000Z"
OLD_START = "2026-10-13T20:47:56.000Z"


@pytest.fixture(autouse=True)
def frozen_now(freezer: FrozenDateTimeFactory) -> None:
    """Freeze time at the moment of the rain_delay event."""
    freezer.move_to(NOW)


class PollingClient:
    """A client whose next poll returns the given rain delay status."""

    def __init__(self, status: dict[str, Any]) -> None:
        """Start with the given device status."""
        self.status = status
        self.get_device_history = AsyncMock(return_value=[])
        self.get_landscape = AsyncMock(return_value=None)

    @property
    async def devices(self) -> list[dict[str, Any]]:
        """Return the sprinkler with the current status."""
        return [
            {
                "id": DEVICE_ID,
                "name": "Garden Timer",
                "type": "sprinkler_timer",
                "zones": [{"station": 1}],
                "status": dict(self.status),
            }
        ]

    @property
    async def timer_programs(self) -> list[dict[str, Any]]:
        """Return no programs."""
        return []


async def make_coordinator(
    hass: HomeAssistant, status: dict[str, Any]
) -> tuple[BHyveDataUpdateCoordinator, PollingClient]:
    """Create a coordinator and run its first poll."""
    client = PollingClient(status)
    coordinator = BHyveDataUpdateCoordinator(hass, client, MagicMock())
    await coordinator.async_refresh()
    return coordinator, client


def status_of(coordinator: BHyveDataUpdateCoordinator) -> dict[str, Any]:
    """Return the sprinkler's status."""
    return coordinator.data["devices"][DEVICE_ID]["device"]["status"]


async def send_rain_delay(
    coordinator: BHyveDataUpdateCoordinator, delay: int, **extra: Any
) -> None:
    """Feed a rain_delay websocket event to the coordinator."""
    with patch.object(coordinator, "async_set_updated_data"):
        await coordinator.async_handle_device_event(
            {"event": "rain_delay", "device_id": DEVICE_ID, "delay": delay, **extra}
        )


async def test_event_sets_start(hass: HomeAssistant) -> None:
    """A re-sent delay runs from the event, not from the earlier start."""
    coordinator, _ = await make_coordinator(
        hass, {"rain_delay": 9, "rain_delay_started_at": OLD_START}
    )

    await send_rain_delay(coordinator, 1, timestamp=EVENT_TIME)

    assert status_of(coordinator)["rain_delay"] == 1
    assert status_of(coordinator)["rain_delay_started_at"] == EVENT_TIME


async def test_event_without_timestamp_starts_now(hass: HomeAssistant) -> None:
    """Without a timestamp, the delay starts when the event arrives."""
    coordinator, _ = await make_coordinator(hass, {"rain_delay": 0})

    await send_rain_delay(coordinator, 24)

    assert status_of(coordinator)["rain_delay_started_at"] == NOW.isoformat()


async def test_stale_poll_keeps_event(hass: HomeAssistant) -> None:
    """A poll still showing the old start does not undo the event."""
    coordinator, _ = await make_coordinator(
        hass, {"rain_delay": 9, "rain_delay_started_at": OLD_START}
    )
    await send_rain_delay(coordinator, 1, timestamp=EVENT_TIME)

    await coordinator.async_refresh()

    assert status_of(coordinator)["rain_delay"] == 1
    assert status_of(coordinator)["rain_delay_started_at"] == EVENT_TIME


async def test_poll_that_caught_up_is_trusted(hass: HomeAssistant) -> None:
    """Once the poll reports the event's start, its values are used."""
    coordinator, client = await make_coordinator(
        hass, {"rain_delay": 9, "rain_delay_started_at": OLD_START}
    )
    await send_rain_delay(coordinator, 1, timestamp=EVENT_TIME)

    # Orbit's own start can be a second before the event's timestamp.
    client.status = {"rain_delay": 1, "rain_delay_started_at": "2026-10-14T04:49:41Z"}
    await coordinator.async_refresh()
    assert status_of(coordinator)["rain_delay_started_at"] == "2026-10-14T04:49:41Z"

    # From then on, polls are used as they are.
    client.status = {"rain_delay": 0, "rain_delay_started_at": "2026-10-14T04:49:41Z"}
    await coordinator.async_refresh()
    assert status_of(coordinator)["rain_delay"] == 0


async def test_cancellation_is_kept_over_stale_poll(hass: HomeAssistant) -> None:
    """A delay cancelled by an event stays off while the poll lags."""
    coordinator, _ = await make_coordinator(
        hass, {"rain_delay": 9, "rain_delay_started_at": OLD_START}
    )

    await send_rain_delay(coordinator, 0, timestamp=EVENT_TIME)
    await coordinator.async_refresh()

    assert status_of(coordinator)["rain_delay"] == 0


async def test_old_event_stops_overriding(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """If the poll never catches up, the event stops applying after a while."""
    coordinator, _ = await make_coordinator(
        hass, {"rain_delay": 9, "rain_delay_started_at": OLD_START}
    )
    await send_rain_delay(coordinator, 0, timestamp=EVENT_TIME)

    freezer.tick(timedelta(minutes=31))
    await coordinator.async_refresh()

    assert status_of(coordinator)["rain_delay"] == 9


async def test_polls_without_events_are_unchanged(hass: HomeAssistant) -> None:
    """With no rain_delay event, polled values are used as they are."""
    coordinator, client = await make_coordinator(
        hass, {"rain_delay": 9, "rain_delay_started_at": OLD_START}
    )

    client.status = {"rain_delay": 4, "rain_delay_started_at": OLD_START}
    await coordinator.async_refresh()

    assert status_of(coordinator)["rain_delay"] == 4
