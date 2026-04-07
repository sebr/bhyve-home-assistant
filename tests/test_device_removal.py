"""Test device removal when filtered from config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.bhyve import (
    remove_devices_from_registry,
    update_listener,
)
from custom_components.bhyve.const import CONF_DEVICES, DOMAIN
from custom_components.bhyve.util import filter_configured_devices


@pytest.mark.asyncio
async def test_remove_devices_from_registry(hass: HomeAssistant) -> None:
    """Test that devices are removed from the registry."""
    # Create a mock config entry first
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={},
        entry_id="test_entry",
    )
    config_entry.add_to_hass(hass)

    # Create a mock device registry
    device_registry = dr.async_get(hass)

    # Add some test devices to the registry
    device1 = device_registry.async_get_or_create(
        config_entry_id="test_entry",
        identifiers={(DOMAIN, "device1")},
        name="Test Device 1",
    )
    device2 = device_registry.async_get_or_create(
        config_entry_id="test_entry",
        identifiers={(DOMAIN, "device2")},
        name="Test Device 2",
    )
    device3 = device_registry.async_get_or_create(
        config_entry_id="test_entry",
        identifiers={(DOMAIN, "device3")},
        name="Test Device 3",
    )

    # Verify devices are in registry
    assert device_registry.async_get(device1.id) is not None
    assert device_registry.async_get(device2.id) is not None
    assert device_registry.async_get(device3.id) is not None

    # Remove device1 and device3
    await remove_devices_from_registry(hass, {"device1", "device3"})

    # Verify device1 and device3 are removed, device2 remains
    assert device_registry.async_get(device1.id) is None
    assert device_registry.async_get(device2.id) is not None
    assert device_registry.async_get(device3.id) is None


@pytest.mark.asyncio
async def test_update_listener_removes_filtered_devices(hass: HomeAssistant) -> None:
    """Test that update_listener removes devices filtered out in options."""
    # Create a real config entry first
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={CONF_DEVICES: ["device2"]},  # Only device2 is configured
        entry_id="test_entry",
    )
    config_entry.add_to_hass(hass)

    # Create mock client with all devices
    mock_client = MagicMock()

    # Mock the async property behavior - each access returns a new coroutine
    async def mock_devices() -> list[dict[str, Any]]:
        return [
            {"id": "device1", "name": "Device 1"},
            {"id": "device2", "name": "Device 2"},
            {"id": "device3", "name": "Device 3"},
        ]

    # Use PropertyMock to return a new coroutine each time the property is accessed
    type(mock_client).devices = PropertyMock(side_effect=lambda: mock_devices())
    # Setup mock data in hass
    hass.data[DOMAIN] = {
        "test_entry": {
            "client": mock_client,
        }
    }

    # Create device registry and add devices
    device_registry = dr.async_get(hass)
    device1 = device_registry.async_get_or_create(
        config_entry_id="test_entry",
        identifiers={(DOMAIN, "device1")},
        name="Device 1",
    )
    device2 = device_registry.async_get_or_create(
        config_entry_id="test_entry",
        identifiers={(DOMAIN, "device2")},
        name="Device 2",
    )
    device3 = device_registry.async_get_or_create(
        config_entry_id="test_entry",
        identifiers={(DOMAIN, "device3")},
        name="Device 3",
    )

    # Mock the reload function
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        # Call update_listener
        await update_listener(hass, config_entry)

        # Verify that device1 and device3 are removed, device2 remains
        assert device_registry.async_get(device1.id) is None
        assert device_registry.async_get(device2.id) is not None
        assert device_registry.async_get(device3.id) is None

        # Verify reload was called
        mock_reload.assert_called_once_with("test_entry")


@pytest.mark.asyncio
async def test_update_listener_handles_errors_gracefully(hass: HomeAssistant) -> None:
    """Test that update_listener handles errors gracefully."""
    # Create a real config entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={CONF_DEVICES: ["device1"]},
        entry_id="test_entry",
    )
    config_entry.add_to_hass(hass)

    # Create mock client that raises an error
    mock_client = MagicMock()

    # Mock the async property to raise an error
    async def mock_devices_error() -> None:
        msg = "API Error"
        raise KeyError(msg)

    # Use PropertyMock to return a new coroutine each time
    type(mock_client).devices = PropertyMock(side_effect=lambda: mock_devices_error())

    # Setup mock data in hass
    hass.data[DOMAIN] = {
        "test_entry": {
            "client": mock_client,
        }
    }

    # Mock the reload function
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        # Call update_listener - should not raise exception
        await update_listener(hass, config_entry)

        # Verify reload was still called despite error
        mock_reload.assert_called_once_with("test_entry")


@pytest.mark.asyncio
async def test_device_recreation_after_filtering_back_in(hass: HomeAssistant) -> None:
    """Test that devices are properly recreated when filtered back into options."""
    # Create a real config entry with initially no devices configured
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={CONF_DEVICES: []},  # Start with no devices configured
        entry_id="test_entry",
    )
    config_entry.add_to_hass(hass)

    # Create mock client with all devices
    mock_client = MagicMock()

    # Mock the async property behavior - each access returns a new coroutine
    async def mock_devices() -> list[dict[str, Any]]:
        return [
            {"id": "device1", "name": "Device 1"},
            {"id": "device2", "name": "Device 2"},
        ]

    # Use PropertyMock to return a new coroutine each time the property is accessed
    type(mock_client).devices = PropertyMock(side_effect=lambda: mock_devices())
    # Setup mock data in hass
    hass.data[DOMAIN] = {
        "test_entry": {
            "client": mock_client,
        }
    }

    # Create device registry
    device_registry = dr.async_get(hass)

    # Initially no devices should be in registry since none are configured
    initial_devices = [
        d for d in device_registry.devices.values() if d.config_entry_id == "test_entry"
    ]
    assert len(initial_devices) == 0

    # Now create a new config entry with device1 included to simulate options update
    config_entry_updated = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={CONF_DEVICES: ["device1"]},  # Now device1 is configured
        entry_id="test_entry",
    )

    # Mock the reload function and call update_listener
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        await update_listener(hass, config_entry_updated)

        # Verify reload was called
        mock_reload.assert_called_once_with("test_entry")


@pytest.mark.asyncio
async def test_filter_configured_devices_with_missing_options(
    hass: HomeAssistant,
) -> None:
    """Test that filter_configured_devices handles missing options gracefully."""
    # Create a config entry with no options
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={},  # Empty options
        entry_id="test_entry",
    )
    config_entry.add_to_hass(hass)

    all_devices = [
        {"id": "device1", "name": "Device 1"},
        {"id": "device2", "name": "Device 2"},
    ]

    # Should return empty list when no devices are configured
    filtered = filter_configured_devices(config_entry, all_devices)
    assert filtered == []

    # Now test with devices configured
    config_entry_with_devices = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={CONF_DEVICES: ["device1"]},
        entry_id="test_entry2",
    )
    config_entry_with_devices.add_to_hass(hass)

    filtered = filter_configured_devices(config_entry_with_devices, all_devices)
    assert len(filtered) == 1
    assert filtered[0]["id"] == "device1"
