"""Test registry migration from v3 zone switches to v4 valves."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.bhyve import _migrate_zone_switch_to_valve
from custom_components.bhyve.const import DOMAIN


@pytest.mark.asyncio
async def test_removes_orphaned_zone_switch(hass: HomeAssistant) -> None:
    """v3 zone switch with `:switch` unique_id suffix gets dropped."""
    config_entry = MockConfigEntry(domain=DOMAIN, title="Test", entry_id="test_entry")
    config_entry.add_to_hass(hass)

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        domain="switch",
        platform=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff:device123:1:switch",
        suggested_object_id="zone_1_zone",
        config_entry=config_entry,
    )

    _migrate_zone_switch_to_valve(hass, config_entry)

    assert ent_reg.async_get("switch.zone_1_zone") is None


@pytest.mark.asyncio
async def test_preserves_existing_valve_when_switch_removed(
    hass: HomeAssistant,
) -> None:
    """The v4 valve entity is left alone when the stale v3 switch is deleted."""
    config_entry = MockConfigEntry(domain=DOMAIN, title="Test", entry_id="test_entry")
    config_entry.add_to_hass(hass)

    ent_reg = er.async_get(hass)
    valve = ent_reg.async_get_or_create(
        domain="valve",
        platform=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff:device123:1:valve",
        suggested_object_id="pond_zone_1_zone",
        config_entry=config_entry,
    )
    ent_reg.async_get_or_create(
        domain="switch",
        platform=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff:device123:1:switch",
        suggested_object_id="zone_1_zone",
        config_entry=config_entry,
    )

    _migrate_zone_switch_to_valve(hass, config_entry)

    assert ent_reg.async_get("switch.zone_1_zone") is None
    assert ent_reg.async_get(valve.entity_id) is not None


@pytest.mark.asyncio
async def test_leaves_non_zone_switches_untouched(hass: HomeAssistant) -> None:
    """Rain-delay, smart-watering, and program switches are left in place."""
    config_entry = MockConfigEntry(domain=DOMAIN, title="Test", entry_id="test_entry")
    config_entry.add_to_hass(hass)

    ent_reg = er.async_get(hass)
    # Rain delay uses `:rain_delay`, smart watering uses `:smart_watering`,
    # program switches use `bhyve:program:...` - none end in `:switch`.
    keep_entities = [
        ent_reg.async_get_or_create(
            domain="switch",
            platform=DOMAIN,
            unique_id="aa:bb:cc:dd:ee:ff:device123:rain_delay",
            suggested_object_id="pond_rain_delay",
            config_entry=config_entry,
        ),
        ent_reg.async_get_or_create(
            domain="switch",
            platform=DOMAIN,
            unique_id="aa:bb:cc:dd:ee:ff:device123:1:smart_watering",
            suggested_object_id="pond_smart_watering",
            config_entry=config_entry,
        ),
        ent_reg.async_get_or_create(
            domain="switch",
            platform=DOMAIN,
            unique_id="bhyve:program:program-abc",
            suggested_object_id="watering_program",
            config_entry=config_entry,
        ),
    ]

    _migrate_zone_switch_to_valve(hass, config_entry)

    for entity in keep_entities:
        assert ent_reg.async_get(entity.entity_id) is not None


@pytest.mark.asyncio
async def test_is_idempotent(hass: HomeAssistant) -> None:
    """Running the migration twice is safe."""
    config_entry = MockConfigEntry(domain=DOMAIN, title="Test", entry_id="test_entry")
    config_entry.add_to_hass(hass)

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        domain="switch",
        platform=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff:device123:1:switch",
        suggested_object_id="zone_1_zone",
        config_entry=config_entry,
    )

    _migrate_zone_switch_to_valve(hass, config_entry)
    _migrate_zone_switch_to_valve(hass, config_entry)

    assert ent_reg.async_get("switch.zone_1_zone") is None


@pytest.mark.asyncio
async def test_only_touches_entities_for_this_config_entry(
    hass: HomeAssistant,
) -> None:
    """Stale switches registered against a different config entry aren't touched."""
    config_entry = MockConfigEntry(domain=DOMAIN, title="Test", entry_id="test_entry")
    config_entry.add_to_hass(hass)

    other_entry = MockConfigEntry(domain=DOMAIN, title="Other", entry_id="other_entry")
    other_entry.add_to_hass(hass)

    ent_reg = er.async_get(hass)
    other = ent_reg.async_get_or_create(
        domain="switch",
        platform=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff:other:1:switch",
        suggested_object_id="other_zone",
        config_entry=other_entry,
    )

    _migrate_zone_switch_to_valve(hass, config_entry)

    assert ent_reg.async_get(other.entity_id) is not None
