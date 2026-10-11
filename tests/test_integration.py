"""
End-to-end tests against a fake Orbit cloud.

These boot the real integration in Home Assistant, with the real client,
websocket transport, coordinator and entities, and only the network replaced
by FakeOrbitCloud. They cover what the unit tests cannot: login through
setup and the config flow, session expiry and re-login, websocket events
reaching entities, and service calls failing with a readable error.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.bhyve.const import CONF_DEVICES, DOMAIN

from .fake_orbit import (
    PASSWORD,
    PROGRAM_ID,
    SPRINKLER_ID,
    SPRINKLER_MAC,
    USERNAME,
    FakeOrbitCloud,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

FRONT_YARD_VALVE = f"{SPRINKLER_MAC}:{SPRINKLER_ID}:1:valve"
RAIN_DELAY_SWITCH = f"{SPRINKLER_MAC}:{SPRINKLER_ID}:rain_delay"
PROGRAM_SWITCH = f"bhyve:program:{PROGRAM_ID}"


@pytest.fixture
def cloud() -> FakeOrbitCloud:
    """Return a fresh fake Orbit cloud."""
    return FakeOrbitCloud()


@pytest.fixture(autouse=True)
async def connect_to_cloud(
    hass: HomeAssistant,
    cloud: FakeOrbitCloud,
    enable_custom_integrations: None,  # noqa: ARG001
) -> AsyncIterator[None]:
    """Route the integration's HTTP session to the fake cloud."""
    with (
        patch("custom_components.bhyve.async_get_clientsession", return_value=cloud),
        patch(
            "custom_components.bhyve.config_flow.async_get_clientsession",
            return_value=cloud,
        ),
    ):
        yield
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_unload(entry.entry_id)
        await settle(hass)


async def settle(hass: HomeAssistant) -> None:
    """
    Let HA jobs and the websocket's own task process pending messages.

    Coordinator polls run as background tasks, which async_block_till_done
    only waits for when asked to.
    """
    for _ in range(3):
        await hass.async_block_till_done(wait_background_tasks=True)
        await asyncio.sleep(0)


async def advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta
) -> None:
    """Move the clock forward and run whatever timers came due."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await settle(hass)


async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a config entry for the sprinkler."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=USERNAME,
        data={CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD},
        options={CONF_DEVICES: [SPRINKLER_ID]},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    return entry


def entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    """Look up an entity id by unique id."""
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert found is not None, f"no {platform} entity with unique id {unique_id}"
    return found


def reauth_flows(hass: HomeAssistant) -> list[dict]:
    """Return the reauth flows in progress."""
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == "reauth"
    ]


# Login (#474)


@pytest.mark.parametrize("token_field", ["orbit_session_token", "orbit_api_key"])
async def test_setup_logs_in_with_either_token_field(
    hass: HomeAssistant, cloud: FakeOrbitCloud, token_field: str
) -> None:
    """Setup works with the renamed login field and the old one."""
    cloud.token_field = token_field

    entry = await setup_entry(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(entity_id(hass, "valve", FRONT_YARD_VALVE)).state == (
        "closed"
    )
    authed = [r for r in cloud.requests if r.path != "/v1/session"]
    assert authed
    assert {r.token for r in authed} == {"token-1"}
    assert cloud.socket.sent[0] == {
        "event": "app_connection",
        "orbit_session_token": "token-1",
    }


async def test_config_flow_creates_entry_with_renamed_token_field(
    hass: HomeAssistant, cloud: FakeOrbitCloud
) -> None:
    """Regression for #474: the config flow failed with cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICES: [SPRINKLER_ID]}
    )
    await settle(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD}
    assert cloud.logins >= 1


async def test_config_flow_rejects_wrong_password(
    hass: HomeAssistant, cloud: FakeOrbitCloud
) -> None:
    """Wrong credentials are reported as invalid_auth, not cannot_connect."""
    cloud.password = "something-else"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


# Session expiry


async def test_expired_session_logs_in_again_without_reauth(
    hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
) -> None:
    """An expired session is renewed silently and the poll still lands."""
    entry = await setup_entry(hass)
    rain_delay = entity_id(hass, "switch", RAIN_DELAY_SWITCH)
    assert hass.states.get(rain_delay).state == "off"

    cloud.expire_sessions()
    cloud.device(SPRINKLER_ID)["status"]["rain_delay"] = 24
    await advance(hass, freezer, timedelta(minutes=6))

    assert cloud.logins == 2
    assert entry.state is ConfigEntryState.LOADED
    assert reauth_flows(hass) == []
    assert hass.states.get(rain_delay).state == "on"


async def test_changed_password_still_starts_reauth(
    hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
) -> None:
    """When the stored password stops working, the user is asked again."""
    await setup_entry(hass)

    cloud.expire_sessions()
    cloud.password = "changed-in-the-app"
    await advance(hass, freezer, timedelta(minutes=6))

    assert len(reauth_flows(hass)) == 1


async def test_websocket_reconnects_with_renewed_token(
    hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
) -> None:
    """After a re-login, the next websocket connection uses the new token."""
    await setup_entry(hass)
    cloud.expire_sessions()
    await advance(hass, freezer, timedelta(minutes=6))
    assert cloud.logins == 2

    cloud.socket.drop()
    await settle(hass)
    await advance(hass, freezer, timedelta(seconds=6))

    assert len(cloud.sockets) == 2
    assert cloud.socket.sent[0] == {
        "event": "app_connection",
        "orbit_session_token": "token-2",
    }


# Websocket events and polling


async def test_websocket_event_updates_valve(
    hass: HomeAssistant, cloud: FakeOrbitCloud
) -> None:
    """A watering event pushed by the cloud opens the valve entity."""
    await setup_entry(hass)
    valve = entity_id(hass, "valve", FRONT_YARD_VALVE)

    cloud.socket.push(
        {
            "event": "watering_in_progress_notification",
            "device_id": SPRINKLER_ID,
            "current_station": 1,
            "program": "manual",
            "run_time": 5,
            "started_watering_station_at": "2026-10-11T06:00:00.000Z",
        }
    )
    await settle(hass)
    assert hass.states.get(valve).state == "open"

    cloud.socket.push({"event": "watering_complete", "device_id": SPRINKLER_ID})
    await settle(hass)
    assert hass.states.get(valve).state == "closed"


async def test_frequent_events_do_not_stop_polling(
    hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
) -> None:
    """Events every minute must not keep pushing the 5-minute poll back."""
    await setup_entry(hass)
    polls_at_setup = cloud.count("get", "/v1/devices")

    for _ in range(7):
        cloud.socket.push(
            {"event": "battery_status", "device_id": SPRINKLER_ID, "battery": {}}
        )
        await settle(hass)
        await advance(hass, freezer, timedelta(minutes=1))

    assert cloud.count("get", "/v1/devices") > polls_at_setup


# Commands


async def test_open_valve_sends_command(
    hass: HomeAssistant, cloud: FakeOrbitCloud
) -> None:
    """Opening a valve sends a manual watering command for its station."""
    await setup_entry(hass)
    valve = entity_id(hass, "valve", FRONT_YARD_VALVE)

    await hass.services.async_call(
        "valve", "open_valve", {"entity_id": valve}, blocking=True
    )

    [command] = cloud.socket.commands()
    assert command["event"] == "change_mode"
    assert command["mode"] == "manual"
    assert command["device_id"] == SPRINKLER_ID
    assert command["stations"] == [{"station": 1, "run_time": 5}]
    assert hass.states.get(valve).state == "open"


async def test_program_switch_updates_program_over_rest(
    hass: HomeAssistant, cloud: FakeOrbitCloud
) -> None:
    """Turning a program off PUTs it with the current session token."""
    await setup_entry(hass)
    program = entity_id(hass, "switch", PROGRAM_SWITCH)

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": program}, blocking=True
    )

    [put] = [r for r in cloud.requests if r.method == "put"]
    assert put.path == f"/v1/sprinkler_timer_programs/{PROGRAM_ID}"
    assert put.token == "token-1"
    assert put.body["sprinkler_timer_program"]["enabled"] is False


async def test_command_while_disconnected_shows_reason(
    hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
) -> None:
    """A command that cannot be sent fails visibly and recovers on reconnect."""
    await setup_entry(hass)
    valve = entity_id(hass, "valve", FRONT_YARD_VALVE)
    rain_delay = entity_id(hass, "switch", RAIN_DELAY_SWITCH)

    cloud.websocket_down = True
    cloud.socket.drop()
    await settle(hass)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "valve", "open_valve", {"entity_id": valve}, blocking=True
        )
    assert str(err.value).startswith("Could not send the command to Garden Timer")
    assert hass.states.get(valve).state == "closed"

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": rain_delay}, blocking=True
        )

    cloud.websocket_down = False
    await advance(hass, freezer, timedelta(minutes=1))
    assert not cloud.socket.closed

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": rain_delay}, blocking=True
    )
    assert cloud.socket.commands() == [
        {"event": "rain_delay", "device_id": SPRINKLER_ID, "delay": 24}
    ]


# Lifecycle


async def test_failed_setup_opens_no_websocket(
    hass: HomeAssistant, cloud: FakeOrbitCloud
) -> None:
    """A setup that will be retried leaves no websocket behind."""
    cloud.failures = {"/v1/devices": 500}

    entry = await setup_entry(hass)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert cloud.sockets == []


async def test_unload_closes_websocket_for_good(
    hass: HomeAssistant, cloud: FakeOrbitCloud, freezer: FrozenDateTimeFactory
) -> None:
    """Unloading closes the websocket and does not reconnect it."""
    entry = await setup_entry(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await settle(hass)
    await advance(hass, freezer, timedelta(minutes=10))

    assert cloud.socket.closed
    assert len(cloud.sockets) == 1
