"""
A stateful fake of the Orbit B-hyve cloud for end-to-end tests.

It stands in for the aiohttp session that BHyveClient receives, so the real
client, websocket transport, coordinator and entities run unmodified against
it. Unlike aioclient_mock it keeps state: it issues session tokens, can expire
them, serves the REST API and the event websocket, and records the commands it
receives.
"""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import MagicMock

from aiohttp import ClientResponseError, WSMessage, WSMsgType
from yarl import URL

if TYPE_CHECKING:
    from types import TracebackType

PASSWORD = "correct-horse"
USERNAME = "gardener@example.com"

BRIDGE_ID = "bridge-1"
SPRINKLER_ID = "sprinkler-1"
SPRINKLER_MAC = "4467552a366e"
PROGRAM_ID = "program-a"


def default_devices() -> list[dict[str, Any]]:
    """Return a hub with a two-zone sprinkler timer behind it."""
    return [
        {
            "id": BRIDGE_ID,
            "name": "Wi-Fi Hub",
            "type": "bridge",
            "mac_address": "446755dc6001",
            "is_connected": True,
            "device_gateway_topic": "gateway-1",
        },
        {
            "id": SPRINKLER_ID,
            "name": "Garden Timer",
            "type": "sprinkler_timer",
            "mac_address": SPRINKLER_MAC,
            "hardware_version": "HT25-0000",
            "firmware_version": "98",
            "is_connected": True,
            "device_gateway_topic": "gateway-1",
            "manual_preset_runtime_sec": 300,
            "water_sense_mode": "off",
            "battery": {"percent": 80},
            "zones": [
                {"station": 1, "name": "Front Yard", "smart_watering_enabled": False},
                {"station": 2, "name": "Back Yard", "smart_watering_enabled": False},
            ],
            "status": {
                "run_mode": "auto",
                "rain_delay": 0,
                "next_start_programs": ["a"],
            },
        },
    ]


def default_programs() -> list[dict[str, Any]]:
    """Return one manual program for the sprinkler."""
    return [
        {
            "id": PROGRAM_ID,
            "device_id": SPRINKLER_ID,
            "name": "Morning",
            "program": "a",
            "enabled": True,
            "is_smart_program": False,
            "start_times": ["06:00"],
            "frequency": {"type": "days", "days": [1, 3, 5]},
            "budget": 100,
            "run_times": [{"station": 1, "run_time": 10}],
        }
    ]


@dataclass
class RecordedRequest:
    """A REST request the fake cloud received."""

    method: str
    path: str
    token: str | None
    body: Any


class FakeResponse:
    """The parts of aiohttp.ClientResponse that BHyveClient uses."""

    def __init__(self, status: int, body: Any = None) -> None:
        """Initialize the response."""
        self.status = status
        self._body = body

    def raise_for_status(self) -> None:
        """Raise like aiohttp for an error status."""
        if self.status >= 400:
            raise ClientResponseError(
                request_info=MagicMock(), history=(), status=self.status
            )

    async def json(self, **_kwargs: Any) -> Any:
        """Return the JSON body."""
        return copy.deepcopy(self._body)

    async def __aenter__(self) -> Self:
        """Enter the response context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the response context."""


class FakeOrbitSocket:
    """One server-side websocket connection."""

    def __init__(self) -> None:
        """Initialize the connection."""
        self.closed = False
        self.sent: list[dict[str, Any]] = []
        self._incoming: asyncio.Queue[WSMessage] = asyncio.Queue()

    async def send_str(self, data: str) -> None:
        """Receive a message from the integration."""
        if self.closed:
            msg = "Cannot write to closing transport"
            raise ConnectionResetError(msg)
        self.sent.append(json.loads(data))

    async def receive(self) -> WSMessage:
        """Hand the integration the next server message."""
        return await self._incoming.get()

    def push(self, payload: dict[str, Any]) -> None:
        """Send an event to the integration."""
        self._incoming.put_nowait(WSMessage(WSMsgType.TEXT, json.dumps(payload), None))

    def drop(self) -> None:
        """Simulate the server dropping the connection."""
        self.closed = True
        self._incoming.put_nowait(WSMessage(WSMsgType.CLOSED, None, None))

    async def close(self) -> None:
        """Close the connection from the integration's side."""
        if not self.closed:
            self.drop()

    async def pong(self) -> None:
        """Answer a ping."""

    def exception(self) -> None:
        """Report no transport exception."""

    def commands(self) -> list[dict[str, Any]]:
        """Return the messages sent, minus the handshake and keepalives."""
        return [m for m in self.sent if m["event"] not in ("app_connection", "ping")]


class _SocketContext:
    """Async context manager returned by ws_connect."""

    def __init__(self, cloud: FakeOrbitCloud) -> None:
        self._cloud = cloud
        self._socket: FakeOrbitSocket | None = None

    async def __aenter__(self) -> FakeOrbitSocket:
        if self._cloud.websocket_down:
            raise ClientResponseError(request_info=MagicMock(), history=(), status=503)
        self._socket = FakeOrbitSocket()
        self._cloud.sockets.append(self._socket)
        return self._socket

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._socket is not None:
            self._socket.closed = True


@dataclass
class FakeOrbitCloud:
    """The Orbit cloud: REST API, session tokens and the event websocket."""

    password: str = PASSWORD
    # Orbit renamed this from orbit_api_key (#474).
    token_field: str = "orbit_session_token"
    devices: list[dict[str, Any]] = field(default_factory=default_devices)
    programs: list[dict[str, Any]] = field(default_factory=default_programs)
    history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Path prefixes that answer with an HTTP error, e.g. {"/v1/devices": 500}.
    failures: dict[str, int] = field(default_factory=dict)
    websocket_down: bool = False

    logins: int = 0
    valid_tokens: set[str] = field(default_factory=set)
    requests: list[RecordedRequest] = field(default_factory=list)
    sockets: list[FakeOrbitSocket] = field(default_factory=list)

    @property
    def socket(self) -> FakeOrbitSocket:
        """Return the most recent websocket connection."""
        return self.sockets[-1]

    def expire_sessions(self) -> None:
        """Invalidate every issued session token."""
        self.valid_tokens.clear()

    def device(self, device_id: str) -> dict[str, Any]:
        """Return the cloud's copy of a device, for changing between polls."""
        return next(d for d in self.devices if d["id"] == device_id)

    def count(self, method: str, path: str) -> int:
        """Count requests for a method and path."""
        return sum(1 for r in self.requests if r.method == method and r.path == path)

    # aiohttp.ClientSession interface used by BHyveClient and OrbitWebsocket.

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,  # noqa: ARG002
        headers: dict | None = None,
        json: Any = None,
    ) -> FakeResponse:
        """Answer a REST request."""
        method = method.lower()
        path = URL(url).path
        token = (headers or {}).get("Orbit-Session-Token") or None
        self.requests.append(RecordedRequest(method, path, token, json))

        for prefix, status in self.failures.items():
            if path.startswith(prefix):
                return FakeResponse(status)

        if method == "post" and path == "/v1/session":
            return self._login(json)
        if token not in self.valid_tokens:
            return FakeResponse(401, {"error": "unauthorized"})
        return self._route(method, path)

    def ws_connect(self, _url: str, **_kwargs: Any) -> _SocketContext:
        """Open the event websocket."""
        return _SocketContext(self)

    def _login(self, body: dict[str, Any]) -> FakeResponse:
        session = (body or {}).get("session", {})
        if session.get("email") != USERNAME or session.get("password") != self.password:
            return FakeResponse(401, {"error": "invalid credentials"})
        self.logins += 1
        token = f"token-{self.logins}"
        self.valid_tokens.add(token)
        return FakeResponse(200, {self.token_field: token, "user_id": "user-1"})

    def _route(self, method: str, path: str) -> FakeResponse:
        if method == "get":
            if path == "/v1/devices":
                return FakeResponse(200, self.devices)
            if path == "/v1/sprinkler_timer_programs":
                return FakeResponse(200, self.programs)
            if path.startswith("/v1/watering_events/"):
                device_id = path.rsplit("/", 1)[-1]
                return FakeResponse(200, self.history.get(device_id, []))
            if path.startswith("/v1/landscape_descriptions/"):
                return FakeResponse(200, [])
        if method == "put":
            return FakeResponse(200, {})
        return FakeResponse(404, {"error": f"no route for {method} {path}"})
