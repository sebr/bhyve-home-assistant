"""Test device removal when filtered from config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.bhyve import remove_devices_from_registry
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
