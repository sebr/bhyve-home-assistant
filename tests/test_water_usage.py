"""Test the zone water usage sensor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfVolume
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.bhyve.const import CONF_DEVICES, DOMAIN
from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.sensor import (
    WATER_USAGE_DESCRIPTION,
    BHyveZoneWaterUsageSensor,
    WaterUsageStoredData,
)

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

DEVICE_ID = "sprinkler-1"
MAC = "4467552a366e"
UNIQUE_ID = f"{MAC}:{DEVICE_ID}:1:water_usage"

DEVICE: dict[str, Any] = {
    "id": DEVICE_ID,
    "name": "Garden Timer",
    "type": "sprinkler_timer",
    "mac_address": MAC,
    "is_connected": True,
    "zones": [
        {"station": 1, "name": "Front Yard"},
        {"station": 2, "name": "Back Yard"},
    ],
    "status": {"run_mode": "auto"},
}


def run(start_time: str, gallons: float | None, station: int = 1) -> dict[str, Any]:
    """Build one irrigation entry as Orbit reports it."""
    return {
        "station": station,
        "start_time": start_time,
        "run_time": 10,
        "status": "complete",
        "water_volume_gal": gallons,
    }


def history(*runs: dict[str, Any]) -> list[dict[str, Any]]:
    """Wrap irrigation entries in a watering event."""
    return [{"irrigation": list(runs)}]


def make_sensor(
    events: list[dict[str, Any]],
) -> tuple[BHyveZoneWaterUsageSensor, MagicMock]:
    """Create the front yard sensor over a coordinator holding events."""
    coordinator = MagicMock(spec=BHyveDataUpdateCoordinator)
    coordinator.data = {
        "devices": {DEVICE_ID: {"device": DEVICE, "history": events}},
        "programs": {},
    }
    sensor = BHyveZoneWaterUsageSensor(
        coordinator, DEVICE, DEVICE["zones"][0], "Front Yard", WATER_USAGE_DESCRIPTION
    )
    return sensor, coordinator


def poll(coordinator: MagicMock, events: list[dict[str, Any]]) -> None:
    """Replace the history the coordinator holds, as a poll would."""
    coordinator.data["devices"][DEVICE_ID]["history"] = events


class TestCounting:
    """Each run's volume is counted exactly once."""

    def test_description_fits_energy_dashboard(self) -> None:
        """The sensor is a water total the Energy dashboard accepts."""
        assert WATER_USAGE_DESCRIPTION.device_class is SensorDeviceClass.WATER
        assert WATER_USAGE_DESCRIPTION.state_class is SensorStateClass.TOTAL_INCREASING
        assert WATER_USAGE_DESCRIPTION.native_unit_of_measurement == (
            UnitOfVolume.GALLONS
        )

    def test_starts_from_visible_history(self) -> None:
        """A new sensor counts the runs Orbit currently reports for its zone."""
        sensor, _ = make_sensor(
            history(
                run("2026-10-01T06:00:00.000Z", 10.5),
                run("2026-10-02T06:00:00.000Z", 4.5),
                run("2026-10-02T06:10:00.000Z", 99, station=2),
            )
        )

        sensor._count_new_runs()

        assert sensor.native_value == 15.0

    def test_repeated_polls_do_not_double_count(self) -> None:
        """The same history seen again adds nothing."""
        events = history(run("2026-10-01T06:00:00.000Z", 10.0))
        sensor, _ = make_sensor(events)

        for _ in range(3):
            sensor._count_new_runs()

        assert sensor.native_value == 10.0

    def test_new_run_is_added(self) -> None:
        """A run that appears in a later poll is added to the total."""
        sensor, coordinator = make_sensor(history(run("2026-10-01T06:00:00.000Z", 10)))
        sensor._count_new_runs()

        poll(
            coordinator,
            history(
                run("2026-10-01T06:00:00.000Z", 10),
                run("2026-10-03T06:00:00.000Z", 7.25),
            ),
        )
        sensor._count_new_runs()

        assert sensor.native_value == 17.25

    def test_growing_run_adds_only_the_difference(self) -> None:
        """A run reported before its final volume is topped up, not recounted."""
        sensor, coordinator = make_sensor(history(run("2026-10-01T06:00:00.000Z", 3)))
        sensor._count_new_runs()

        poll(coordinator, history(run("2026-10-01T06:00:00.000Z", 8)))
        sensor._count_new_runs()

        assert sensor.native_value == 8.0

    def test_shrinking_run_never_lowers_the_total(self) -> None:
        """A corrected-down volume does not make the total decrease."""
        sensor, coordinator = make_sensor(history(run("2026-10-01T06:00:00.000Z", 8)))
        sensor._count_new_runs()

        poll(coordinator, history(run("2026-10-01T06:00:00.000Z", 5)))
        sensor._count_new_runs()

        assert sensor.native_value == 8.0

    def test_window_slides_without_recounting(self) -> None:
        """Runs leaving the window are forgotten; returning ones are ignored."""
        old, mid, new = (
            run("2026-10-01T06:00:00.000Z", 1),
            run("2026-10-02T06:00:00.000Z", 2),
            run("2026-10-03T06:00:00.000Z", 4),
        )
        sensor, coordinator = make_sensor(history(old, mid))
        sensor._count_new_runs()

        poll(coordinator, history(mid, new))
        sensor._count_new_runs()
        assert sensor.native_value == 7.0
        assert "2026-10-01T06:00:00.000Z" not in sensor._usage.counted

        # A page that briefly includes the old run again does not recount it.
        poll(coordinator, history(old, mid, new))
        sensor._count_new_runs()
        assert sensor.native_value == 7.0

    def test_failed_history_fetch_keeps_total(self) -> None:
        """Empty history (a failed fetch) neither resets nor forgets runs."""
        sensor, coordinator = make_sensor(history(run("2026-10-01T06:00:00.000Z", 3)))
        sensor._count_new_runs()

        poll(coordinator, [])
        sensor._count_new_runs()
        assert sensor.native_value == 3.0

        poll(coordinator, history(run("2026-10-01T06:00:00.000Z", 5)))
        sensor._count_new_runs()
        assert sensor.native_value == 5.0

    def test_runs_without_volume_are_skipped(self) -> None:
        """Runs with no reported volume add nothing until they report one."""
        sensor, coordinator = make_sensor(
            history(run("2026-10-01T06:00:00.000Z", None))
        )
        sensor._count_new_runs()
        assert sensor.native_value == 0.0

        poll(coordinator, history(run("2026-10-01T06:00:00.000Z", 6)))
        sensor._count_new_runs()
        assert sensor.native_value == 6.0


class TestStoredData:
    """The counting state survives a round trip through storage."""

    def test_round_trip(self) -> None:
        """as_dict and from_dict are inverses."""
        data = WaterUsageStoredData(
            total=12.5,
            watermark="2026-10-02T06:00:00.000Z",
            counted={"2026-10-02T06:00:00.000Z": 2.5},
        )

        assert WaterUsageStoredData.from_dict(data.as_dict()) == data

    @pytest.mark.parametrize(
        "stored",
        [{}, {"total": "lots"}, {"total": 1, "counted": {"a": None}}],
    )
    def test_unusable_data_is_rejected(self, stored: dict[str, Any]) -> None:
        """Corrupt stored data is ignored rather than raising."""
        assert WaterUsageStoredData.from_dict(stored) is None


class FakeClient:
    """Stand-in for BHyveClient serving one sprinkler and its history."""

    events: ClassVar[list[dict[str, Any]]] = []

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
        """Return the sprinkler."""
        return [dict(DEVICE)]

    @property
    async def timer_programs(self) -> list[dict[str, Any]]:
        """Return no programs."""
        return []

    async def get_device_history(self, *_args: Any, **_kwargs: Any) -> list:
        """Return the canned watering events."""
        return FakeClient.events

    async def get_landscape(self, *_args: Any, **_kwargs: Any) -> None:
        """Return no landscape."""


async def setup_integration(hass: HomeAssistant) -> None:
    """Set up the integration for the sprinkler."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        options={CONF_DEVICES: [DEVICE_ID]},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.bhyve.BHyveClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_restart_continues_from_restored_total(hass: HomeAssistant) -> None:
    """After a restart, only runs newer than the saved watermark are added."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, UNIQUE_ID, suggested_object_id="garden_timer_front_yard"
    )
    entity_id = "sensor.garden_timer_front_yard"
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(entity_id, "120.0"),
                WaterUsageStoredData(
                    total=120.0,
                    watermark="2026-10-02T06:00:00.000Z",
                    counted={"2026-10-02T06:00:00.000Z": 4.0},
                ).as_dict(),
            )
        ],
    )
    FakeClient.events = history(
        run("2026-10-02T06:00:00.000Z", 4.0),  # counted before the restart
        run("2026-10-04T06:00:00.000Z", 6.5),  # watered while HA was down
    )

    await setup_integration(hass)

    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == 126.5
    assert state.attributes["unit_of_measurement"] == UnitOfVolume.GALLONS
    assert state.attributes["device_class"] == SensorDeviceClass.WATER
    assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_metric_users_see_litres(hass: HomeAssistant) -> None:
    """On a metric system the gallons Orbit reports are shown in litres."""
    FakeClient.events = history(run("2026-10-02T06:00:00.000Z", 10.0))

    await setup_integration(hass)

    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, UNIQUE_ID)
    state = hass.states.get(entity_id)
    assert state.attributes["unit_of_measurement"] == UnitOfVolume.LITERS
    assert float(state.state) == pytest.approx(37.9, abs=0.1)
