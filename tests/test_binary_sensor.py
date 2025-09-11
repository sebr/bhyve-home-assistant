"""Test BHyve binary sensor entities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.bhyve.binary_sensor import (
    BHyveFloodSensor,
    BHyveTemperatureBinarySensor,
    async_setup_entry,
)
from custom_components.bhyve.const import EVENT_FS_ALARM
from custom_components.bhyve.pybhyve.client import BHyveClient
from custom_components.bhyve.pybhyve.typings import BHyveDevice

# Test constants
TEST_RSSI_NORMAL = -45
TEST_RSSI_ALARM = -55
TEST_TEMP_THRESHOLD_LOW = 32
TEST_TEMP_THRESHOLD_HIGH = 100
EXPECTED_FLOOD_ENTITIES = 2


@pytest.fixture
def mock_bhyve_client() -> MagicMock:
    """Mock BHyve client."""
    client = MagicMock(spec=BHyveClient)
    client.login = AsyncMock(return_value=True)
    # devices is an async property, so we need to create a mock property
    type(client).devices = AsyncMock(return_value=[])
    client.timer_programs = AsyncMock(return_value=[])
    client.get_device = AsyncMock()
    client.send_message = AsyncMock()
    client.stop = MagicMock()
    return client


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


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    async def test_setup_entry_with_flood_devices(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test setting up binary sensors for flood devices."""
        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_bhyve_client,
                }
            }
        }

        # Mock the client's devices property as an async mock that returns devices
        async def mock_devices() -> list[BHyveDevice]:
            return [mock_flood_device]

        mock_bhyve_client.devices = mock_devices()

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Patch filter_configured_devices to just return the devices as-is
        with patch(
            "custom_components.bhyve.binary_sensor.filter_configured_devices"
        ) as mock_filter:
            mock_filter.return_value = [mock_flood_device]

            # Call setup entry
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Verify entities were added
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]

        # Should create 2 entities: flood sensor and temperature binary sensor
        assert len(entities) == EXPECTED_FLOOD_ENTITIES
        assert isinstance(entities[0], BHyveFloodSensor)
        assert isinstance(entities[1], BHyveTemperatureBinarySensor)

    async def test_setup_entry_no_flood_devices(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test setting up binary sensors with no flood devices."""
        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_bhyve_client,
                }
            }
        }

        # Mock devices list with no flood devices
        sprinkler_device = BHyveDevice({"type": "sprinkler_timer", "name": "Sprinkler"})

        # Mock the client's devices property
        async def mock_devices() -> list[BHyveDevice]:
            return [sprinkler_device]

        mock_bhyve_client.devices = mock_devices()

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Patch filter_configured_devices to return non-flood device
        with patch(
            "custom_components.bhyve.binary_sensor.filter_configured_devices"
        ) as mock_filter:
            mock_filter.return_value = [sprinkler_device]

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
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test flood sensor entity initialization."""
        sensor = BHyveFloodSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Test basic properties
        assert sensor.name == "Basement Flood Sensor flood sensor"
        assert sensor.device_class == BinarySensorDeviceClass.MOISTURE
        assert sensor.unique_id == "aa:bb:cc:dd:ee:ff:test-flood-123:water"

    async def test_flood_sensor_normal_state(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test flood sensor in normal (not flooded) state."""
        sensor = BHyveFloodSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Setup device to populate state
        sensor._setup(mock_flood_device)

        # Test state
        assert sensor.state == "off"
        assert sensor.is_on is False
        assert sensor.available is True

        # Test attributes
        attrs = sensor.extra_state_attributes
        assert attrs["location"] == "Basement"
        assert attrs["shutoff"] is True
        assert attrs["rssi"] == TEST_RSSI_NORMAL

    async def test_flood_sensor_alarm_state(
        self,
        hass: HomeAssistant,
        mock_flood_device_alarming: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test flood sensor in alarm (flooded) state."""
        sensor = BHyveFloodSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device_alarming,
        )

        # Setup device to populate state
        sensor._setup(mock_flood_device_alarming)

        # Test state
        assert sensor.state == "on"
        assert sensor.is_on is True
        assert sensor.available is True

    async def test_flood_sensor_websocket_event(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test flood sensor response to websocket events."""
        sensor = BHyveFloodSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Setup initial state
        sensor._setup(mock_flood_device)
        assert sensor.state == "off"

        # Simulate flood alarm event
        alarm_event = {
            "event": EVENT_FS_ALARM,
            "device_id": "test-flood-123",
            "flood_alarm_status": "alarm",
            "rssi": TEST_RSSI_ALARM,
            "timestamp": "2021-08-29T16:33:17.089Z",
        }

        # Process the websocket event
        sensor._on_ws_data(alarm_event)

        # State should be updated to alarm
        assert sensor.state == "on"
        assert sensor.is_on is True
        assert sensor.extra_state_attributes["rssi"] == TEST_RSSI_ALARM

    async def test_flood_sensor_event_filtering(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test flood sensor only handles relevant events."""
        sensor = BHyveFloodSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Test relevant event
        assert sensor._should_handle_event(EVENT_FS_ALARM, {}) is True

        # Test irrelevant events
        assert sensor._should_handle_event("other_event", {}) is False
        assert sensor._should_handle_event("device_idle", {}) is False

    async def test_flood_sensor_disconnected_device(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test flood sensor with disconnected device."""
        # Create disconnected device
        disconnected_device_data = dict(mock_flood_device)
        disconnected_device_data["is_connected"] = False
        disconnected_device = BHyveDevice(disconnected_device_data)

        sensor = BHyveFloodSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=disconnected_device,
        )

        # Setup device to populate state
        sensor._setup(disconnected_device)

        # Should be unavailable
        assert sensor.available is False


class TestBHyveTemperatureBinarySensor:
    """Test BHyveTemperatureBinarySensor entity."""

    async def test_temperature_sensor_initialization(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test temperature binary sensor entity initialization."""
        sensor = BHyveTemperatureBinarySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Test basic properties
        assert sensor.name == "Basement Flood Sensor temperature alert"
        assert sensor.unique_id == "aa:bb:cc:dd:ee:ff:test-flood-123:tempalert"

    async def test_temperature_sensor_normal_state(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test temperature sensor in normal state."""
        sensor = BHyveTemperatureBinarySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Setup device to populate state
        sensor._setup(mock_flood_device)

        # Test state
        assert sensor.state == "off"
        assert sensor.is_on is False
        assert sensor.available is True

        # Test attributes (temperature thresholds)
        attrs = sensor.extra_state_attributes
        assert attrs["low"] == TEST_TEMP_THRESHOLD_LOW
        assert attrs["high"] == TEST_TEMP_THRESHOLD_HIGH

    async def test_temperature_sensor_alarm_state(
        self,
        hass: HomeAssistant,
        mock_flood_device_alarming: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test temperature sensor in alarm state."""
        sensor = BHyveTemperatureBinarySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device_alarming,
        )

        # Setup device to populate state
        sensor._setup(mock_flood_device_alarming)

        # Test state
        assert sensor.state == "on"
        assert sensor.is_on is True
        assert sensor.available is True

    async def test_temperature_sensor_websocket_event(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test temperature sensor response to websocket events."""
        sensor = BHyveTemperatureBinarySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Setup initial state
        sensor._setup(mock_flood_device)
        assert sensor.state == "off"

        # Simulate temperature alarm event
        alarm_event = {
            "event": EVENT_FS_ALARM,
            "device_id": "test-flood-123",
            "temp_alarm_status": "alarm",
            "temp_f": 110.0,
            "timestamp": "2021-08-29T16:33:17.089Z",
        }

        # Process the websocket event
        sensor._on_ws_data(alarm_event)

        # State should be updated to alarm
        assert sensor.state == "on"
        assert sensor.is_on is True

    async def test_temperature_sensor_event_filtering(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test temperature sensor only handles relevant events."""
        sensor = BHyveTemperatureBinarySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_flood_device,
        )

        # Test relevant event
        assert sensor._should_handle_event(EVENT_FS_ALARM, {}) is True

        # Test irrelevant events
        assert sensor._should_handle_event("other_event", {}) is False
        assert sensor._should_handle_event("device_idle", {}) is False


class TestBinarySensorEdgeCases:
    """Test edge cases for binary sensors."""

    async def test_sensors_handle_missing_status_data(
        self,
        hass: HomeAssistant,
        mock_bhyve_client: MagicMock,
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

        flood_sensor = BHyveFloodSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=minimal_device,
        )

        temp_sensor = BHyveTemperatureBinarySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=minimal_device,
        )

        # Setup should not crash
        flood_sensor._setup(minimal_device)
        temp_sensor._setup(minimal_device)

        # Should default to "off" state
        assert flood_sensor.state == "off"
        assert temp_sensor.state == "off"
        assert flood_sensor.available is True
        assert temp_sensor.available is True

    async def test_sensors_handle_partial_status_data(
        self,
        hass: HomeAssistant,
        mock_flood_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test sensors handle partial status data."""
        # Device with partial status
        partial_device_data = dict(mock_flood_device)
        partial_device_data["status"] = {
            "flood_alarm_status": "alarm"
        }  # Missing temp_alarm_status
        partial_device = BHyveDevice(partial_device_data)

        flood_sensor = BHyveFloodSensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=partial_device,
        )

        temp_sensor = BHyveTemperatureBinarySensor(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=partial_device,
        )

        # Setup should not crash
        flood_sensor._setup(partial_device)
        temp_sensor._setup(partial_device)

        # Flood sensor should detect alarm, temp sensor should default to off
        assert flood_sensor.state == "on"
        assert temp_sensor.state == "off"
