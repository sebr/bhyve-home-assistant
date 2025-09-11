"""Test BHyve switch entities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from custom_components.bhyve.const import EVENT_PROGRAM_CHANGED, EVENT_RAIN_DELAY
from custom_components.bhyve.pybhyve.client import BHyveClient
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


@pytest.fixture
def mock_bhyve_client() -> MagicMock:
    """Mock BHyve client."""
    client = MagicMock(spec=BHyveClient)
    client.login = AsyncMock(return_value=True)
    # devices and timer_programs are async properties
    type(client).devices = AsyncMock(return_value=[])
    type(client).timer_programs = AsyncMock(return_value=[])
    client.get_device = AsyncMock()
    client.send_message = AsyncMock()
    client.update_program = AsyncMock()
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


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    async def test_setup_entry_with_sprinkler_devices_and_programs(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test setting up switches for sprinkler devices with programs."""
        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_bhyve_client,
                }
            }
        }

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Patch filter_configured_devices and async properties
        with patch(
            "custom_components.bhyve.switch.filter_configured_devices"
        ) as mock_filter:
            mock_filter.return_value = [mock_sprinkler_device]

            # Mock the client's async properties
            async def mock_devices() -> list[BHyveDevice]:
                return [mock_sprinkler_device]

            async def mock_programs() -> list[BHyveTimerProgram]:
                return [mock_timer_program]

            mock_bhyve_client.devices = mock_devices()
            mock_bhyve_client.timer_programs = mock_programs()

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
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test setup entry with device missing status attribute."""
        # Create device without status
        device_without_status = BHyveDevice(
            {
                "id": TEST_DEVICE_ID,
                "name": "Broken Sprinkler",
                "type": "sprinkler_timer",
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "is_connected": True,
                # Missing 'status' field
            }
        )

        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_bhyve_client,
                }
            }
        }

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Patch filter_configured_devices
        with patch(
            "custom_components.bhyve.switch.filter_configured_devices"
        ) as mock_filter:
            mock_filter.return_value = [device_without_status]

            # Mock the client's async properties
            async def mock_devices() -> list[BHyveDevice]:
                return [device_without_status]

            async def mock_programs() -> list[BHyveTimerProgram]:
                return []

            mock_bhyve_client.devices = mock_devices()
            mock_bhyve_client.timer_programs = mock_programs()

            # Call setup entry
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Verify no entities were added due to missing status
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 0

    async def test_setup_entry_with_non_sprinkler_devices(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test setup entry with non-sprinkler devices."""
        # Create non-sprinkler device
        flood_device = BHyveDevice(
            {
                "id": "flood-123",
                "name": "Flood Sensor",
                "type": "flood_sensor",
                "mac_address": "bb:cc:dd:ee:ff:aa",
                "is_connected": True,
            }
        )

        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_bhyve_client,
                }
            }
        }

        # Mock async_add_entities
        async_add_entities = MagicMock()

        # Patch filter_configured_devices
        with patch(
            "custom_components.bhyve.switch.filter_configured_devices"
        ) as mock_filter:
            mock_filter.return_value = [flood_device]

            # Mock the client's async properties
            async def mock_devices() -> list[BHyveDevice]:
                return [flood_device]

            async def mock_programs() -> list[BHyveTimerProgram]:
                return []

            mock_bhyve_client.devices = mock_devices()
            mock_bhyve_client.timer_programs = mock_programs()

            # Call setup entry
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Verify no entities were added for non-sprinkler device
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 0


class TestBHyveProgramSwitch:
    """Test BHyveProgramSwitch entity."""

    async def test_program_switch_initialization(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test program switch entity initialization."""
        switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            icon="bulletin-board",
        )

        # Test basic properties
        assert switch.name == "Front Yard Sprinkler Morning Schedule program"
        assert switch.device_class == SwitchDeviceClass.SWITCH
        assert switch.unique_id == f"bhyve:program:{TEST_PROGRAM_ID}"
        assert switch.entity_category == EntityCategory.CONFIG
        assert switch.available is True

    async def test_program_switch_enabled_state(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test program switch with enabled program."""
        switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            icon="bulletin-board",
        )

        # Test state
        assert switch.is_on is True

        # Test attributes
        attrs = switch.extra_state_attributes
        assert attrs["device_id"] == TEST_DEVICE_ID
        assert attrs["is_smart_program"] is False
        assert attrs["frequency"] == {"type": "days", "days": [1, 2, 3, 4, 5]}
        assert attrs["start_times"] == ["06:00"]
        assert attrs["budget"] == TEST_PROGRAM_BUDGET
        assert attrs["program"] == "a"
        assert attrs["run_times"] == [{"station": 1, "run_time": 15}]

    async def test_program_switch_disabled_state(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program_disabled: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test program switch with disabled program."""
        switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program_disabled,
            icon="bulletin-board",
        )

        # Test state
        assert switch.is_on is False

        # Test smart program attribute
        attrs = switch.extra_state_attributes
        assert attrs["is_smart_program"] is True

    async def test_program_switch_turn_on(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program_disabled: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test turning on program switch."""
        switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program_disabled,
            icon="bulletin-board",
        )

        # Initially disabled
        assert switch.is_on is False

        # Turn on
        await switch.async_turn_on()

        # Verify update_program was called
        mock_bhyve_client.update_program.assert_called_once_with(
            TEST_PROGRAM_ID, mock_timer_program_disabled
        )

        # Program should be updated to enabled
        assert mock_timer_program_disabled["enabled"] is True

    async def test_program_switch_turn_off(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test turning off program switch."""
        switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            icon="bulletin-board",
        )

        # Initially enabled
        assert switch.is_on is True

        # Turn off
        await switch.async_turn_off()

        # Verify update_program was called
        mock_bhyve_client.update_program.assert_called_once_with(
            TEST_PROGRAM_ID, mock_timer_program
        )

        # Program should be updated to disabled
        assert mock_timer_program["enabled"] is False

    async def test_program_switch_start_program(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test starting a program manually."""
        switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            icon="bulletin-board",
        )

        # Start program
        await switch.start_program()

        # Verify send_message was called with correct payload structure
        mock_bhyve_client.send_message.assert_called_once()
        call_args = mock_bhyve_client.send_message.call_args[0][0]

        assert call_args["event"] == "change_mode"
        assert call_args["mode"] == "manual"
        assert call_args["device_id"] == TEST_DEVICE_ID
        assert call_args["program"] == "a"
        assert "timestamp" in call_args

    async def test_program_switch_websocket_event(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test program switch response to websocket events."""
        switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            icon="bulletin-board",
        )

        # Test initial program
        assert switch._program["enabled"] is True

        # Simulate program changed event
        new_program_data = {
            "enabled": False,
            "budget": 80,
            "frequency": {"type": "days", "days": [1, 3, 5]},
        }

        program_event = {
            "event": EVENT_PROGRAM_CHANGED,
            "program": new_program_data,
        }

        # Process the websocket event
        switch._on_ws_data(program_event)

        # Program should be updated
        assert switch._program == new_program_data
        assert switch.is_on is False

    async def test_program_switch_event_filtering(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test program switch only handles relevant events."""
        switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            icon="bulletin-board",
        )

        # Test relevant event
        assert switch._should_handle_event(EVENT_PROGRAM_CHANGED, {}) is True

        # Test irrelevant events
        assert switch._should_handle_event("other_event", {}) is False
        assert switch._should_handle_event(EVENT_RAIN_DELAY, {}) is False


class TestBHyveRainDelaySwitch:
    """Test BHyveRainDelaySwitch entity."""

    async def test_rain_delay_switch_initialization(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test rain delay switch entity initialization."""
        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            icon="weather-pouring",
        )

        # Test basic properties
        assert switch.name == "Front Yard Sprinkler rain delay"
        assert switch.device_class == SwitchDeviceClass.SWITCH
        assert switch.unique_id == f"aa:bb:cc:dd:ee:ff:{TEST_DEVICE_ID}:rain_delay"
        assert switch.entity_category == EntityCategory.CONFIG

    async def test_rain_delay_switch_no_delay_state(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test rain delay switch with no active delay."""
        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            icon="weather-pouring",
        )

        # Setup device to populate state
        switch._setup(mock_sprinkler_device)

        # Test state
        assert switch.is_on is False
        assert switch.available is True

        # Test attributes - when no rain delay, attrs should be empty
        attrs = switch.extra_state_attributes
        assert attrs == {}

    async def test_rain_delay_switch_active_delay_state(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_rain_delay: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test rain delay switch with active delay."""
        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_rain_delay,
            icon="weather-pouring",
        )

        # Setup device to populate state
        switch._setup(mock_sprinkler_device_with_rain_delay)

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
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test turning on rain delay switch."""
        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            icon="weather-pouring",
        )

        # Setup device
        switch._setup(mock_sprinkler_device)

        # Initially off
        assert switch.is_on is False

        # Mock the enable_rain_delay method
        switch.enable_rain_delay = AsyncMock()

        # Turn on
        await switch.async_turn_on()

        # Verify state changed and method was called
        assert switch.is_on is True
        switch.enable_rain_delay.assert_called_once()

    async def test_rain_delay_switch_turn_off(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_rain_delay: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test turning off rain delay switch."""
        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_rain_delay,
            icon="weather-pouring",
        )

        # Setup device
        switch._setup(mock_sprinkler_device_with_rain_delay)

        # Initially on
        assert switch.is_on is True

        # Mock the disable_rain_delay method
        switch.disable_rain_delay = AsyncMock()

        # Turn off
        await switch.async_turn_off()

        # Verify state changed and method was called
        assert switch.is_on is False
        switch.disable_rain_delay.assert_called_once()

    async def test_rain_delay_switch_websocket_event(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test rain delay switch response to websocket events."""
        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            icon="weather-pouring",
        )

        # Setup device
        switch._setup(mock_sprinkler_device)

        # Initially no delay
        assert switch.is_on is False

        # Mock _update_device_soon to avoid timer complexity
        switch._update_device_soon = MagicMock()

        # Simulate rain delay event
        rain_delay_event = {
            "event": EVENT_RAIN_DELAY,
            "device_id": TEST_DEVICE_ID,
            "delay": TEST_RAIN_DELAY_HOURS,
            "timestamp": "2020-01-14T12:10:10.000Z",
        }

        # Process the websocket event
        switch._on_ws_data(rain_delay_event)

        # State should be updated and device refresh should be scheduled
        assert switch.is_on is True
        switch._update_device_soon.assert_called_once()

    async def test_rain_delay_switch_websocket_event_zero_delay(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device_with_rain_delay: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test rain delay switch response to zero delay websocket event."""
        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device_with_rain_delay,
            icon="weather-pouring",
        )

        # Setup device with active delay
        switch._setup(mock_sprinkler_device_with_rain_delay)

        # Initially has delay
        assert switch.is_on is True

        # Mock _update_device_soon
        switch._update_device_soon = MagicMock()

        # Simulate rain delay disabled event
        rain_delay_event = {
            "event": EVENT_RAIN_DELAY,
            "device_id": TEST_DEVICE_ID,
            "delay": 0,
            "timestamp": "2020-01-14T12:10:10.000Z",
        }

        # Process the websocket event
        switch._on_ws_data(rain_delay_event)

        # State should be updated to off
        assert switch.is_on is False
        switch._update_device_soon.assert_called_once()

    async def test_rain_delay_switch_event_filtering(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test rain delay switch only handles relevant events."""
        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            icon="weather-pouring",
        )

        # Test relevant event
        assert switch._should_handle_event(EVENT_RAIN_DELAY, {}) is True

        # Test irrelevant events
        assert switch._should_handle_event("other_event", {}) is False
        assert switch._should_handle_event(EVENT_PROGRAM_CHANGED, {}) is False

    async def test_rain_delay_switch_disconnected_device(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test rain delay switch with disconnected device."""
        # Create disconnected device
        disconnected_device_data = dict(mock_sprinkler_device)
        disconnected_device_data["is_connected"] = False
        disconnected_device = BHyveDevice(disconnected_device_data)

        switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=disconnected_device,
            icon="weather-pouring",
        )

        # Setup device to populate state
        switch._setup(disconnected_device)

        # Should be unavailable
        assert switch.available is False


class TestSwitchEdgeCases:
    """Test edge cases for switches."""

    async def test_switches_handle_missing_data_gracefully(
        self,
        hass: HomeAssistant,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test switches handle missing data gracefully."""
        # Device with minimal data
        minimal_device = BHyveDevice(
            {
                "id": TEST_DEVICE_ID,
                "name": "Minimal Device",
                "type": "sprinkler_timer",
                "mac_address": "cc:dd:ee:ff:aa:bb",
                "is_connected": True,
                "status": {},  # Empty status
            }
        )

        # Program with minimal data
        minimal_program = BHyveTimerProgram(
            {
                "id": TEST_PROGRAM_ID,
                "device_id": TEST_DEVICE_ID,
                "name": "Minimal Program",
                "program": "a",
                # Missing many optional fields
            }
        )

        program_switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=minimal_device,
            program=minimal_program,
            icon="bulletin-board",
        )

        rain_delay_switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=minimal_device,
            icon="weather-pouring",
        )

        # Setup should not crash
        rain_delay_switch._setup(minimal_device)

        # Should handle missing data gracefully
        assert program_switch.is_on is False  # Default for missing 'enabled'
        assert rain_delay_switch.is_on is False  # No rain delay
        assert program_switch.available is True
        assert rain_delay_switch.available is True

        # Attributes should handle missing data
        prog_attrs = program_switch.extra_state_attributes
        assert prog_attrs["device_id"] == TEST_DEVICE_ID
        assert prog_attrs["is_smart_program"] is False  # Default
        assert prog_attrs["frequency"] is None  # Missing
        assert prog_attrs["budget"] is None  # Missing

    async def test_switches_handle_websocket_events_without_data(
        self,
        hass: HomeAssistant,
        mock_sprinkler_device: BHyveDevice,
        mock_timer_program: BHyveTimerProgram,
        mock_bhyve_client: MagicMock,
    ) -> None:
        """Test switches handle websocket events without required data."""
        program_switch = BHyveProgramSwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            program=mock_timer_program,
            icon="bulletin-board",
        )

        rain_delay_switch = BHyveRainDelaySwitch(
            hass=hass,
            bhyve=mock_bhyve_client,
            device=mock_sprinkler_device,
            icon="weather-pouring",
        )

        # Setup rain delay switch
        rain_delay_switch._setup(mock_sprinkler_device)

        # Test websocket events with missing data
        program_switch._on_ws_data({"event": EVENT_PROGRAM_CHANGED})  # No program data
        program_switch._on_ws_data({})  # No event field

        rain_delay_switch._on_ws_data({"event": EVENT_RAIN_DELAY})  # No delay data
        rain_delay_switch._on_ws_data({})  # No event field

        # Should not crash and maintain state
        assert program_switch.is_on is True  # Original state preserved
        assert rain_delay_switch.is_on is False  # Original state preserved
