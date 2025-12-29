"""Test BHyve valve entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.pybhyve.typings import BHyveDevice, BHyveZone
from custom_components.bhyve.valve import BHyveZoneValve

# Test constants
TEST_RUNTIME_MINUTES = 14
TEST_PRESET_RUNTIME_SECONDS = 480


def create_mock_coordinator(devices: dict, programs: dict | None = None) -> MagicMock:
    """Create a mock coordinator with the given devices."""
    coordinator = MagicMock(spec=BHyveDataUpdateCoordinator)
    coordinator.data = {
        "devices": devices,
        "programs": programs or {},
    }
    coordinator.last_update_success = True
    coordinator.async_set_updated_data = MagicMock()
    coordinator.client = MagicMock()
    coordinator.client.send_message = AsyncMock()
    coordinator.client.get_landscape = AsyncMock()
    coordinator.client.update_landscape = AsyncMock()
    return coordinator


@pytest.fixture
def mock_zone_data() -> BHyveZone:
    """Mock zone data for testing."""
    return BHyveZone(
        {
            "station": "1",
            "name": "Front Yard",
            "enabled": True,
            "smart_watering_enabled": True,
            "image_url": "https://example.com/front_yard.jpg",
        }
    )


async def test_zone_valve_initialization(
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
) -> None:
    """Test zone valve entity initialization."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    zone_name = "Front Yard"
    device_programs = []

    valve = BHyveZoneValve(
        coordinator=coordinator,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name=zone_name,
        device_programs=device_programs,
    )

    # Test basic properties
    assert valve.name == f"{zone_name} zone"
    expected_unique_id = (
        f"{mock_sprinkler_device['mac_address']}:"
        f"{mock_sprinkler_device['id']}:"
        f"{mock_zone_data['station']}:valve"
    )
    assert valve.unique_id == expected_unique_id
    assert valve.device_class == "water"
    assert valve.is_closed is True
    assert valve.reports_position is False

    # Test zone-specific attributes
    assert valve._zone_name == zone_name
    assert valve._zone_id == mock_zone_data["station"]
    assert valve._smart_watering_enabled == mock_zone_data["smart_watering_enabled"]
    assert valve.entity_picture == mock_zone_data["image_url"]


async def test_zone_valve_attributes(
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
) -> None:
    """Test zone valve entity attributes."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    valve = BHyveZoneValve(
        coordinator=coordinator,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
    )

    attrs = valve.extra_state_attributes
    assert attrs["device_name"] == mock_sprinkler_device["name"]
    assert attrs["device_id"] == mock_sprinkler_device["id"]
    assert attrs["zone_name"] == "Front Yard"
    assert attrs["station"] == mock_zone_data["station"]
    assert attrs["smart_watering_enabled"] == mock_zone_data["smart_watering_enabled"]


async def test_zone_valve_open_close(
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
) -> None:
    """Test zone valve open/close functionality."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    valve = BHyveZoneValve(
        coordinator=coordinator,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
    )

    # Test opening valve (start watering)
    await valve.async_open_valve()
    coordinator.client.send_message.assert_called_once()
    sent_message = coordinator.client.send_message.call_args[0][0]
    assert sent_message["event"] == "change_mode"
    assert sent_message["device_id"] == mock_sprinkler_device["id"]
    assert sent_message["mode"] == "manual"
    assert sent_message["stations"] == [
        {"station": mock_zone_data["station"], "run_time": 5.0}
    ]

    # Reset mock
    coordinator.client.send_message.reset_mock()

    # Test closing valve (stop watering)
    await valve.async_close_valve()
    coordinator.client.send_message.assert_called_once()
    sent_message = coordinator.client.send_message.call_args[0][0]
    assert sent_message["event"] == "change_mode"
    assert sent_message["device_id"] == mock_sprinkler_device["id"]
    assert sent_message["mode"] == "manual"
    assert sent_message["stations"] == []


async def test_zone_valve_availability(
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
) -> None:
    """Test zone valve availability based on device connection."""
    # Create device with connected status
    connected_device_data = dict(mock_sprinkler_device)
    connected_device_data["is_connected"] = True
    connected_device = BHyveDevice(connected_device_data)

    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": connected_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    valve = BHyveZoneValve(
        coordinator=coordinator,
        device=connected_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
    )

    assert valve.available is True

    # Test with disconnected device
    disconnected_device_data = dict(mock_sprinkler_device)
    disconnected_device_data["is_connected"] = False
    disconnected_device = BHyveDevice(disconnected_device_data)

    # Update coordinator data
    coordinator.data["devices"]["test-device-123"]["device"] = disconnected_device

    assert valve.available is False


async def test_valve_watering_state(
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
) -> None:
    """Test valve watering state detection."""
    # Create device with watering status
    watering_device_data = dict(mock_sprinkler_device)
    watering_device_data["status"] = {
        "watering_status": {
            "current_station": "1",  # matches mock_zone_data["station"]
            "program": "e",
            "run_time": TEST_RUNTIME_MINUTES,
            "started_watering_station_at": "2020-01-09T20:29:59.000Z",
            "stations": [{"station": "1", "run_time": TEST_RUNTIME_MINUTES}],
        }
    }
    watering_device = BHyveDevice(watering_device_data)

    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": watering_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    valve = BHyveZoneValve(
        coordinator=coordinator,
        device=watering_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
    )

    # Valve should be open (watering) when current_station matches
    assert valve.is_closed is False

    # Check attributes
    attrs = valve.extra_state_attributes
    assert attrs["current_station"] == "1"
    assert attrs["current_program"] == "e"
    assert attrs["current_runtime"] == TEST_RUNTIME_MINUTES
    assert attrs.get("started_watering_station_at") is not None


async def test_valve_watering_other_zone(
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
) -> None:
    """Test valve state when another zone is watering."""
    # Create device with different zone watering
    other_zone_device_data = dict(mock_sprinkler_device)
    other_zone_device_data["status"] = {
        "watering_status": {
            "current_station": "2",  # different from mock_zone_data["station"] = "1"
            "program": "a",
            "run_time": 10,
        }
    }
    other_zone_device = BHyveDevice(other_zone_device_data)

    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": other_zone_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    valve = BHyveZoneValve(
        coordinator=coordinator,
        device=other_zone_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
    )

    # Valve should be closed when another zone is watering
    assert valve.is_closed is True


async def test_valve_no_watering_status(
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
) -> None:
    """Test valve state when no watering is in progress."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    valve = BHyveZoneValve(
        coordinator=coordinator,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
    )

    # Valve should be closed when no watering status
    assert valve.is_closed is True


async def test_valve_with_landscape_data(
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
) -> None:
    """Test valve attributes with landscape data."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {
                    "1": {
                        "id": "landscape-123",
                        "image_url": "https://example.com/landscape.jpg",
                        "sprinkler_type": "spray",
                    }
                },
            }
        }
    )

    valve = BHyveZoneValve(
        coordinator=coordinator,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
    )

    attrs = valve.extra_state_attributes
    assert attrs.get("landscape_image") == "https://example.com/landscape.jpg"
    assert attrs.get("sprinkler_type") == "spray"
