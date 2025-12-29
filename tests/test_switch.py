"""Test BHyve switch entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.pybhyve.typings import BHyveDevice, BHyveTimerProgram
from custom_components.bhyve.switch import (
    BHyveProgramSwitch,
    BHyveRainDelaySwitch,
    async_setup_entry,
)

# Test constants
TEST_RAIN_DELAY_HOURS = 24
TEST_PROGRAM_BUDGET = 100
TEST_DEVICE_ID = "test-device-123"
TEST_PROGRAM_ID = "test-program-456"
EXPECTED_SWITCH_ENTITIES = 2


def create_mock_coordinator(devices: dict, programs: dict) -> MagicMock:
    """Create a mock coordinator with the given devices and programs."""
    coordinator = MagicMock(spec=BHyveDataUpdateCoordinator)
    coordinator.data = {
        "devices": devices,
        "programs": programs,
    }
    coordinator.last_update_success = True
    coordinator.async_set_updated_data = MagicMock()
    coordinator.client = MagicMock()
    coordinator.client.send_message = AsyncMock()
    coordinator.client.update_program = AsyncMock()
    return coordinator


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.options = {}
    return entry


@pytest.fixture
def mock_sprinkler_device() -> BHyveDevice:
    """Mock BHyve sprinkler device."""
    return BHyveDevice(
        {
            "id": TEST_DEVICE_ID,
            "name": "Front Yard Sprinkler",
            "type": "sprinkler_timer",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "hardware_version": "v2.0",
            "firmware_version": "1.2.3",
            "is_connected": True,
            "status": {
                "run_mode": "auto",
                "watering_status": None,
                "rain_delay": 0,
                "rain_delay_started_at": None,
                "rain_delay_cause": None,
                "rain_delay_weather_type": None,
            },
        }
    )


@pytest.fixture
def mock_sprinkler_device_with_rain_delay() -> BHyveDevice:
    """Mock BHyve sprinkler device with active rain delay."""
    return BHyveDevice(
        {
            "id": TEST_DEVICE_ID,
            "name": "Front Yard Sprinkler",
            "type": "sprinkler_timer",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "hardware_version": "v2.0",
            "firmware_version": "1.2.3",
            "is_connected": True,
            "status": {
                "run_mode": "auto",
                "watering_status": None,
                "rain_delay": TEST_RAIN_DELAY_HOURS,
                "rain_delay_started_at": "2020-01-14T12:10:10.000Z",
                "rain_delay_cause": "Weather",
                "rain_delay_weather_type": "Rain",
            },
        }
    )


@pytest.fixture
def mock_timer_program() -> BHyveTimerProgram:
    """Mock BHyve timer program."""
    return BHyveTimerProgram(
        {
            "id": TEST_PROGRAM_ID,
            "device_id": TEST_DEVICE_ID,
            "name": "Morning Schedule",
            "program": "a",
            "enabled": True,
            "is_smart_program": False,
            "frequency": {"type": "days", "days": [1, 2, 3, 4, 5]},
            "start_times": ["06:00"],
            "budget": TEST_PROGRAM_BUDGET,
            "run_times": [{"station": 1, "run_time": 15}],
        }
    )


@pytest.fixture
def mock_timer_program_disabled() -> BHyveTimerProgram:
    """Mock disabled BHyve timer program."""
    return BHyveTimerProgram(
        {
            "id": TEST_PROGRAM_ID,
            "device_id": TEST_DEVICE_ID,
            "name": "Evening Schedule",
            "program": "b",
            "enabled": False,
            "is_smart_program": True,
            "frequency": {"type": "days", "days": [6, 0]},
            "start_times": ["18:00"],
            "budget": 85,
            "run_times": [{"station": 1, "run_time": 20}],
        }
    )


@pytest.fixture
def mock_coordinator(
    mock_sprinkler_device: BHyveDevice, mock_timer_program: BHyveTimerProgram
) -> MagicMock:
    """Mock coordinator with sprinkler device and program data."""
    return create_mock_coordinator(
        {
            TEST_DEVICE_ID: {
                "device": mock_sprinkler_device,
                "history": [],
                "landscapes": {},
            }
        },
        {TEST_PROGRAM_ID: mock_timer_program},
    )


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    async def test_setup_entry_with_sprinkler_devices_and_programs(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test setting up switches for sprinkler devices with programs."""
        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": mock_coordinator,
                    "devices": [mock_sprinkler_device],
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

        # Should create 2 entities: rain delay switch and program switch
        assert len(entities) == EXPECTED_SWITCH_ENTITIES
        assert isinstance(entities[0], BHyveRainDelaySwitch)
        assert isinstance(entities[1], BHyveProgramSwitch)

    async def test_setup_entry_with_device_missing_status(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test setup entry with device missing status attribute."""
        # Create device without status
        device_without_status = BHyveDevice(
            {
                "id": "test-device-456",
                "name": "Broken Device",
                "type": "sprinkler_timer",
                "is_connected": True,
                # Missing 'status' field
            }
        )

        coordinator = create_mock_coordinator(
            {
                "test-device-456": {
                    "device": device_without_status,
                    "history": [],
                    "landscapes": {},
                }
            },
            {},
        )

        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": coordinator,
                    "devices": [device_without_status],
                }
            }
        }

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Call setup entry - should not crash
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Verify no entities were added (device skipped due to missing status)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 0

    async def test_setup_entry_with_non_sprinkler_devices(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test setting up switches with non-sprinkler devices."""
        # Create flood sensor device (non-sprinkler)
        flood_device = BHyveDevice(
            {"id": "test-flood-789", "type": "flood_sensor", "name": "Flood Sensor"}
        )

        coordinator = create_mock_coordinator(
            {
                "test-flood-789": {
                    "device": flood_device,
                    "history": [],
                    "landscapes": {},
                }
            },
            {},
        )

        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": coordinator,
                    "devices": [flood_device],
                }
            }
        }

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Call setup entry
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Verify no entities were added (no sprinkler devices)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 0


class TestBHyveProgramSwitch:
    """Test BHyveProgramSwitch entity."""

    async def test_program_switch_initialization(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test program switch entity initialization."""
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
        )

        # Test basic properties
        assert switch.name == "Front Yard Sprinkler Morning Schedule program"
        assert switch.device_class == SwitchDeviceClass.SWITCH
        assert switch.entity_category == EntityCategory.CONFIG
        assert switch.unique_id == f"bhyve:program:{TEST_PROGRAM_ID}"

    async def test_program_switch_enabled_state(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test program switch in enabled state."""
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
        )

        # Test state (should be enabled)
        assert switch.is_on is True
        assert switch.available is True

        # Test attributes
        attrs = switch.extra_state_attributes
        assert attrs["device_id"] == TEST_DEVICE_ID
        assert attrs["is_smart_program"] is False
        assert attrs["budget"] == TEST_PROGRAM_BUDGET
        assert "frequency" in attrs
        assert "start_times" in attrs

    async def test_program_switch_disabled_state(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program_disabled: BHyveTimerProgram,
    ) -> None:
        """Test program switch in disabled state."""
        coordinator = create_mock_coordinator(
            {
                TEST_DEVICE_ID: {
                    "device": mock_sprinkler_device,
                    "history": [],
                    "landscapes": {},
                }
            },
            {TEST_PROGRAM_ID: mock_timer_program_disabled},
        )

        switch = BHyveProgramSwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program_disabled,
        )

        # Test state (should be disabled)
        assert switch.is_on is False
        assert switch.available is True

    async def test_program_switch_turn_on(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program_disabled: BHyveTimerProgram,
    ) -> None:
        """Test turning on a program switch."""
        coordinator = create_mock_coordinator(
            {
                TEST_DEVICE_ID: {
                    "device": mock_sprinkler_device,
                    "history": [],
                    "landscapes": {},
                }
            },
            {TEST_PROGRAM_ID: mock_timer_program_disabled},
        )

        switch = BHyveProgramSwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program_disabled,
        )

        # Turn on the switch
        await switch.async_turn_on()

        # Verify update_program was called with enabled=True
        coordinator.client.update_program.assert_called_once()
        call_args = coordinator.client.update_program.call_args[0]
        assert call_args[0] == TEST_PROGRAM_ID
        assert call_args[1]["enabled"] is True

    async def test_program_switch_turn_off(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test turning off a program switch."""
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
        )

        # Turn off the switch
        await switch.async_turn_off()

        # Verify update_program was called with enabled=False
        mock_coordinator.client.update_program.assert_called_once()
        call_args = mock_coordinator.client.update_program.call_args[0]
        assert call_args[0] == TEST_PROGRAM_ID
        assert call_args[1]["enabled"] is False

    async def test_program_switch_start_program(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test starting a program manually."""
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
        )

        # Start the program
        await switch.start_program()

        # Verify send_message was called with correct payload
        mock_coordinator.client.send_message.assert_called_once()
        payload = mock_coordinator.client.send_message.call_args[0][0]
        assert payload["event"] == "change_mode"
        assert payload["mode"] == "manual"
        assert payload["device_id"] == TEST_DEVICE_ID
        assert payload["program"] == "a"

    async def test_program_switch_websocket_event(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test program switch response to websocket events."""
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
        )

        # Initial state should be enabled
        assert switch.is_on is True

        # Simulate coordinator update with disabled state
        mock_coordinator.data["programs"][TEST_PROGRAM_ID]["enabled"] = False

        # State should be updated to disabled
        assert switch.is_on is False

    async def test_program_switch_event_filtering(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test program switch handles all events via coordinator."""
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
        )

        # Coordinator-based entities don't need event filtering
        # They just read from coordinator.data
        assert switch.is_on is True


class TestBHyveRainDelaySwitch:
    """Test BHyveRainDelaySwitch entity."""

    async def test_rain_delay_switch_initialization(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test rain delay switch entity initialization."""
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
        )

        # Test basic properties
        assert switch.name == "Front Yard Sprinkler rain delay"
        assert switch.device_class == SwitchDeviceClass.SWITCH
        assert switch.entity_category == EntityCategory.CONFIG
        assert (
            switch.unique_id
            == f"{mock_sprinkler_device['mac_address']}:{TEST_DEVICE_ID}:rain_delay"
        )

    async def test_rain_delay_switch_no_delay_state(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test rain delay switch with no active delay."""
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
        )

        # Test state
        assert switch.is_on is False
        assert switch.available is True

        # Test attributes (should be empty when no delay)
        attrs = switch.extra_state_attributes
        assert attrs == {}

    async def test_rain_delay_switch_active_delay_state(
        self,
        mock_sprinkler_device_with_rain_delay: BHyveDevice,
    ) -> None:
        """Test rain delay switch with active delay."""
        coordinator = create_mock_coordinator(
            {
                TEST_DEVICE_ID: {
                    "device": mock_sprinkler_device_with_rain_delay,
                    "history": [],
                    "landscapes": {},
                }
            },
            {},
        )

        switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_rain_delay,
        )

        # Test state
        assert switch.is_on is True
        assert switch.available is True

        # Test attributes
        attrs = switch.extra_state_attributes
        assert attrs["delay"] == TEST_RAIN_DELAY_HOURS
        assert attrs["cause"] == "Weather"
        assert attrs["weather_type"] == "Rain"
        assert "started_at" in attrs

    async def test_rain_delay_switch_turn_on(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test turning on rain delay switch."""
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
        )

        # Turn on the switch
        await switch.async_turn_on()

        # Verify send_message was called with delay=24
        mock_coordinator.client.send_message.assert_called_once()
        payload = mock_coordinator.client.send_message.call_args[0][0]
        assert payload["event"] == "rain_delay"
        assert payload["device_id"] == TEST_DEVICE_ID
        assert payload["delay"] == 24  # Default 24 hours

    async def test_rain_delay_switch_turn_off(
        self,
        mock_sprinkler_device_with_rain_delay: BHyveDevice,
    ) -> None:
        """Test turning off rain delay switch."""
        coordinator = create_mock_coordinator(
            {
                TEST_DEVICE_ID: {
                    "device": mock_sprinkler_device_with_rain_delay,
                    "history": [],
                    "landscapes": {},
                }
            },
            {},
        )

        switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_rain_delay,
        )

        # Turn off the switch
        await switch.async_turn_off()

        # Verify send_message was called with delay=0
        coordinator.client.send_message.assert_called_once()
        payload = coordinator.client.send_message.call_args[0][0]
        assert payload["event"] == "rain_delay"
        assert payload["device_id"] == TEST_DEVICE_ID
        assert payload["delay"] == 0

    async def test_rain_delay_switch_websocket_event(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test rain delay switch response to websocket events."""
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
        )

        # Initial state should be off (no delay)
        assert switch.is_on is False

        # Simulate coordinator update with rain delay
        mock_coordinator.data["devices"][TEST_DEVICE_ID]["device"]["status"][
            "rain_delay"
        ] = 24

        # State should be updated to on
        assert switch.is_on is True

    async def test_rain_delay_switch_websocket_event_zero_delay(
        self,
        mock_sprinkler_device_with_rain_delay: BHyveDevice,
    ) -> None:
        """Test rain delay switch when delay is set to zero."""
        coordinator = create_mock_coordinator(
            {
                TEST_DEVICE_ID: {
                    "device": mock_sprinkler_device_with_rain_delay,
                    "history": [],
                    "landscapes": {},
                }
            },
            {},
        )

        switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_rain_delay,
        )

        # Initial state should be on (has delay)
        assert switch.is_on is True

        # Simulate coordinator update with zero delay
        coordinator.data["devices"][TEST_DEVICE_ID]["device"]["status"][
            "rain_delay"
        ] = 0

        # State should be updated to off
        assert switch.is_on is False

    async def test_rain_delay_switch_event_filtering(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test rain delay switch handles all events via coordinator."""
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
        )

        # Coordinator-based entities don't need event filtering
        # They just read from coordinator.data
        assert switch.is_on is False

    async def test_rain_delay_switch_disconnected_device(
        self,
        mock_sprinkler_device: BHyveDevice,
    ) -> None:
        """Test rain delay switch with disconnected device."""
        # Create disconnected device
        disconnected_device_data = dict(mock_sprinkler_device)
        disconnected_device_data["is_connected"] = False
        disconnected_device = BHyveDevice(disconnected_device_data)

        coordinator = create_mock_coordinator(
            {
                TEST_DEVICE_ID: {
                    "device": disconnected_device,
                    "history": [],
                    "landscapes": {},
                }
            },
            {},
        )

        switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=disconnected_device,
        )

        # Should be unavailable
        assert switch.available is False


class TestSwitchEdgeCases:
    """Test edge cases for switches."""

    async def test_switches_handle_missing_data_gracefully(
        self,
    ) -> None:
        """Test switches handle devices with missing data gracefully."""
        # Coordinator with minimal device data
        minimal_device = BHyveDevice(
            {
                "id": "test-device-minimal",
                "name": "Minimal Device",
                "type": "sprinkler_timer",
                "mac_address": "ff:ee:dd:cc:bb:aa",
                "is_connected": True,
                "status": {},  # Empty status
            }
        )

        minimal_program = BHyveTimerProgram(
            {
                "id": "test-program-minimal",
                "device_id": "test-device-minimal",
                "name": "Minimal Program",
                "program": "c",
                # Missing many optional fields
            }
        )

        coordinator = create_mock_coordinator(
            {
                "test-device-minimal": {
                    "device": minimal_device,
                    "history": [],
                    "landscapes": {},
                }
            },
            {"test-program-minimal": minimal_program},
        )

        rain_delay_switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=minimal_device,
        )

        program_switch = BHyveProgramSwitch(
            coordinator=coordinator,
            device=minimal_device,
            program=minimal_program,
        )

        # Should handle missing data gracefully
        assert rain_delay_switch.is_on is False
        assert program_switch.is_on is False
        assert rain_delay_switch.available is True
        assert program_switch.available is True

    async def test_switches_handle_websocket_events_without_data(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test switches handle websocket events with missing fields."""
        program_switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
        )

        rain_delay_switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
        )

        # Entities should work even when data is incomplete
        # (coordinator ensures data structure is always present)
        assert program_switch.is_on is True
        assert rain_delay_switch.is_on is False
