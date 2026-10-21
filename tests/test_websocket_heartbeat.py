"""
Test that a websocket connection that silently died is noticed and replaced.

These run the real OrbitWebsocket and aiohttp client against a real aiohttp
websocket server on localhost. A server that stops answering protocol pings
stands in for a connection that died without closing (for example after a
network or cloud outage): before the heartbeat, receive() waited on it forever
and live updates stopped until Home Assistant restarted.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from custom_components.bhyve.pybhyve import websocket as websocket_module
from custom_components.bhyve.pybhyve.websocket import OrbitWebsocket

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

HEARTBEAT = 0.5


class FakeOrbitEvents:
    """A websocket endpoint that records each connection's handshake."""

    def __init__(self, *, answer_pings: bool) -> None:
        """Initialize; with answer_pings False the server ignores pings."""
        self.answer_pings = answer_pings
        self.handshakes: list[dict[str, Any]] = []

    async def handle(self, request: web.Request) -> web.WebSocketResponse:
        """Accept a connection and read until it closes."""
        ws = web.WebSocketResponse(autoping=self.answer_pings)
        await ws.prepare(request)
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("event") == "app_connection":
                    self.handshakes.append(data)
        return ws


@pytest.fixture
async def connect(
    socket_enabled: None,  # noqa: ARG001
) -> AsyncIterator[Any]:
    """Return a function that runs OrbitWebsocket against a local server."""
    servers: list[TestServer] = []
    sessions: list[aiohttp.ClientSession] = []
    sockets: list[OrbitWebsocket] = []

    async def _connect(events: FakeOrbitEvents) -> OrbitWebsocket:
        app = web.Application()
        app.router.add_get("/v1/events", events.handle)
        server = TestServer(app)
        await server.start_server()
        servers.append(server)
        session = aiohttp.ClientSession()
        sessions.append(session)
        orbit = OrbitWebsocket(
            token="token",
            loop=asyncio.get_running_loop(),
            session=session,
            url=str(server.make_url("/v1/events")).replace("http", "ws", 1),
            async_callback=AsyncMock(),
        )
        sockets.append(orbit)
        orbit.start()
        return orbit

    with (
        patch.object(websocket_module, "WS_HEARTBEAT", HEARTBEAT),
        patch.object(websocket_module, "RECONNECT_DELAY", 0.05),
    ):
        yield _connect
        for orbit in sockets:
            await orbit.stop()
        # aiohttp may schedule one last heartbeat check while a connection is
        # closing; it finds the connection closed and stops. Let it run out.
        await asyncio.sleep(HEARTBEAT * 3)
        for session in sessions:
            await session.close()
        for server in servers:
            await server.close()


async def wait_for(condition: Any, within: float = 5.0) -> None:
    """Wait until condition() is true, or fail."""
    async with asyncio.timeout(within):
        while not condition():  # noqa: ASYNC110 - polling server-side state
            await asyncio.sleep(0.02)


async def test_silent_connection_is_replaced(connect: Any) -> None:
    """A connection whose pings go unanswered is closed and reconnected."""
    events = FakeOrbitEvents(answer_pings=False)

    await connect(events)
    await wait_for(lambda: len(events.handshakes) >= 2)

    # Each new connection authenticates again with the session token.
    assert events.handshakes[1] == {
        "event": "app_connection",
        "orbit_session_token": "token",
    }


async def test_healthy_connection_is_kept(connect: Any) -> None:
    """A connection that answers pings stays up across many heartbeats."""
    events = FakeOrbitEvents(answer_pings=True)

    orbit = await connect(events)
    await wait_for(lambda: len(events.handshakes) == 1)
    await asyncio.sleep(HEARTBEAT * 4)

    assert len(events.handshakes) == 1
    assert orbit.state == websocket_module.STATE_RUNNING
