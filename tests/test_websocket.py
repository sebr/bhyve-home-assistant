"""Test Orbit BHyve websocket transport."""

import json
import logging
from collections.abc import Callable, Coroutine
from types import TracebackType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import WSMsgType

from custom_components.bhyve.pybhyve.websocket import (
    MAX_RECONNECT_DELAY,
    RECONNECT_DELAY,
    STATE_STOPPED,
    OrbitWebsocket,
)

WEBSOCKET_LOGGER = "custom_components.bhyve.pybhyve.websocket"


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


class FailingWebsocketContext:
    """Fake websocket context that raises on entry."""

    def __init__(self, exc: BaseException) -> None:
        """Initialize the failing context with the exception to raise."""
        self.exc = exc

    async def __aenter__(self) -> FakeWebSocket:
        """Raise the configured exception."""
        raise self.exc

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the failing context (unreachable when __aenter__ raises)."""


class FakeSession:
    """Fake aiohttp client session."""

    def __init__(self, ws_connect_error: BaseException | None = None) -> None:
        """Initialize the fake session, optionally raising on ws_connect."""
        self.websocket = FakeWebSocket()
        self.ws_connect_error = ws_connect_error

    def ws_connect(
        self,
        _url: str,
        **_kwargs: object,
    ) -> FakeWebsocketContext | FailingWebsocketContext:
        """Return a fake websocket context, or one that raises on entry."""
        if self.ws_connect_error is not None:
            return FailingWebsocketContext(self.ws_connect_error)
        return FakeWebsocketContext(self.websocket)


def make_response_error(status: int) -> aiohttp.ClientResponseError:
    """Build an aiohttp ClientResponseError with the given status."""
    return aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=status,
        message=f"HTTP {status}",
    )


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


@pytest.mark.parametrize("status", [500, 502, 503, 504, 599])
async def test_5xx_handshake_warns_and_schedules_retry(
    caplog: pytest.LogCaptureFixture, status: int
) -> None:
    """Test 5xx handshake responses warn and schedule a backoff retry."""
    loop = FakeLoop()
    session = FakeSession(ws_connect_error=make_response_error(status))
    websocket = create_websocket(loop=loop, session=session)

    caplog.set_level(logging.DEBUG, logger=WEBSOCKET_LOGGER)
    await websocket.running()

    records = [r for r in caplog.records if r.name == WEBSOCKET_LOGGER]
    assert any(
        r.levelno == logging.WARNING and str(status) in r.getMessage() for r in records
    )
    assert not any(r.levelno >= logging.ERROR for r in records)
    assert loop.call_later_handles[-1].delay == RECONNECT_DELAY
    assert websocket._reconnect_delay == RECONNECT_DELAY * 2


async def test_non_5xx_handshake_errors_and_schedules_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test non-5xx handshake responses log an error and schedule a retry."""
    loop = FakeLoop()
    session = FakeSession(ws_connect_error=make_response_error(401))
    websocket = create_websocket(loop=loop, session=session)

    caplog.set_level(logging.DEBUG, logger=WEBSOCKET_LOGGER)
    await websocket.running()

    records = [r for r in caplog.records if r.name == WEBSOCKET_LOGGER]
    assert any(
        r.levelno == logging.ERROR
        and "Unexpected websocket HTTP error" in r.getMessage()
        for r in records
    )
    assert loop.call_later_handles[-1].delay == RECONNECT_DELAY
