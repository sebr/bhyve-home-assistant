"""Test Orbit BHyve websocket transport."""

import json
from collections.abc import Callable, Coroutine
from types import TracebackType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp import WSMsgType

from custom_components.bhyve.pybhyve.websocket import (
    MAX_RECONNECT_DELAY,
    RECONNECT_DELAY,
    STATE_STOPPED,
    OrbitWebsocket,
)


class FakeTimerHandle:
    """Fake asyncio timer handle."""

    def __init__(self, delay: float, callback: Callable[[], None]) -> None:
        """Initialize the fake timer handle."""
        self.delay = delay
        self.callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        """Cancel the fake timer handle."""
        self.cancelled = True


class FakeLoop:
    """Fake event loop for websocket scheduling tests."""

    def __init__(self) -> None:
        """Initialize the fake loop."""
        self.call_later_handles: list[FakeTimerHandle] = []
        self.call_at_handles: list[FakeTimerHandle] = []
        self.created_tasks: list[Coroutine[Any, Any, Any]] = []

    def time(self) -> float:
        """Return the fake loop time."""
        return 0

    def call_at(self, when: float, callback: Callable[[], None]) -> FakeTimerHandle:
        """Record a scheduled call_at callback."""
        handle = FakeTimerHandle(when, callback)
        self.call_at_handles.append(handle)
        return handle

    def call_later(self, delay: float, callback: Callable[[], None]) -> FakeTimerHandle:
        """Record a scheduled call_later callback."""
        handle = FakeTimerHandle(delay, callback)
        self.call_later_handles.append(handle)
        return handle

    def create_task(self, coro: Coroutine[Any, Any, Any]) -> MagicMock:
        """Record and close a created coroutine task."""
        self.created_tasks.append(coro)
        coro.close()
        return MagicMock()


class FakeMessage:
    """Fake websocket message."""

    type = WSMsgType.CLOSE


class FakeWebSocket:
    """Fake aiohttp websocket response."""

    def __init__(self) -> None:
        """Initialize the fake websocket response."""
        self.closed = False
        self.sent: list[str] = []

    async def send_str(self, data: str) -> None:
        """Record sent websocket data."""
        self.sent.append(data)

    async def receive(self) -> FakeMessage:
        """Return a close message to end the receive loop."""
        return FakeMessage()

    async def pong(self) -> None:
        """Handle websocket pong calls."""

    async def close(self) -> None:
        """Close the fake websocket."""
        self.closed = True

    def exception(self) -> None:
        """Return no websocket exception."""


class FakeWebsocketContext:
    """Fake websocket async context manager."""

    def __init__(self, websocket: FakeWebSocket) -> None:
        """Initialize the fake websocket context."""
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        """Enter the fake websocket context."""
        return self.websocket

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the fake websocket context."""
        self.websocket.closed = True


class FakeSession:
    """Fake aiohttp client session."""

    def __init__(self) -> None:
        """Initialize the fake session."""
        self.websocket = FakeWebSocket()

    def ws_connect(self, _url: str) -> FakeWebsocketContext:
        """Return a fake websocket context."""
        return FakeWebsocketContext(self.websocket)


def create_websocket(
    loop: FakeLoop | None = None,
    session: FakeSession | None = None,
) -> OrbitWebsocket:
    """Create an Orbit websocket with test doubles."""
    return OrbitWebsocket(
        token="token",
        loop=loop or FakeLoop(),
        session=session or FakeSession(),
        url="wss://example.test",
        async_callback=AsyncMock(),
    )


def test_retry_uses_exponential_backoff_until_max() -> None:
    """Test reconnect retries back off to the maximum delay."""
    loop = FakeLoop()
    websocket = create_websocket(loop=loop)

    for expected_delay in [5, 10, 20, 40, 80, 160, 300, 300]:
        websocket.state = STATE_STOPPED

        websocket.retry()

        handle = loop.call_later_handles[-1]
        assert handle.delay == expected_delay
        handle.callback()

    assert websocket._reconnect_delay == MAX_RECONNECT_DELAY


async def test_successful_connection_resets_reconnect_delay() -> None:
    """Test a successful websocket connection resets the backoff delay."""
    loop = FakeLoop()
    session = FakeSession()
    websocket = create_websocket(loop=loop, session=session)
    websocket._reconnect_delay = 80

    await websocket.running()

    assert loop.call_later_handles[-1].delay == RECONNECT_DELAY
    assert websocket._reconnect_delay == RECONNECT_DELAY * 2
    assert json.loads(session.websocket.sent[0]) == {
        "event": "app_connection",
        "orbit_session_token": "token",
    }


async def test_stop_cancels_pending_reconnect() -> None:
    """Test stop cancels a pending reconnect timer."""
    loop = FakeLoop()
    websocket = create_websocket(loop=loop)

    websocket.retry()
    handle = loop.call_later_handles[-1]

    await websocket.stop()

    assert handle.cancelled
    assert websocket._reconnect_cb is None


async def test_stale_reconnect_callback_does_not_restart_after_stop() -> None:
    """Test a stale reconnect callback cannot restart a stopped websocket."""
    loop = FakeLoop()
    websocket = create_websocket(loop=loop)

    websocket.retry()
    handle = loop.call_later_handles[-1]
    await websocket.stop()
    handle.callback()

    assert websocket.state == STATE_STOPPED
    assert not loop.created_tasks
