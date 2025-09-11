"""Test BHyve sensor entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant

from custom_components.bhyve.pybhyve.client import BHyveClient
from custom_components.bhyve.pybhyve.typings import BHyveDevice
from custom_components.bhyve.sensor import (
    BHyveBatterySensor,
    BHyveStateSensor,
    BHyveTemperatureSensor,
    BHyveZoneHistorySensor,
)

# Test constants
TEST_BATTERY_LEVEL = 85
TEST_BATTERY_LEVEL_UPDATED = 50
TEST_TEMPERATURE_FAHRENHEIT = 72.5


@pytest.fixture
def mock_bhyve_client() -> MagicMock:
    """Mock BHyve client."""
    client = MagicMock(spec=BHyveClient)
    client.login = AsyncMock(return_value=True)
    client.devices = AsyncMock(return_value=[])
    client.timer_programs = AsyncMock(return_value=[])
    client.get_device = AsyncMock()
    client.send_message = AsyncMock()
    client.get_device_history = AsyncMock()
    client.stop = MagicMock()
    return client


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
            },
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
        hass: HomeAssistant,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test battery sensor entity initialization."""
        sensor = BHyveBatterySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
        )

        # Test basic properties
        assert sensor.name == "Test Sprinkler battery level"
        assert sensor.device_class == SensorDeviceClass.BATTERY
        assert sensor._state_class == SensorStateClass.MEASUREMENT
        assert sensor._attr_native_unit_of_measurement == PERCENTAGE
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC

    async def test_battery_sensor_state(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test battery sensor state and attributes."""
        sensor = BHyveBatterySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
        )

        # Setup device to populate state
        sensor._setup(mock_sprinkler_device_with_battery)

        # Test state
        assert sensor.state == TEST_BATTERY_LEVEL
        assert sensor.available is True

        # Test icon changes based on battery level
        assert "battery" in sensor.icon

    async def test_battery_sensor_websocket_event(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test battery sensor response to websocket events."""
        sensor = BHyveBatterySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
        )

        # Simulate battery status update
        battery_event = {
            "event": "battery_status",
            "device_id": "test-device-123",
            "percent": 50,
            "timestamp": "2020-01-09T21:00:00.000Z",
        }

        # Process the websocket event
        sensor._on_ws_data(battery_event)

        # Battery level should be updated
        assert sensor.state == TEST_BATTERY_LEVEL_UPDATED


class TestBHyveStateSensor:
    """Test BHyveStateSensor entity."""

    async def test_state_sensor_initialization(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test state sensor entity initialization."""
        sensor = BHyveStateSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
        )

        # Test basic properties
        assert sensor.name == "Test Sprinkler state"
        assert sensor.device_class is None

    async def test_state_sensor_values(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test state sensor state values."""
        sensor = BHyveStateSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
        )

        # Setup device to populate state
        sensor._setup(mock_sprinkler_device_with_battery)

        # Test initial state
        assert sensor.state == "auto"
        assert sensor.available is True


class TestBHyveTemperatureSensor:
    """Test BHyveTemperatureSensor entity."""

    async def test_temperature_sensor_initialization(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test temperature sensor entity initialization."""
        sensor = BHyveTemperatureSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Test basic properties
        assert sensor.name == "Test Flood Sensor temperature sensor"
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE

    async def test_temperature_sensor_state(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test temperature sensor state."""
        sensor = BHyveTemperatureSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Setup device to populate state
        sensor._setup(mock_flood_device)

        # Test state after setup
        assert sensor._attr_native_value == TEST_TEMPERATURE_FAHRENHEIT
        assert sensor._attr_native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT
        assert sensor._state_class == SensorStateClass.MEASUREMENT
        assert sensor.available is True


class TestBHyveZoneHistorySensor:
    """Test BHyveZoneHistorySensor entity."""

    async def test_zone_history_sensor_initialization(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test zone history sensor entity initialization."""
        zone_data = {"station": "1", "name": "Front Yard"}
        zone_name = "Front Yard"

        sensor = BHyveZoneHistorySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
            zone=zone_data,
            zone_name=zone_name,
        )

        # Test basic properties
        assert sensor.name == "Front Yard zone history"
        assert sensor.device_class == "timestamp"

    async def test_zone_history_sensor_attributes(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_bhyve_client: MagicMock,
        mock_zone_history_data: list,
    ) -> None:
        """Test zone history sensor attributes."""
        zone_data = {"station": "1", "name": "Front Yard"}
        zone_name = "Front Yard"

        sensor = BHyveZoneHistorySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
            zone=zone_data,
            zone_name=zone_name,
        )

        # Mock the device history fetch
        mock_bhyve_client.get_device_history.return_value = mock_zone_history_data

        # Update sensor to fetch history
        await sensor.async_update()

        # Test that history data is processed
        attrs = sensor.extra_state_attributes

        # Check that watering event attributes are set
        irrigation_event = mock_zone_history_data[0]["irrigation"][0]
        assert attrs.get("budget") == irrigation_event["budget"]
        assert attrs.get("program") == irrigation_event["program"]
        assert attrs.get("program_name") == irrigation_event["program_name"]
        assert attrs.get("run_time") == irrigation_event["run_time"]
        assert attrs.get("status") == irrigation_event["status"]
        assert attrs.get("consumption_gallons") == irrigation_event["water_volume_gal"]
        assert attrs.get("consumption_litres") == round(
            irrigation_event["water_volume_gal"] * 3.785, 2
        )


class TestSensorWebsocketEvents:
    """Test sensor responses to websocket events."""

    async def test_sensors_handle_device_connection_events(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_battery: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test sensors handle device connection/disconnection events."""
        battery_sensor = BHyveBatterySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
        )

        state_sensor = BHyveStateSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_battery,
        )

        # Initially available
        battery_sensor._setup(mock_sprinkler_device_with_battery)
        state_sensor._setup(mock_sprinkler_device_with_battery)

        assert battery_sensor.available is True
        assert state_sensor.available is True

        # Simulate device disconnection
        disconnected_device_data = dict(mock_sprinkler_device_with_battery)
        disconnected_device_data["is_connected"] = False
        disconnected_device = BHyveDevice(disconnected_device_data)

        battery_sensor._setup(disconnected_device)
        state_sensor._setup(disconnected_device)

        # Sensors should be unavailable
        assert battery_sensor.available is False
        assert state_sensor.available is False
