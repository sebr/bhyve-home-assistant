"""Test BHyve switch entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator
from custom_components.bhyve.pybhyve.typings import BHyveDevice, BHyveTimerProgram
from custom_components.bhyve.switch import (
    BHyveProgramSwitch,
    BHyveRainDelaySwitch,
    BHyveSmartWateringSwitch,
    BHyveSwitchEntityDescription,
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
    coordinator.client.update_device = AsyncMock()
    return coordinator


def create_program_switch_description() -> BHyveSwitchEntityDescription:
    """Create a program switch description for testing."""
    return BHyveSwitchEntityDescription(
        key="program",
        translation_key="program",
        icon="mdi:bulletin-board",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
    )


def create_rain_delay_switch_description(
    device: BHyveDevice,
) -> BHyveSwitchEntityDescription:
    """Create a rain delay switch description for testing."""
    return BHyveSwitchEntityDescription(
        key="rain_delay",
        name=f"{device.get('name')} rain delay",
        icon="mdi:weather-pouring",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
    )


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
            "is_smart_program": False,
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
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
        )

        # Test basic properties
        assert switch._attr_translation_placeholders == {
            "program_name": "Morning Schedule"
        }
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
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
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

        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program_disabled,
            description=description,
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

        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program_disabled,
            description=description,
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
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
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
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
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
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
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
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
        )

        # Coordinator-based entities don't need event filtering
        # They just read from coordinator.data
        assert switch.is_on is True

    async def test_update_program_config_start_times_only(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test updating only the start_times overrides that field only."""
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
        )

        await switch.async_update_program_config(start_times=["07:30", "19:00"])

        mock_coordinator.client.update_program.assert_called_once()
        program_id, payload = mock_coordinator.client.update_program.call_args[0]
        assert program_id == TEST_PROGRAM_ID
        assert payload["start_times"] == ["07:30", "19:00"]
        # Unchanged fields are preserved
        assert payload["frequency"] == mock_timer_program["frequency"]
        assert payload["enabled"] is True
        assert payload["id"] == TEST_PROGRAM_ID

    async def test_update_program_config_frequency_only(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test updating only the frequency overrides that field only."""
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
        )

        frequency = {
            "type": "days",
            "days": [1, 3, 4],
            "interval": 1,
            "interval_hours": 0,
        }
        await switch.async_update_program_config(frequency=frequency)

        mock_coordinator.client.update_program.assert_called_once()
        program_id, payload = mock_coordinator.client.update_program.call_args[0]
        assert program_id == TEST_PROGRAM_ID
        assert payload["frequency"] == frequency
        # Unchanged fields are preserved
        assert payload["start_times"] == mock_timer_program["start_times"]
        assert payload["enabled"] is True

    async def test_update_program_config_both_fields(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test updating both start_times and frequency together."""
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
        )

        frequency = {"type": "interval", "interval": 2}
        await switch.async_update_program_config(
            start_times=["06:00"], frequency=frequency
        )

        mock_coordinator.client.update_program.assert_called_once()
        program_id, payload = mock_coordinator.client.update_program.call_args[0]
        assert program_id == TEST_PROGRAM_ID
        assert payload["start_times"] == ["06:00"]
        assert payload["frequency"] == frequency
        # Unchanged fields are preserved
        assert payload["enabled"] is True
        assert payload["id"] == TEST_PROGRAM_ID
        assert payload["device_id"] == TEST_DEVICE_ID

    async def test_update_program_config_budget_only(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test updating only the budget overrides that field only."""
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
        )

        await switch.async_update_program_config(budget=150)

        mock_coordinator.client.update_program.assert_called_once()
        program_id, payload = mock_coordinator.client.update_program.call_args[0]
        assert program_id == TEST_PROGRAM_ID
        assert payload["budget"] == 150
        # Unchanged fields are preserved
        assert payload["start_times"] == mock_timer_program["start_times"]
        assert payload["frequency"] == mock_timer_program["frequency"]
        assert payload["enabled"] is True

    async def test_update_program_config_requires_at_least_one_field(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test that the method raises if neither field is provided."""
        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
        )

        with pytest.raises(ServiceValidationError):
            await switch.async_update_program_config()

        mock_coordinator.client.update_program.assert_not_called()

    async def test_setup_registers_update_program_service(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test that async_setup_entry registers the update_program service."""
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": mock_coordinator,
                    "devices": [mock_sprinkler_device],
                }
            }
        }

        assert not hass.services.has_service("bhyve", "update_program")

        await async_setup_entry(hass, mock_config_entry, MagicMock())

        assert hass.services.has_service("bhyve", "update_program")

    async def test_update_program_config_rejects_smart_program(
        self,
        mock_sprinkler_device: BHyveDevice,
    ) -> None:
        """Test that smart programs cannot be updated via this service."""
        smart_program = BHyveTimerProgram(
            {
                "id": TEST_PROGRAM_ID,
                "device_id": TEST_DEVICE_ID,
                "name": "Smart",
                "program": "e",
                "enabled": True,
                "is_smart_program": True,
            }
        )
        coordinator = create_mock_coordinator(
            {
                TEST_DEVICE_ID: {
                    "device": mock_sprinkler_device,
                    "history": [],
                    "landscapes": {},
                }
            },
            {TEST_PROGRAM_ID: smart_program},
        )

        description = create_program_switch_description()
        switch = BHyveProgramSwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device,
            program=smart_program,
            description=description,
        )

        with pytest.raises(ServiceValidationError):
            await switch.async_update_program_config(start_times=["06:00"])

        coordinator.client.update_program.assert_not_called()


class TestBHyveRainDelaySwitch:
    """Test BHyveRainDelaySwitch entity."""

    async def test_rain_delay_switch_initialization(
        self,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test rain delay switch entity initialization."""
        description = create_rain_delay_switch_description(mock_sprinkler_device)
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            description=description,
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
        description = create_rain_delay_switch_description(mock_sprinkler_device)
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            description=description,
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

        description = create_rain_delay_switch_description(
            mock_sprinkler_device_with_rain_delay
        )
        switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_rain_delay,
            description=description,
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
        description = create_rain_delay_switch_description(mock_sprinkler_device)
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            description=description,
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

        description = create_rain_delay_switch_description(
            mock_sprinkler_device_with_rain_delay
        )
        switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_rain_delay,
            description=description,
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
        description = create_rain_delay_switch_description(mock_sprinkler_device)
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            description=description,
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

        description = create_rain_delay_switch_description(
            mock_sprinkler_device_with_rain_delay
        )
        switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=mock_sprinkler_device_with_rain_delay,
            description=description,
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
        description = create_rain_delay_switch_description(mock_sprinkler_device)
        switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            description=description,
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

        description = create_rain_delay_switch_description(disconnected_device)
        switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=disconnected_device,
            description=description,
        )

        # Should be unavailable
        assert switch.available is False


class TestDynamicProgramCreation:
    """Test dynamic program creation via events."""

    async def test_program_created_event_adds_new_switch(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test that bhyve_program_created event creates a new switch entity."""
        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": mock_coordinator,
                    "devices": [mock_sprinkler_device],
                }
            }
        }

        # Track all calls to async_add_entities
        all_added_entities: list[list] = []

        def track_add_entities(entities: list) -> None:
            all_added_entities.append(list(entities))

        async_add_entities = MagicMock(side_effect=track_add_entities)

        # Setup the entry to support async_on_unload
        unload_callbacks: list = []
        mock_config_entry.async_on_unload = unload_callbacks.append

        # Call setup entry
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Verify initial entities were added (rain delay + existing program)
        assert len(all_added_entities) == 1
        assert len(all_added_entities[0]) == EXPECTED_SWITCH_ENTITIES

        # Create a new program
        new_program = {
            "id": "new-program-789",
            "device_id": TEST_DEVICE_ID,
            "name": "New Evening Schedule",
            "program": "c",
            "enabled": True,
            "frequency": {"type": "days", "days": [0, 6]},
            "start_times": ["19:00"],
            "budget": 75,
            "run_times": [{"station": 2, "run_time": 10}],
        }

        # Fire the program created event
        hass.bus.async_fire(
            "bhyve_program_created",
            {"program_id": "new-program-789", "program": new_program},
        )
        await hass.async_block_till_done()

        # Verify a new entity was added
        assert len(all_added_entities) == 2
        assert len(all_added_entities[1]) == 1
        new_entity = all_added_entities[1][0]
        assert isinstance(new_entity, BHyveProgramSwitch)
        assert new_entity._attr_translation_placeholders == {
            "program_name": "New Evening Schedule"
        }

    async def test_program_created_event_unknown_device(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_sprinkler_device: BHyveDevice,
        mock_coordinator: MagicMock,
    ) -> None:
        """Test that program created event for unknown device is ignored."""
        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": mock_coordinator,
                    "devices": [mock_sprinkler_device],
                }
            }
        }

        # Track all calls to async_add_entities
        all_added_entities: list[list] = []

        def track_add_entities(entities: list) -> None:
            all_added_entities.append(list(entities))

        async_add_entities = MagicMock(side_effect=track_add_entities)

        # Setup the entry to support async_on_unload
        mock_config_entry.async_on_unload = lambda _cb: None

        # Call setup entry
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Fire event with unknown device_id
        hass.bus.async_fire(
            "bhyve_program_created",
            {
                "program_id": "orphan-program",
                "program": {
                    "id": "orphan-program",
                    "device_id": "unknown-device-id",
                    "name": "Orphan Program",
                },
            },
        )
        await hass.async_block_till_done()

        # Verify no new entity was added
        assert len(all_added_entities) == 1


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

        description = create_rain_delay_switch_description(minimal_device)
        rain_delay_switch = BHyveRainDelaySwitch(
            coordinator=coordinator,
            device=minimal_device,
            description=description,
        )

        description = create_program_switch_description()
        program_switch = BHyveProgramSwitch(
            coordinator=coordinator,
            device=minimal_device,
            program=minimal_program,
            description=description,
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
        description = create_program_switch_description()
        program_switch = BHyveProgramSwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            description=description,
        )

        description = create_rain_delay_switch_description(mock_sprinkler_device)
        rain_delay_switch = BHyveRainDelaySwitch(
            coordinator=mock_coordinator,
            device=mock_sprinkler_device,
            description=description,
        )

        # Entities should work even when data is incomplete
        # (coordinator ensures data structure is always present)
        assert program_switch.is_on is True
        assert rain_delay_switch.is_on is False


class TestBHyveSmartWateringSwitch:
    """Test BHyveSmartWateringSwitch entity."""

    @staticmethod
    def _create_switch(
        device: BHyveDevice, zone: dict, coordinator: MagicMock | None = None
    ) -> BHyveSmartWateringSwitch:
        if coordinator is None:
            coordinator = create_mock_coordinator(
                {
                    device["id"]: {
                        "device": device,
                        "history": [],
                        "landscapes": {},
                    }
                },
                {},
            )
        return BHyveSmartWateringSwitch(
            coordinator=coordinator,
            device=device,
            zone=zone,
            description=BHyveSwitchEntityDescription(
                key="smart_watering",
                translation_key="smart_watering",
                icon="mdi:auto-fix",
                entity_category=EntityCategory.CONFIG,
            ),
        )

    async def test_single_zone_device_name(self) -> None:
        """Test smart watering switch name for single-zone device."""
        device = BHyveDevice(
            {
                "id": "device-1",
                "name": "Street Lawn",
                "type": "sprinkler_timer",
                "mac_address": "aa:bb:cc:dd:ee:01",
                "hardware_version": "HT25-0000",
                "firmware_version": "0085",
                "is_connected": True,
                "status": {"run_mode": "auto"},
                "zones": [
                    {"station": 1, "smart_watering_enabled": True},
                ],
            }
        )
        switch = self._create_switch(device, device["zones"][0])
        assert switch._attr_name == "Smart watering"

    async def test_multi_zone_device_names(self) -> None:
        """Test smart watering switch names for multi-zone device."""
        device = BHyveDevice(
            {
                "id": "device-2",
                "name": "Dover Gardens",
                "type": "sprinkler_timer",
                "mac_address": "aa:bb:cc:dd:ee:02",
                "hardware_version": "WT25G2-0001",
                "firmware_version": "0087",
                "is_connected": True,
                "status": {"run_mode": "auto"},
                "zones": [
                    {
                        "station": 1,
                        "name": "Front Garden",
                        "smart_watering_enabled": True,
                    },
                    {
                        "station": 2,
                        "name": "Back Garden",
                        "smart_watering_enabled": True,
                    },
                    {
                        "station": 3,
                        "name": "Side Garden",
                        "smart_watering_enabled": False,
                    },
                ],
            }
        )
        switch_1 = self._create_switch(device, device["zones"][0])
        switch_2 = self._create_switch(device, device["zones"][1])
        switch_3 = self._create_switch(device, device["zones"][2])

        assert switch_1._attr_name == "Front Garden smart watering"
        assert switch_2._attr_name == "Back Garden smart watering"
        assert switch_3._attr_name == "Side Garden smart watering"

        # Unique IDs include station
        assert "1:smart_watering" in switch_1.unique_id
        assert "2:smart_watering" in switch_2.unique_id
        assert "3:smart_watering" in switch_3.unique_id

    async def test_is_on_reads_zone_data(self) -> None:
        """Test is_on reflects the zone's smart_watering_enabled value."""
        device = BHyveDevice(
            {
                "id": "device-3",
                "name": "Monash",
                "type": "sprinkler_timer",
                "mac_address": "aa:bb:cc:dd:ee:03",
                "hardware_version": "WT25G2-0001",
                "firmware_version": "0087",
                "is_connected": True,
                "status": {"run_mode": "auto"},
                "zones": [
                    {
                        "station": 1,
                        "name": "Front Lawn",
                        "smart_watering_enabled": True,
                    },
                    {
                        "station": 2,
                        "name": "Back Lawn",
                        "smart_watering_enabled": False,
                    },
                ],
            }
        )
        coordinator = create_mock_coordinator(
            {
                "device-3": {
                    "device": device,
                    "history": [],
                    "landscapes": {},
                }
            },
            {},
        )

        switch_on = self._create_switch(device, device["zones"][0], coordinator)
        switch_off = self._create_switch(device, device["zones"][1], coordinator)

        assert switch_on.is_on is True
        assert switch_off.is_on is False

    async def test_turn_on_patches_zone(self) -> None:
        """Test turning on sets smart_watering_enabled on the zone."""
        device = BHyveDevice(
            {
                "id": "device-4",
                "name": "Test",
                "type": "sprinkler_timer",
                "mac_address": "aa:bb:cc:dd:ee:04",
                "hardware_version": "HT25-0000",
                "firmware_version": "0085",
                "is_connected": True,
                "status": {"run_mode": "auto"},
                "zones": [
                    {"station": 1, "smart_watering_enabled": False},
                    {"station": 2, "smart_watering_enabled": False},
                ],
            }
        )
        coordinator = create_mock_coordinator(
            {"device-4": {"device": device, "history": [], "landscapes": {}}},
            {},
        )
        switch = self._create_switch(device, device["zones"][0], coordinator)

        await switch.async_turn_on()
        coordinator.client.update_device.assert_called_once()
        call_args = coordinator.client.update_device.call_args[0][0]
        assert call_args["id"] == "device-4"
        # Zone 1 should be enabled, zone 2 unchanged
        zones = call_args["zones"]
        assert zones[0]["station"] == 1
        assert zones[0]["smart_watering_enabled"] is True
        assert zones[1]["station"] == 2
        assert zones[1]["smart_watering_enabled"] is False

    async def test_turn_off_patches_zone(self) -> None:
        """Test turning off sets smart_watering_enabled false on the zone."""
        device = BHyveDevice(
            {
                "id": "device-4",
                "name": "Test",
                "type": "sprinkler_timer",
                "mac_address": "aa:bb:cc:dd:ee:04",
                "hardware_version": "HT25-0000",
                "firmware_version": "0085",
                "is_connected": True,
                "status": {"run_mode": "auto"},
                "zones": [
                    {"station": 1, "smart_watering_enabled": True},
                    {"station": 2, "smart_watering_enabled": True},
                ],
            }
        )
        coordinator = create_mock_coordinator(
            {"device-4": {"device": device, "history": [], "landscapes": {}}},
            {},
        )
        switch = self._create_switch(device, device["zones"][0], coordinator)

        await switch.async_turn_off()
        coordinator.client.update_device.assert_called_once()
        call_args = coordinator.client.update_device.call_args[0][0]
        zones = call_args["zones"]
        # Zone 1 should be disabled, zone 2 unchanged
        assert zones[0]["smart_watering_enabled"] is False
        assert zones[1]["smart_watering_enabled"] is True

    async def test_setup_creates_per_zone_switches(self, hass: HomeAssistant) -> None:
        """Test setup creates one smart watering switch per zone."""
        device = BHyveDevice(
            {
                "id": "dover-gardens",
                "name": "Dover Gardens",
                "type": "sprinkler_timer",
                "mac_address": "4467550a3f05",
                "hardware_version": "WT25G2-0001",
                "firmware_version": "0087",
                "is_connected": True,
                "smart_watering_enabled": True,
                "status": {
                    "run_mode": "auto",
                    "watering_status": None,
                },
                "zones": [
                    {
                        "station": 1,
                        "name": "Front Garden",
                        "smart_watering_enabled": True,
                    },
                    {
                        "station": 2,
                        "name": "Front Garden by House",
                        "smart_watering_enabled": True,
                    },
                    {
                        "station": 3,
                        "name": "Back Garden West",
                        "smart_watering_enabled": True,
                    },
                    {
                        "station": 4,
                        "name": "Back Garden Middle",
                        "smart_watering_enabled": True,
                    },
                    {
                        "station": 5,
                        "name": "Back Garden East",
                        "smart_watering_enabled": True,
                    },
                ],
            }
        )

        coordinator = create_mock_coordinator(
            {
                "dover-gardens": {
                    "device": device,
                    "history": [],
                    "landscapes": {},
                }
            },
            {},
        )

        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "coordinator": coordinator,
                    "devices": [device],
                }
            }
        }

        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_id"
        entry.options = {}
        entry.async_on_unload = lambda _cb: None

        added_entities: list = []

        def track_add(entities: list) -> None:
            added_entities.extend(entities)

        await async_setup_entry(hass, entry, MagicMock(side_effect=track_add))

        smart_switches = [
            e for e in added_entities if isinstance(e, BHyveSmartWateringSwitch)
        ]
        assert len(smart_switches) == 5

        names = [s._attr_name for s in smart_switches]
        assert "Front Garden smart watering" in names
        assert "Back Garden West smart watering" in names
