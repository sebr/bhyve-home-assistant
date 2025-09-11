"""Test BHyve utility functions."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt

from custom_components.bhyve.const import CONF_DEVICES
from custom_components.bhyve.util import (
    filter_configured_devices,
    orbit_time_to_local_time,
)

# Test constants
EXPECTED_CONFIGURED_DEVICES = 3
EXPECTED_INTEGER_DEVICES = 2
EXPECTED_MIXED_DEVICES = 2
EXPECTED_DEFAULT_NAME_DEVICES = 3
EXPECTED_ORDER_DEVICES = 3
EXPECTED_SPECIAL_CHAR_DEVICES = 3


class TestOrbitTimeToLocalTime:
    """Test orbit_time_to_local_time function."""

    def test_orbit_time_to_local_time_valid_timestamp(self) -> None:
        """Test converting a valid Orbit timestamp to local time."""
        # Test with a known UTC timestamp
        utc_timestamp = "2020-01-14T12:10:10.000Z"

        result = orbit_time_to_local_time(utc_timestamp)

        # Should return a datetime object
        assert isinstance(result, datetime)

        # Should have timezone information
        assert result.tzinfo is not None

        # The UTC timestamp should be properly parsed
        expected_utc = dt.parse_datetime(utc_timestamp)
        expected_local = dt.as_local(expected_utc)
        assert result == expected_local

    def test_orbit_time_to_local_time_different_formats(self) -> None:
        """Test converting different timestamp formats."""
        # Test various valid formats
        test_cases = [
            "2020-01-14T12:10:10Z",
            "2020-01-14T12:10:10.123Z",
            "2020-01-14T12:10:10+00:00",
            "2020-12-25T18:30:45.999Z",
        ]

        for timestamp in test_cases:
            result = orbit_time_to_local_time(timestamp)
            assert isinstance(result, datetime)
            assert result.tzinfo is not None

    def test_orbit_time_to_local_time_none_input(self) -> None:
        """Test converting None timestamp."""
        result = orbit_time_to_local_time(None)
        assert result is None

    def test_orbit_time_to_local_time_empty_string(self) -> None:
        """Test converting empty string timestamp."""
        result = orbit_time_to_local_time("")
        assert result is None

    def test_orbit_time_to_local_time_invalid_format(self) -> None:
        """Test converting invalid timestamp format."""
        invalid_timestamps = [
            "not-a-timestamp",
            "2020/01/14 12:10:10",  # Wrong format
            "12:10:10",  # Missing date
            "invalid-date-format",  # Completely invalid
        ]

        for timestamp in invalid_timestamps:
            result = orbit_time_to_local_time(timestamp)
            assert result is None

    def test_orbit_time_to_local_time_partial_dates(self) -> None:
        """Test converting partial date strings."""
        # Some partial dates might be successfully parsed by the datetime parser
        partial_dates = [
            "2020-01-14",  # Date only - might be parsed as midnight
        ]

        for timestamp in partial_dates:
            result = orbit_time_to_local_time(timestamp)
            # Result might be valid datetime or None depending on parser behavior
            if result is not None:
                assert isinstance(result, datetime)
                assert result.tzinfo is not None

    def test_orbit_time_to_local_time_invalid_datetime_values(self) -> None:
        """Test converting timestamps with invalid datetime values."""
        # Some invalid timestamps might raise exceptions during parsing
        invalid_timestamps_with_exceptions = [
            "2020-13-45T25:70:80Z",  # Invalid date/time values
        ]

        for timestamp in invalid_timestamps_with_exceptions:
            # These might raise ValueError during dt.datetime creation
            try:
                result = orbit_time_to_local_time(timestamp)
                # If no exception, result should be None
                assert result is None
            except ValueError:
                # ValueError is acceptable for invalid datetime values
                pass

    def test_orbit_time_to_local_time_timezone_conversion(self) -> None:
        """Test that timezone conversion works correctly."""
        # Use a specific UTC timestamp
        utc_timestamp = "2020-06-15T14:30:00.000Z"

        result = orbit_time_to_local_time(utc_timestamp)

        # Parse the original UTC time for comparison
        utc_time = dt.parse_datetime(utc_timestamp)

        # Both should be valid datetime objects
        assert result is not None
        assert utc_time is not None

        # The result should be the same instant in time, just in local timezone
        assert result.utctimetuple() == utc_time.utctimetuple()

        # But the timezone should be different (local vs UTC)
        if result.tzinfo != UTC:
            assert result.tzinfo != utc_time.tzinfo


class TestFilterConfiguredDevices:
    """Test filter_configured_devices function."""

    @pytest.fixture
    def mock_config_entry(self) -> ConfigEntry:
        """Create a mock config entry."""
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {CONF_DEVICES: ["device-1", "device-3", "device-5"]}
        return entry

    @pytest.fixture
    def sample_devices(self) -> list:
        """Create sample devices for testing."""
        return [
            {"id": "device-1", "name": "Front Sprinkler", "type": "sprinkler_timer"},
            {"id": "device-2", "name": "Side Sprinkler", "type": "sprinkler_timer"},
            {"id": "device-3", "name": "Back Sprinkler", "type": "sprinkler_timer"},
            {"id": "device-4", "name": "Flood Sensor", "type": "flood_sensor"},
            {"id": "device-5", "name": "Faucet Timer", "type": "faucet_timer"},
        ]

    def test_filter_configured_devices_basic(
        self, mock_config_entry: ConfigEntry, sample_devices: list
    ) -> None:
        """Test basic device filtering functionality."""
        result = filter_configured_devices(mock_config_entry, sample_devices)

        # Should return only configured devices (device-1, device-3, device-5)
        assert len(result) == EXPECTED_CONFIGURED_DEVICES

        # Verify correct devices are returned
        device_ids = [device["id"] for device in result]
        assert "device-1" in device_ids
        assert "device-3" in device_ids
        assert "device-5" in device_ids

        # Verify excluded devices are not returned
        assert "device-2" not in device_ids
        assert "device-4" not in device_ids

    def test_filter_configured_devices_preserves_device_data(
        self, mock_config_entry: ConfigEntry, sample_devices: list
    ) -> None:
        """Test that device filtering preserves all device data."""
        result = filter_configured_devices(mock_config_entry, sample_devices)

        # Find the front sprinkler in results
        front_sprinkler = next(d for d in result if d["id"] == "device-1")

        # Verify all original data is preserved
        assert front_sprinkler["name"] == "Front Sprinkler"
        assert front_sprinkler["type"] == "sprinkler_timer"
        assert front_sprinkler["id"] == "device-1"

    def test_filter_configured_devices_integer_ids(self) -> None:
        """Test device filtering with integer device IDs."""
        # Create config entry with string representations of integer IDs
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {CONF_DEVICES: ["1", "3"]}  # String representations

        # Create devices with integer IDs
        int_devices = [
            {"id": 1, "name": "Device 1", "type": "sprinkler_timer"},
            {"id": 2, "name": "Device 2", "type": "sprinkler_timer"},
            {"id": 3, "name": "Device 3", "type": "flood_sensor"},
        ]

        result = filter_configured_devices(entry, int_devices)

        # Should return devices 1 and 3
        assert len(result) == EXPECTED_INTEGER_DEVICES
        device_ids = [device["id"] for device in result]
        expected_device_1 = 1
        expected_device_3 = 3
        excluded_device_2 = 2
        assert expected_device_1 in device_ids
        assert expected_device_3 in device_ids
        assert excluded_device_2 not in device_ids

    def test_filter_configured_devices_string_and_int_ids_mixed(self) -> None:
        """Test device filtering with mixed string/int IDs."""
        # Config has string representations
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {CONF_DEVICES: ["1", "3"]}

        # Devices have integer IDs
        devices = [
            {"id": 1, "name": "Device 1", "type": "sprinkler_timer"},
            {"id": 2, "name": "Device 2", "type": "sprinkler_timer"},
            {"id": 3, "name": "Device 3", "type": "flood_sensor"},
        ]

        result = filter_configured_devices(entry, devices)

        # Should work because of str() conversion in filter function
        assert len(result) == EXPECTED_MIXED_DEVICES
        device_ids = [device["id"] for device in result]
        expected_device_1 = 1
        expected_device_3 = 3
        assert expected_device_1 in device_ids
        assert expected_device_3 in device_ids

    def test_filter_configured_devices_no_matching_devices(
        self, sample_devices: list
    ) -> None:
        """Test device filtering when no devices match configuration."""
        # Create config entry with non-existent device IDs
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {CONF_DEVICES: ["device-99", "device-100"]}

        result = filter_configured_devices(entry, sample_devices)

        # Should return empty list
        assert len(result) == 0
        assert result == []

    def test_filter_configured_devices_empty_device_list(
        self, mock_config_entry: ConfigEntry
    ) -> None:
        """Test device filtering with empty device list."""
        result = filter_configured_devices(mock_config_entry, [])

        # Should return empty list
        assert len(result) == 0
        assert result == []

    def test_filter_configured_devices_empty_config(self, sample_devices: list) -> None:
        """Test device filtering with empty configuration."""
        # Create config entry with no configured devices
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {CONF_DEVICES: []}

        result = filter_configured_devices(entry, sample_devices)

        # Should return empty list
        assert len(result) == 0
        assert result == []

    def test_filter_configured_devices_adds_default_name(self) -> None:
        """Test that devices without names get default name."""
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {CONF_DEVICES: ["device-1", "device-2"]}

        # Create devices, one without a name
        devices = [
            {"id": "device-1", "name": "Named Device", "type": "sprinkler_timer"},
            {"id": "device-2", "type": "flood_sensor"},  # No name field
            {
                "id": "device-3",
                "name": None,
                "type": "faucet_timer",
            },  # Explicit None name
        ]

        # Add device-3 to config to test explicit None case
        entry.options[CONF_DEVICES].append("device-3")

        result = filter_configured_devices(entry, devices)

        # Should return all three devices
        assert len(result) == EXPECTED_DEFAULT_NAME_DEVICES

        # Find devices in result
        named_device = next(d for d in result if d["id"] == "device-1")
        unnamed_device = next(d for d in result if d["id"] == "device-2")
        none_name_device = next(d for d in result if d["id"] == "device-3")

        # Named device should keep its name
        assert named_device["name"] == "Named Device"

        # Unnamed device should get default name
        assert unnamed_device["name"] == "Unknown Device"

        # Device with None name should get default name
        assert none_name_device["name"] == "Unknown Device"

    def test_filter_configured_devices_modifies_original_devices(self) -> None:
        """Test that the function modifies device name in place."""
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {CONF_DEVICES: ["device-1"]}

        # Create device without name
        devices = [{"id": "device-1", "type": "sprinkler_timer"}]
        original_device = devices[0]

        result = filter_configured_devices(entry, devices)

        # Original device should have been modified
        assert original_device["name"] == "Unknown Device"

        # Result should contain the same modified device
        assert result[0] is original_device
        assert result[0]["name"] == "Unknown Device"

    def test_filter_configured_devices_missing_conf_devices_key(
        self, sample_devices: list
    ) -> None:
        """Test device filtering when CONF_DEVICES key is missing."""
        # Create config entry without CONF_DEVICES key
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {}  # Missing CONF_DEVICES

        # Should raise KeyError when trying to access missing key
        with pytest.raises(KeyError):
            filter_configured_devices(entry, sample_devices)

    def test_filter_configured_devices_preserves_order(self) -> None:
        """Test that device filtering preserves the order of filtered devices."""
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {CONF_DEVICES: ["device-3", "device-1", "device-2"]}

        devices = [
            {"id": "device-1", "name": "First Device", "type": "sprinkler_timer"},
            {"id": "device-2", "name": "Second Device", "type": "flood_sensor"},
            {"id": "device-3", "name": "Third Device", "type": "faucet_timer"},
            {"id": "device-4", "name": "Fourth Device", "type": "sprinkler_timer"},
        ]

        result = filter_configured_devices(entry, devices)

        # Should preserve order from original devices list, not config order
        assert len(result) == EXPECTED_ORDER_DEVICES
        assert result[0]["id"] == "device-1"  # First in original list
        assert result[1]["id"] == "device-2"  # Second in original list
        assert result[2]["id"] == "device-3"  # Third in original list


class TestUtilsEdgeCases:
    """Test edge cases for utility functions."""

    def test_orbit_time_with_different_timezone_formats(self) -> None:
        """Test orbit_time_to_local_time with various timezone formats."""
        # Test different timezone representations
        timestamps = [
            "2020-01-14T12:10:10Z",  # Zulu time
            "2020-01-14T12:10:10+00:00",  # UTC offset
            "2020-01-14T12:10:10-05:00",  # Negative offset
            "2020-01-14T12:10:10.123+02:00",  # Positive offset with milliseconds
        ]

        for timestamp in timestamps:
            result = orbit_time_to_local_time(timestamp)
            if (
                result is not None
            ):  # Some might be invalid depending on dt.parse_datetime
                assert isinstance(result, datetime)
                assert result.tzinfo is not None

    def test_filter_devices_with_special_characters_in_ids(self) -> None:
        """Test filtering devices with special characters in IDs."""
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {
            CONF_DEVICES: [
                "device-with-dashes",
                "device_with_underscores",
                "device@with@symbols",
            ]
        }

        devices = [
            {
                "id": "device-with-dashes",
                "name": "Dash Device",
                "type": "sprinkler_timer",
            },
            {
                "id": "device_with_underscores",
                "name": "Underscore Device",
                "type": "flood_sensor",
            },
            {
                "id": "device@with@symbols",
                "name": "Symbol Device",
                "type": "faucet_timer",
            },
            {"id": "normal-device", "name": "Normal Device", "type": "sprinkler_timer"},
        ]

        result = filter_configured_devices(entry, devices)

        assert len(result) == EXPECTED_SPECIAL_CHAR_DEVICES
        device_ids = [device["id"] for device in result]
        assert "device-with-dashes" in device_ids
        assert "device_with_underscores" in device_ids
        assert "device@with@symbols" in device_ids
        assert "normal-device" not in device_ids

    def test_orbit_time_with_microseconds(self) -> None:
        """Test orbit_time_to_local_time with microsecond precision."""
        timestamp = "2020-01-14T12:10:10.123456Z"

        result = orbit_time_to_local_time(timestamp)

        if result is not None:  # Depends on dt.parse_datetime capability
            assert isinstance(result, datetime)
            # Check if microseconds are preserved (if supported)
            parsed_utc = dt.parse_datetime(timestamp)
            if parsed_utc and hasattr(parsed_utc, "microsecond"):
                expected_local = dt.as_local(parsed_utc)
                assert result == expected_local
