"""Common fixtures for BHyve tests."""

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.bhyve import DOMAIN
from custom_components.bhyve.pybhyve.typings import BHyveDevice


@pytest.fixture
def mock_sprinkler_device() -> BHyveDevice:
    """Mock BHyve sprinkler device data."""
    return BHyveDevice(
        {
            "id": "test-device-123",
            "name": "Test Sprinkler",
            "type": "sprinkler_timer",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "hardware_version": "v2.0",
            "firmware_version": "1.2.3",
            "zones": [
                {
                    "id": 1,
                    "name": "Front Yard",
                    "enabled": True,
                    "manual_preset_runtime": 300,
                    "sprinkler_type": "spray",
                    "image_url": "https://example.com/front_yard.jpg",
                    "smart_watering_enabled": True,
                },
                {
                    "id": 2,
                    "name": "Back Yard",
                    "enabled": True,
                    "manual_preset_runtime": 600,
                    "sprinkler_type": "rotor",
                    "image_url": "https://example.com/back_yard.jpg",
                    "smart_watering_enabled": False,
                },
            ],
            "status": {
                "run_mode": "auto",
                "is_connected": True,
                "battery_percent": 85,
            },
        }
    )


@pytest.fixture
def mock_config_entry() -> dict[str, str]:
    """Mock config entry."""
    return {"username": "test@example.com", "password": "test_password"}


@pytest.fixture
def mock_hass_config_entry() -> ConfigEntry:
    """Mock Home Assistant config entry."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="BHyve Test",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "test_password",
        },
        source="user",
        entry_id="test_entry_id",
        unique_id="test_unique_id",
    )
