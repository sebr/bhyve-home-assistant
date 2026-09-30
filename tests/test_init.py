"""Test integration setup."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bhyve.const import CONF_DEVICES, DOMAIN

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

BRIDGE = {
    "id": "bridge-1",
    "name": "Wi-Fi Hub",
    "type": "bridge",
    "mac_address": "446755dc6001",
    "is_connected": True,
    "device_gateway_topic": "devices-1",
}
FLOOD = {
    "id": "flood-1",
    "name": "Basement Flood",
    "type": "flood_sensor",
    "is_connected": True,
    "device_gateway_topic": "devices-1",
    "status": {},
}


class FakeClient:
    """Stand-in for BHyveClient that serves canned devices."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Accept and ignore the real client's arguments."""

    async def login(self) -> bool:
        """Report a successful login."""
        return True

    def listen(self, loop: AbstractEventLoop, async_callback: Callable) -> None:
        """Do not open a websocket."""

    async def stop(self, *args: Any, **kwargs: Any) -> None:
        """Nothing to stop."""

    @property
    async def devices(self) -> list[dict[str, Any]]:
        """Return a bridge and a flood sensor behind it."""
        return [dict(BRIDGE), dict(FLOOD)]

    @property
    async def timer_programs(self) -> list[dict[str, Any]]:
        """Return no programs."""
        return []


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_links_child_devices_to_bridge(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Child devices link to the bridge's registry entry by id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        options={CONF_DEVICES: ["flood-1"]},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.bhyve.BHyveClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    by_identifier = {
        identifier: device
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        for identifier in device.identifiers
    }
    bridge = by_identifier[(DOMAIN, "bridge-1")]
    flood = by_identifier[(DOMAIN, "flood-1")]
    assert bridge.via_device_id is None
    assert flood.via_device_id == bridge.id
    assert "deprecated `via_device`" not in caplog.text
