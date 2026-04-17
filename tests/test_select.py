"""Test BHyve select entities."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.helpers.entity import EntityCategory

from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.pybhyve.typings import BHyveDevice
from custom_components.bhyve.select import SELECT_TYPES, BHyveSelectEntity


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
    return coordinator


async def test_select_initialization(
    mock_sprinkler_device: BHyveDevice,
) -> None:
    """Test select entity initialization."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    description = SELECT_TYPES[0]
    entity = BHyveSelectEntity(coordinator, mock_sprinkler_device, description)

    assert entity._attr_name == "Device mode"
    assert entity.unique_id == (
        f"{mock_sprinkler_device['mac_address']}:"
        f"{mock_sprinkler_device['id']}:device_mode"
    )
    assert entity.entity_description.entity_category == EntityCategory.CONFIG
    assert entity.entity_description.options == ["auto", "off"]


async def test_select_current_option(
    mock_sprinkler_device: BHyveDevice,
) -> None:
    """Test current_option returns run_mode from device status."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    entity = BHyveSelectEntity(coordinator, mock_sprinkler_device, SELECT_TYPES[0])

    assert entity.current_option == "auto"


async def test_select_option_off(
    mock_sprinkler_device: BHyveDevice,
) -> None:
    """Test selecting 'off' sends correct websocket message."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    entity = BHyveSelectEntity(coordinator, mock_sprinkler_device, SELECT_TYPES[0])

    await entity.async_select_option("off")

    coordinator.client.send_message.assert_called_once_with(
        {
            "event": "change_mode",
            "device_id": "test-device-123",
            "mode": "off",
        }
    )


async def test_select_option_auto(
    mock_sprinkler_device: BHyveDevice,
) -> None:
    """Test selecting 'auto' sends correct websocket message."""
    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    entity = BHyveSelectEntity(coordinator, mock_sprinkler_device, SELECT_TYPES[0])

    await entity.async_select_option("auto")

    coordinator.client.send_message.assert_called_once_with(
        {
            "event": "change_mode",
            "device_id": "test-device-123",
            "mode": "auto",
        }
    )


async def test_select_current_option_from_websocket_event(
    mock_sprinkler_device: BHyveDevice,
) -> None:
    """Test current_option reads 'mode' field set by websocket events."""
    device_data = dict(mock_sprinkler_device)
    device_data["status"] = {"run_mode": "auto", "mode": "off"}
    device = BHyveDevice(device_data)

    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": device,
                "history": [],
                "landscapes": {},
            }
        }
    )

    entity = BHyveSelectEntity(coordinator, device, SELECT_TYPES[0])

    # 'mode' (from websocket event) takes precedence over 'run_mode'
    assert entity.current_option == "off"


async def test_select_current_option_missing_status(
    mock_sprinkler_device: BHyveDevice,
) -> None:
    """Test current_option returns None when status is missing."""
    device_data = dict(mock_sprinkler_device)
    del device_data["status"]
    device_no_status = BHyveDevice(device_data)

    coordinator = create_mock_coordinator(
        {
            "test-device-123": {
                "device": device_no_status,
                "history": [],
                "landscapes": {},
            }
        }
    )

    entity = BHyveSelectEntity(coordinator, device_no_status, SELECT_TYPES[0])

    assert entity.current_option is None
