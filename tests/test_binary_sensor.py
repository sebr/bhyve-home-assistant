"""Test BHyve binary sensor entities."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.bhyve.binary_sensor import (
    BINARY_SENSOR_TYPES,
    BHyveBinarySensor,
    async_setup_entry,
)
from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.pybhyve.typings import BHyveDevice

# Test constants
TEST_RSSI_NORMAL = -45
TEST_RSSI_ALARM = -55
TEST_TEMP_THRESHOLD_LOW = 32
TEST_TEMP_THRESHOLD_HIGH = 100
EXPECTED_FLOOD_ENTITIES = 2


def create_mock_coordinator(devices: dict) -> MagicMock:
    """Create a mock coordinator with the given devices."""
    coordinator = MagicMock(spec=BHyveDataUpdateCoordinator)
    coordinator.data = {
        "devices": devices,
        "programs": {},
    }
    coordinator.last_update_success = True
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.options = {}
    return entry


@pytest.fixture
def mock_flood_device() -> BHyveDevice:
    """Mock BHyve flood sensor device."""
    return BHyveDevice(
        {
            "id": "test-flood-123",
            "name": "Basement Flood Sensor",
            "type": "flood_sensor",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "hardware_version": "v1.0",
            "firmware_version": "2.1.0",
            "is_connected": True,
            "location_name": "Basement",
            "auto_shutoff": True,
            "status": {
                "flood_alarm_status": "ok",
                "temp_alarm_status": "ok",
                "temp_f": 72.0,
                "rssi": TEST_RSSI_NORMAL,
            },
            "temp_alarm_thresholds": {
                "low": TEST_TEMP_THRESHOLD_LOW,
                "high": TEST_TEMP_THRESHOLD_HIGH,
            },
        }
    )


@pytest.fixture
def mock_flood_device_alarming() -> BHyveDevice:
    """Mock BHyve flood sensor device in alarm state."""
    return BHyveDevice(
        {
            "id": "test-flood-456",
            "name": "Garage Flood Sensor",
            "type": "flood_sensor",
            "mac_address": "bb:cc:dd:ee:ff:aa",
            "hardware_version": "v1.0",
            "firmware_version": "2.1.0",
            "is_connected": True,
            "location_name": "Garage",
            "auto_shutoff": False,
            "status": {
                "flood_alarm_status": "alarm",
                "temp_alarm_status": "alarm",
                "temp_f": 105.0,
                "rssi": TEST_RSSI_ALARM,
            },
            "temp_alarm_thresholds": {
                "low": TEST_TEMP_THRESHOLD_LOW,
                "high": TEST_TEMP_THRESHOLD_HIGH,
            },
        }
    )


@pytest.fixture
def mock_coordinator(mock_flood_device: BHyveDevice) -> MagicMock:
    """Mock coordinator with flood device data."""
    return create_mock_coordinator(
        {
            "test-flood-123": {
                "device": mock_flood_device,
                "history": [],
                "landscapes": {},
            }
        }
    )


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    async def test_setup_entry_with_flood_devices(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test setting up binary sensors for flood devices."""
        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": mock_coordinator,
                    "devices": [mock_flood_device],
                }
            }
        }

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Call setup entry
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Verify entities were added
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]

        # Should create 2 entities: flood sensor and temperature binary sensor
        assert len(entities) == EXPECTED_FLOOD_ENTITIES
        assert isinstance(entities[0], BHyveBinarySensor)
        assert isinstance(entities[1], BHyveBinarySensor)
        assert entities[0].entity_description.key == "flood"
        assert entities[1].entity_description.key == "temperature_alert"

    async def test_setup_entry_no_flood_devices(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test setting up binary sensors with no flood devices."""
        # Create coordinator with sprinkler device (non-flood)
        sprinkler_device = BHyveDevice(
            {"id": "test-sprinkler-123", "type": "sprinkler_timer", "name": "Sprinkler"}
        )
        coordinator = create_mock_coordinator(
            {
                "test-sprinkler-123": {
                    "device": sprinkler_device,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": coordinator,
                    "devices": [sprinkler_device],
                }
            }
        }

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Call setup entry
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Verify no entities were added
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 0


class TestBHyveFloodSensor:
    """Test BHyveFloodSensor entity."""

    async def test_flood_sensor_initialization(
        self,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test flood sensor entity initialization."""
        sensor = BHyveBinarySensor(
            coordinator=mock_coordinator,
            device=mock_flood_device,
            description=BINARY_SENSOR_TYPES[0],
        )

        # Test basic properties
        assert sensor.name == "Basement Flood Sensor flood sensor"
        assert sensor.device_class == BinarySensorDeviceClass.MOISTURE
        assert sensor.unique_id == "aa:bb:cc:dd:ee:ff:test-flood-123:water"

    async def test_flood_sensor_normal_state(
        self,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test flood sensor in normal (not flooded) state."""
        sensor = BHyveBinarySensor(
            coordinator=mock_coordinator,
            device=mock_flood_device,
            description=BINARY_SENSOR_TYPES[0],
        )

        # Test state
        assert sensor.is_on is False
        assert sensor.available is True

        # Test attributes
        attrs = sensor.extra_state_attributes
        assert attrs["location"] == "Basement"
        assert attrs["shutoff"] is True
        assert attrs["rssi"] == TEST_RSSI_NORMAL

    async def test_flood_sensor_alarm_state(
        self,
        mock_flood_device_alarming: BHyveDevice,
    ) -> None:
        """Test flood sensor in alarm (flooded) state."""
        coordinator = create_mock_coordinator(
            {
                "test-flood-456": {
                    "device": mock_flood_device_alarming,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveBinarySensor(
            coordinator=coordinator,
            device=mock_flood_device_alarming,
            description=BINARY_SENSOR_TYPES[0],
        )

        # Test state
        assert sensor.is_on is True
        assert sensor.available is True

    async def test_flood_sensor_websocket_event(
        self,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test flood sensor response to websocket events."""
        sensor = BHyveBinarySensor(
            coordinator=mock_coordinator,
            device=mock_flood_device,
            description=BINARY_SENSOR_TYPES[0],
        )

        # Initial state should be normal
        assert sensor.is_on is False

        # Simulate coordinator update with alarm status
        mock_coordinator.data["devices"]["test-flood-123"]["device"]["status"][
            "flood_alarm_status"
        ] = "alarm"
        mock_coordinator.data["devices"]["test-flood-123"]["device"]["status"][
            "rssi"
        ] = TEST_RSSI_ALARM

        # State should be updated to alarm
        assert sensor.is_on is True
        assert sensor.extra_state_attributes["rssi"] == TEST_RSSI_ALARM

    async def test_flood_sensor_event_filtering(
        self,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test flood sensor handles all events via coordinator."""
        sensor = BHyveBinarySensor(
            coordinator=mock_coordinator,
            device=mock_flood_device,
            description=BINARY_SENSOR_TYPES[0],
        )

        # Coordinator-based entities don't need event filtering
        # They just read from coordinator.data
        assert sensor.is_on is False

    async def test_flood_sensor_disconnected_device(
        self,
        mock_flood_device: BHyveDevice,
    ) -> None:
        """Test flood sensor with disconnected device."""
        # Create disconnected device
        disconnected_device_data = dict(mock_flood_device)
        disconnected_device_data["is_connected"] = False
        disconnected_device = BHyveDevice(disconnected_device_data)

        coordinator = create_mock_coordinator(
            {
                "test-flood-123": {
                    "device": disconnected_device,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveBinarySensor(
            coordinator=coordinator,
            device=disconnected_device,
            description=BINARY_SENSOR_TYPES[0],
        )

        # Should be unavailable
        assert sensor.available is False


class TestBHyveTemperatureBinarySensor:
    """Test BHyveTemperatureBinarySensor entity."""

    async def test_temperature_sensor_initialization(
        self,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test temperature binary sensor entity initialization."""
        sensor = BHyveBinarySensor(
            coordinator=mock_coordinator,
            device=mock_flood_device,
            description=BINARY_SENSOR_TYPES[1],
        )

        # Test basic properties
        assert sensor.name == "Basement Flood Sensor temperature alert"
        assert sensor.unique_id == "aa:bb:cc:dd:ee:ff:test-flood-123:tempalert"

    async def test_temperature_sensor_normal_state(
        self,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test temperature sensor in normal state."""
        sensor = BHyveBinarySensor(
            coordinator=mock_coordinator,
            device=mock_flood_device,
            description=BINARY_SENSOR_TYPES[1],
        )

        # Test state
        assert sensor.is_on is False
        assert sensor.available is True

        # Test attributes (temperature thresholds)
        attrs = sensor.extra_state_attributes
        assert attrs["low"] == TEST_TEMP_THRESHOLD_LOW
        assert attrs["high"] == TEST_TEMP_THRESHOLD_HIGH

    async def test_temperature_sensor_alarm_state(
        self,
        mock_flood_device_alarming: BHyveDevice,
    ) -> None:
        """Test temperature sensor in alarm state."""
        coordinator = create_mock_coordinator(
            {
                "test-flood-456": {
                    "device": mock_flood_device_alarming,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveBinarySensor(
            coordinator=coordinator,
            device=mock_flood_device_alarming,
            description=BINARY_SENSOR_TYPES[1],
        )

        # Test state
        assert sensor.is_on is True
        assert sensor.available is True

    async def test_temperature_sensor_websocket_event(
        self,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test temperature sensor response to websocket events."""
        sensor = BHyveBinarySensor(
            coordinator=mock_coordinator,
            device=mock_flood_device,
            description=BINARY_SENSOR_TYPES[1],
        )

        # Initial state should be normal
        assert sensor.is_on is False

        # Simulate coordinator update with alarm status
        mock_coordinator.data["devices"]["test-flood-123"]["device"]["status"][
            "temp_alarm_status"
        ] = "alarm"

        # State should be updated to alarm
        assert sensor.is_on is True

    async def test_temperature_sensor_event_filtering(
        self,
        mock_flood_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test temperature sensor handles all events via coordinator."""
        sensor = BHyveBinarySensor(
            coordinator=mock_coordinator,
            device=mock_flood_device,
            description=BINARY_SENSOR_TYPES[1],
        )

        # Coordinator-based entities don't need event filtering
        # They just read from coordinator.data
        assert sensor.is_on is False


class TestBinarySensorEdgeCases:
    """Test edge cases for binary sensors."""

    async def test_sensors_handle_missing_status_data(
        self,
    ) -> None:
        """Test sensors handle devices with missing status data gracefully."""
        # Device with no status field
        minimal_device = BHyveDevice(
            {
                "id": "test-device-789",
                "name": "Minimal Device",
                "type": "flood_sensor",
                "mac_address": "cc:dd:ee:ff:aa:bb",
                "is_connected": True,
            }
        )

        coordinator = create_mock_coordinator(
            {
                "test-device-789": {
                    "device": minimal_device,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        flood_sensor = BHyveBinarySensor(
            coordinator=coordinator,
            device=minimal_device,
            description=BINARY_SENSOR_TYPES[0],
        )

        temp_sensor = BHyveBinarySensor(
            coordinator=coordinator,
            device=minimal_device,
            description=BINARY_SENSOR_TYPES[1],
        )

        # Should default to "off" state
        assert flood_sensor.is_on is False
        assert temp_sensor.is_on is False
        assert flood_sensor.available is True
        assert temp_sensor.available is True

    async def test_sensors_handle_partial_status_data(
        self,
        mock_flood_device: BHyveDevice,
    ) -> None:
        """Test sensors handle partial status data."""
        # Device with partial status
        partial_device_data = dict(mock_flood_device)
        partial_device_data["status"] = {
            "flood_alarm_status": "alarm"
        }  # Missing temp_alarm_status
        partial_device = BHyveDevice(partial_device_data)

        coordinator = create_mock_coordinator(
            {
                "test-flood-123": {
                    "device": partial_device,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        flood_sensor = BHyveBinarySensor(
            coordinator=coordinator,
            device=partial_device,
            description=BINARY_SENSOR_TYPES[0],
        )

        temp_sensor = BHyveBinarySensor(
            coordinator=coordinator,
            device=partial_device,
            description=BINARY_SENSOR_TYPES[1],
        )

        # Flood sensor should detect alarm, temp sensor should default to off
        assert flood_sensor.is_on is True
        assert temp_sensor.is_on is False
