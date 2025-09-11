"""Test BHyve valve entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from homeassistant.core import HomeAssistant

from custom_components.bhyve.pybhyve.client import BHyveClient
from custom_components.bhyve.pybhyve.typings import BHyveDevice, BHyveZone
from custom_components.bhyve.valve import BHyveZoneValve


@pytest.fixture
def mock_zone_data() -> BHyveZone:
    """Mock zone data for testing."""
    return BHyveZone({
        "station": "1",
        "name": "Front Yard",
        "enabled": True,
        "smart_watering_enabled": True,
        "image_url": "https://example.com/front_yard.jpg",
    })


@pytest.fixture
def mock_bhyve_client() -> BHyveClient:
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
    mock_bhyve_client: BHyveClient,
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
    assert valve.unique_id == f"{mock_sprinkler_device['mac_address']}:{mock_sprinkler_device['id']}:{mock_zone_data['station']}:valve"
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
    mock_bhyve_client: BHyveClient,
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
    mock_bhyve_client: BHyveClient,
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
    assert sent_message["stations"] == [{"station": mock_zone_data["station"], "run_time": 5.0}]

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
    mock_bhyve_client: BHyveClient,
) -> None:
    """Test zone valve availability based on device connection."""
    # Create device with connected status
    connected_device = mock_sprinkler_device.copy()
    connected_device["is_connected"] = True

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
    disconnected_device = mock_sprinkler_device.copy()
    disconnected_device["is_connected"] = False

    valve._setup(disconnected_device)
    assert valve.available is False