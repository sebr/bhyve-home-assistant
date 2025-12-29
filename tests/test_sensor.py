"""Test BHyve sensor entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature

from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.pybhyve.typings import BHyveDevice
from custom_components.bhyve.sensor import (
    SENSOR_TYPES_BATTERY,
    SENSOR_TYPES_FLOOD,
    SENSOR_TYPES_SPRINKLER,
    BHyveSensor,
    BHyveZoneHistorySensor,
)

# Test constants
TEST_BATTERY_LEVEL = 85
TEST_BATTERY_LEVEL_UPDATED = 50
TEST_TEMPERATURE_FAHRENHEIT = 72.5


def create_mock_coordinator(devices: dict) -> MagicMock:
    """Create a mock coordinator with the given devices."""
    coordinator = MagicMock(spec=BHyveDataUpdateCoordinator)
    coordinator.data = {
        "devices": devices,
        "programs": {},
    }
    coordinator.last_update_success = True
    coordinator.async_set_updated_data = MagicMock()
    coordinator.client = MagicMock()
    coordinator.client.send_message = AsyncMock()
    return coordinator


@pytest.fixture
def mock_sprinkler_device_with_battery() -> BHyveDevice:
    """Mock BHyve sprinkler device with battery data."""
    return BHyveDevice(
        {
            "id": "test-device-123",
            "name": "Test Sprinkler",
            "type": "sprinkler_timer",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "hardware_version": "v2.0",
            "firmware_version": "1.2.3",
            "is_connected": True,
            "battery": {
                "percent": TEST_BATTERY_LEVEL,
                "charging": False,
            },
            "status": {
                "run_mode": "auto",
                "watering_status": None,
            },
            "zones": [{"station": "1", "name": "Front Lawn"}],
        }
    )


@pytest.fixture
def mock_flood_device() -> BHyveDevice:
    """Mock BHyve flood sensor device."""
    return BHyveDevice(
        {
            "id": "test-flood-456",
            "name": "Test Flood Sensor",
            "type": "flood_sensor",
            "mac_address": "bb:cc:dd:ee:ff:aa",
            "hardware_version": "v1.0",
            "firmware_version": "2.1.0",
            "is_connected": True,
            "battery": {
                "percent": 90,
                "charging": False,
            },
            "status": {
                "temp_f": TEST_TEMPERATURE_FAHRENHEIT,
                "rssi": -45,
                "temp_alarm_status": "ok",
            },
            "location_name": "Basement",
        }
    )


@pytest.fixture
def mock_zone_history_data() -> list:
    """Mock zone history data."""
    return [
        {
            "irrigation": [
                {
                    "station": "1",
                    "budget": 100,
                    "program": "a",
                    "program_name": "Morning Schedule",
                    "run_time": 15,
                    "status": "completed",
                    "water_volume_gal": 25.5,
                    "start_time": "2020-01-09T20:15:00.000Z",
                }
            ]
        }
    ]


class TestBHyveBatterySensor:
    """Test BHyveBatterySensor entity."""

    async def test_battery_sensor_initialization(
        self,
        mock_sprinkler_device_with_battery: BHyveDevice,
    ) -> None:
        """Test battery sensor entity initialization."""
        coordinator = create_mock_coordinator(
            {
                "test-device-123": {
                    "device": mock_sprinkler_device_with_battery,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            description=SENSOR_TYPES_BATTERY[0],
        )

        # Test basic properties
        assert sensor.name == "Test Sprinkler battery level"
        assert sensor.device_class == SensorDeviceClass.BATTERY
        assert sensor.entity_description.state_class == SensorStateClass.MEASUREMENT
        assert sensor.entity_description.native_unit_of_measurement == PERCENTAGE
        assert sensor.entity_description.entity_category == EntityCategory.DIAGNOSTIC

    async def test_battery_sensor_state(
        self,
        mock_sprinkler_device_with_battery: BHyveDevice,
    ) -> None:
        """Test battery sensor state and attributes."""
        coordinator = create_mock_coordinator(
            {
                "test-device-123": {
                    "device": mock_sprinkler_device_with_battery,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            description=SENSOR_TYPES_BATTERY[0],
        )

        # Test state
        assert sensor.native_value == TEST_BATTERY_LEVEL
        assert sensor.available is True

        # Test icon changes based on battery level
        assert sensor.icon is not None
        assert "battery" in sensor.icon

    async def test_battery_sensor_websocket_event(
        self,
        mock_sprinkler_device_with_battery: BHyveDevice,
    ) -> None:
        """Test battery sensor response to websocket events."""
        coordinator = create_mock_coordinator(
            {
                "test-device-123": {
                    "device": mock_sprinkler_device_with_battery,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            description=SENSOR_TYPES_BATTERY[0],
        )

        # Initial state
        assert sensor.native_value == TEST_BATTERY_LEVEL

        # Simulate coordinator update with new battery level
        coordinator.data["devices"]["test-device-123"]["device"]["battery"][
            "percent"
        ] = TEST_BATTERY_LEVEL_UPDATED

        # State should be updated
        assert sensor.native_value == TEST_BATTERY_LEVEL_UPDATED


class TestBHyveStateSensor:
    """Test BHyveStateSensor entity."""

    async def test_state_sensor_initialization(
        self,
        mock_sprinkler_device_with_battery: BHyveDevice,
    ) -> None:
        """Test state sensor entity initialization."""
        coordinator = create_mock_coordinator(
            {
                "test-device-123": {
                    "device": mock_sprinkler_device_with_battery,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            description=SENSOR_TYPES_SPRINKLER[0],
        )

        # Test basic properties
        assert sensor.name == "Test Sprinkler state"
        assert sensor.entity_description.entity_category == EntityCategory.DIAGNOSTIC

    async def test_state_sensor_values(
        self,
        mock_sprinkler_device_with_battery: BHyveDevice,
    ) -> None:
        """Test state sensor with different run modes."""
        coordinator = create_mock_coordinator(
            {
                "test-device-123": {
                    "device": mock_sprinkler_device_with_battery,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            description=SENSOR_TYPES_SPRINKLER[0],
        )

        # Test initial state
        assert sensor.native_value == "auto"

        # Simulate coordinator update
        coordinator.data["devices"]["test-device-123"]["device"]["status"][
            "run_mode"
        ] = "manual"

        assert sensor.native_value == "manual"


class TestBHyveTemperatureSensor:
    """Test BHyveTemperatureSensor entity."""

    async def test_temperature_sensor_initialization(
        self,
        mock_flood_device: BHyveDevice,
    ) -> None:
        """Test temperature sensor entity initialization."""
        coordinator = create_mock_coordinator(
            {
                "test-flood-456": {
                    "device": mock_flood_device,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_flood_device,
            description=SENSOR_TYPES_FLOOD[0],
        )

        # Test basic properties
        assert sensor.name == "Test Flood Sensor temperature sensor"
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.entity_description.state_class == SensorStateClass.MEASUREMENT
        assert (
            sensor.entity_description.native_unit_of_measurement
            == UnitOfTemperature.FAHRENHEIT
        )

    async def test_temperature_sensor_state(
        self,
        mock_flood_device: BHyveDevice,
    ) -> None:
        """Test temperature sensor state and attributes."""
        coordinator = create_mock_coordinator(
            {
                "test-flood-456": {
                    "device": mock_flood_device,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_flood_device,
            description=SENSOR_TYPES_FLOOD[0],
        )

        # Test state
        assert sensor.native_value == TEST_TEMPERATURE_FAHRENHEIT
        assert sensor.available is True

        # Test attributes
        attrs = sensor.extra_state_attributes
        assert attrs["location"] == "Basement"
        assert attrs["rssi"] == -45
        assert attrs["temperature_alarm"] == "ok"


class TestBHyveZoneHistorySensor:
    """Test BHyveZoneHistorySensor entity."""

    async def test_zone_history_sensor_initialization(
        self,
        mock_sprinkler_device_with_battery: BHyveDevice,
    ) -> None:
        """Test zone history sensor entity initialization."""
        coordinator = create_mock_coordinator(
            {
                "test-device-123": {
                    "device": mock_sprinkler_device_with_battery,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        zone = {"station": "1", "name": "Front Lawn"}

        sensor = BHyveZoneHistorySensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            zone=zone,
            zone_name="Front Lawn",
        )

        # Test basic properties
        assert sensor.name == "Front Lawn zone history"
        assert sensor._attr_device_class == SensorDeviceClass.TIMESTAMP
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC

    async def test_zone_history_sensor_attributes(
        self,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_zone_history_data: list,
    ) -> None:
        """Test zone history sensor with history data."""
        coordinator = create_mock_coordinator(
            {
                "test-device-123": {
                    "device": mock_sprinkler_device_with_battery,
                    "history": mock_zone_history_data,
                    "landscapes": {},
                }
            }
        )

        zone = {"station": "1", "name": "Front Lawn"}

        sensor = BHyveZoneHistorySensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            zone=zone,
            zone_name="Front Lawn",
        )

        # Test state (should be ISO timestamp)
        assert sensor.native_value is not None
        assert "2020-01-09" in sensor.native_value

        # Test attributes
        attrs = sensor.extra_state_attributes
        assert attrs["budget"] == 100
        assert attrs["program"] == "a"
        assert attrs["program_name"] == "Morning Schedule"
        assert attrs["run_time"] == 15
        assert attrs["status"] == "completed"
        assert attrs["consumption_gallons"] == 25.5
        assert attrs["consumption_litres"] == 96.52


class TestSensorWebsocketEvents:
    """Test sensor response to websocket events."""

    async def test_sensors_handle_device_connection_events(
        self,
        mock_sprinkler_device_with_battery: BHyveDevice,
    ) -> None:
        """Test sensors handle device connection/disconnection events."""
        coordinator = create_mock_coordinator(
            {
                "test-device-123": {
                    "device": mock_sprinkler_device_with_battery,
                    "history": [],
                    "landscapes": {},
                }
            }
        )

        battery_sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            description=SENSOR_TYPES_BATTERY[0],
        )

        state_sensor = BHyveSensor(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_battery,
            description=SENSOR_TYPES_SPRINKLER[0],
        )

        # Initial state - sensors should be available
        assert battery_sensor.available is True
        assert state_sensor.available is True

        # Simulate device disconnection
        coordinator.data["devices"]["test-device-123"]["device"]["is_connected"] = False

        # Sensors should be unavailable
        assert battery_sensor.available is False
        assert state_sensor.available is False
