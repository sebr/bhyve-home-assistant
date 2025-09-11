"""Test BHyve valve entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.bhyve.pybhyve.client import BHyveClient
from custom_components.bhyve.pybhyve.typings import BHyveDevice, BHyveZone
from custom_components.bhyve.valve import BHyveZoneValve

# Test constants
TEST_RUNTIME_MINUTES = 14
TEST_PRESET_RUNTIME_SECONDS = 480


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


@pytest.fixture
def mock_bhyve_client() -> MagicMock:
    """Mock BHyve client."""
    client = MagicMock(spec=BHyveClient)
    client.login = AsyncMock(return_value=True)
    client.devices = AsyncMock(return_value=[])
    client.timer_programs = AsyncMock(return_value=[])
    client.get_device = AsyncMock()
    client.send_message = AsyncMock()
    client.stop = MagicMock()
    return client


async def test_zone_valve_initialization(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test zone valve entity initialization."""
    zone_name = "Front Yard"
    device_programs = []
    icon = "sprinkler-variant"

    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name=zone_name,
        device_programs=device_programs,
        icon=icon,
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
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test zone valve entity attributes."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Setup device to populate attributes
    valve._setup(mock_sprinkler_device)

    attrs = valve.extra_state_attributes
    assert attrs["device_name"] == mock_sprinkler_device["name"]
    assert attrs["device_id"] == mock_sprinkler_device["id"]
    assert attrs["zone_name"] == "Front Yard"
    assert attrs["station"] == mock_zone_data["station"]
    assert attrs["smart_watering_enabled"] == mock_zone_data["smart_watering_enabled"]


async def test_zone_valve_open_close(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test zone valve open/close functionality."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Test opening valve (start watering)
    await valve.async_open_valve()
    mock_bhyve_client.send_message.assert_called_once()
    sent_message = mock_bhyve_client.send_message.call_args[0][0]
    assert sent_message["event"] == "change_mode"
    assert sent_message["device_id"] == mock_sprinkler_device["id"]
    assert sent_message["mode"] == "manual"
    assert sent_message["stations"] == [
        {"station": mock_zone_data["station"], "run_time": 5.0}
    ]

    # Reset mock
    mock_bhyve_client.send_message.reset_mock()

    # Test closing valve (stop watering)
    await valve.async_close_valve()
    mock_bhyve_client.send_message.assert_called_once()
    sent_message = mock_bhyve_client.send_message.call_args[0][0]
    assert sent_message["event"] == "change_mode"
    assert sent_message["device_id"] == mock_sprinkler_device["id"]
    assert sent_message["mode"] == "manual"
    assert sent_message["stations"] == []


async def test_zone_valve_availability(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test zone valve availability based on device connection."""
    # Create device with connected status
    connected_device_data = dict(mock_sprinkler_device)
    connected_device_data["is_connected"] = True
    connected_device = BHyveDevice(connected_device_data)

    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=connected_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    valve._setup(connected_device)
    assert valve.available is True

    # Test with disconnected device
    disconnected_device_data = dict(mock_sprinkler_device)
    disconnected_device_data["is_connected"] = False
    disconnected_device = BHyveDevice(disconnected_device_data)

    valve._setup(disconnected_device)
    assert valve.available is False


async def test_valve_websocket_watering_in_progress(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test valve response to watering_in_progress websocket event."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Initially valve should be closed
    assert valve.is_closed is True

    # Simulate watering in progress for this zone
    watering_event = {
        "event": "watering_in_progress_notification",
        "program": "e",
        "current_station": 1,  # matches mock_zone_data["station"]
        "run_time": TEST_RUNTIME_MINUTES,
        "started_watering_station_at": "2020-01-09T20:29:59.000Z",
        "rain_sensor_hold": False,
        "device_id": "test-device-123",
        "timestamp": "2020-01-09T20:29:59.000Z",
    }

    # Process the websocket event
    valve._on_ws_data(watering_event)

    # Valve should now be open (watering)
    assert valve.is_closed is False

    # Check attributes are updated
    attrs = valve.extra_state_attributes
    assert (
        attrs["started_watering_station_at"] is not None
    )  # timestamp converted to datetime
    assert attrs["current_station"] == 1
    assert attrs["current_program"] == "e"
    assert attrs["current_runtime"] == TEST_RUNTIME_MINUTES


async def test_valve_websocket_watering_other_zone(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test valve response when another zone is watering."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Start watering this zone first
    valve._attr_is_closed = False

    # Simulate watering in progress for different zone
    watering_event = {
        "event": "watering_in_progress_notification",
        "program": "a",
        "current_station": 2,  # different from mock_zone_data["station"] = "1"
        "run_time": 10,
        "started_watering_station_at": "2020-01-09T20:30:00.000Z",
        "device_id": "test-device-123",
        "timestamp": "2020-01-09T20:30:00.000Z",
    }

    # Process the websocket event
    valve._on_ws_data(watering_event)

    # This valve should be closed since another zone is watering
    assert valve.is_closed is True


async def test_valve_websocket_device_idle(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test valve response to device_idle websocket event."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Start with valve open (watering)
    valve._attr_is_closed = False

    # Simulate device idle event
    idle_event = {
        "event": "device_idle",
        "device_id": "test-device-123",
        "timestamp": "2020-01-10T12:32:06.000Z",
    }

    # Process the websocket event
    valve._on_ws_data(idle_event)

    # Valve should be closed after device idle
    assert valve.is_closed is True

    # Watering attributes should be cleared
    attrs = valve.extra_state_attributes
    assert attrs.get("started_watering_station_at") is None
    assert attrs.get("current_station") is None
    assert attrs.get("current_program") is None
    assert attrs.get("current_runtime") is None


async def test_valve_websocket_watering_complete(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test valve response to watering_complete websocket event."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Start with valve open (watering)
    valve._attr_is_closed = False

    # Simulate watering complete event
    complete_event = {
        "event": "watering_complete",
        "device_id": "test-device-123",
        "timestamp": "2020-01-09T20:44:00.000Z",
    }

    # Process the websocket event
    valve._on_ws_data(complete_event)

    # Valve should be closed after watering complete
    assert valve.is_closed is True


async def test_valve_websocket_change_mode_off(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test valve response to change_mode off/auto websocket event."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Start with valve open (watering)
    valve._attr_is_closed = False

    # Simulate change mode to off
    mode_event = {
        "event": "change_mode",
        "mode": "off",
        "device_id": "test-device-123",
        "timestamp": "2020-01-09T20:44:00.000Z",
    }

    # Process the websocket event
    valve._on_ws_data(mode_event)

    # Valve should be closed after mode change to off
    assert valve.is_closed is True

    # Test with auto mode as well
    valve._attr_is_closed = False
    mode_event["mode"] = "auto"
    valve._on_ws_data(mode_event)
    assert valve.is_closed is True


async def test_valve_websocket_manual_preset_runtime(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test valve response to set_manual_preset_runtime websocket event."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Simulate manual preset runtime update
    runtime_event = {
        "event": "set_manual_preset_runtime",
        "device_id": "test-device-123",
        "seconds": TEST_PRESET_RUNTIME_SECONDS,
        "timestamp": "2020-01-18T17:00:35.000Z",
    }

    # Process the websocket event
    valve._on_ws_data(runtime_event)

    # Manual preset runtime should be updated
    assert valve._manual_preset_runtime == TEST_PRESET_RUNTIME_SECONDS

    # Attribute should be updated
    attrs = valve.extra_state_attributes
    assert attrs["manual_preset_runtime"] == TEST_PRESET_RUNTIME_SECONDS


async def test_valve_websocket_event_filtering(
    hass: HomeAssistant,
    mock_sprinkler_device: BHyveDevice,
    mock_zone_data: BHyveZone,
    mock_bhyve_client: MagicMock,
) -> None:
    """Test that valve only handles relevant websocket events."""
    valve = BHyveZoneValve(
        hass=hass,
        bhyve=mock_bhyve_client,
        device=mock_sprinkler_device,
        zone=mock_zone_data,
        zone_name="Front Yard",
        device_programs=[],
        icon="sprinkler-variant",
    )

    # Test handled events
    handled_events = [
        "change_mode",
        "device_idle",
        "program_changed",
        "set_manual_preset_runtime",
        "watering_complete",
        "watering_in_progress_notification",
    ]

    for event_name in handled_events:
        assert valve._should_handle_event(event_name, {}) is True

    # Test unhandled events
    unhandled_events = [
        "battery_status",
        "rain_delay",
        "unknown_event",
        "fs_status_update",
    ]

    for event_name in unhandled_events:
        assert valve._should_handle_event(event_name, {}) is False
