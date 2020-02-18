"""Define an object to interact with the REST API."""

import logging
import re
import time

from asyncio import ensure_future

from .const import (
    API_HOST,
    API_POLL_PERIOD,
    DEVICES_PATH,
    TIMER_PROGRAMS_PATH,
    LOGIN_PATH,
    WS_HOST,
)
from .errors import RequestError
from .websocket import OrbitWebsocket

_LOGGER = logging.getLogger(__name__)


class Client:
    """Define the API object."""

    def __init__(
        self, username: str, password: str, loop, session, async_callback
    ) -> None:
        """Initialize."""
        self._username: str = username
        self._password: int = password
        self._ws_url: str = WS_HOST
        self._token: str = None

        self._websocket = None
        self._loop = loop
        self._session = session
        self._async_callback = async_callback

        self._devices = []
        self._last_poll_devices = 0

        self._timer_programs = []
        self._last_poll_programs = 0

    async def _request(self, method: str, endpoint: str, params: dict = None) -> list:
        """Make a request against the API."""
        url: str = f"{API_HOST}{endpoint}"

        if not params:
            params = {}

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Host": re.sub("https?://", "", API_HOST),
            "Content-Type": "application/json; charset=utf-8;",
            "Referer": API_HOST,
            "Orbit-Session-Token": self._token,
        }
        headers["User-Agent"] = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/72.0.3626.81 Safari/537.36"
        )

        async with self._session.request(
            method, url, params=params, headers=headers
        ) as resp:
            try:
                resp.raise_for_status()
                return await resp.json(content_type=None)
            except Exception as err:
                raise RequestError(f"Error requesting data from {url}: {err}")

    async def _refresh_devices(self, force_update=False):
        now = time.time()
        if force_update:
            _LOGGER.debug("Forcing device refresh")
        elif now - self._last_poll_devices < API_POLL_PERIOD:
            return

        self._devices = await self._request(
            "get", DEVICES_PATH, params={"t": str(time.time())}
        )

        self._last_poll_devices = now

    async def _refresh_timer_programs(self, force_update=False):
        now = time.time()
        if force_update:
            _LOGGER.debug("Forcing device refresh")
        elif now - self._last_poll_programs < API_POLL_PERIOD:
            return

        self._timer_programs = await self._request(
            "get", TIMER_PROGRAMS_PATH, params={"t": str(time.time())}
        )
        self._last_poll_programs = now

    async def _async_ws_handler(self, data):
        """Process incoming websocket message."""
        if self._async_callback:
            ensure_future(self._async_callback(data))

    async def login(self) -> bool:
        """Log in with username & password and save the token."""
        url: str = f"{API_HOST}{LOGIN_PATH}"
        json = {"session": {"email": self._username, "password": self._password}}

        async with self._session.request("post", url, json=json) as resp:
            try:
                resp.raise_for_status()
                response = await resp.json(content_type=None)
                _LOGGER.debug("Logged in")
                self._token = response["orbit_session_token"]

            except Exception as err:
                raise RequestError(f"Error requesting data from {url}: {err}")

        if self._token is None:
            return False

        self._websocket = OrbitWebsocket(
            token=self._token,
            loop=self._loop,
            session=self._session,
            url=self._ws_url,
            async_callback=self._async_ws_handler,
        )
        self._websocket.start()
        return True

    async def stop(self):
        if self._websocket is not None:
            await self._websocket.stop()

    @property
    async def devices(self):
        """Get all devices."""
        await self._refresh_devices()
        return self._devices

    @property
    async def timer_programs(self, force_update=False):
        """Get timer programs."""
        await self._refresh_timer_programs()
        return self._timer_programs

    async def get_device(self, device_id, force_update=False):
        """Get device by id."""
        await self._refresh_devices(force_update=force_update)
        for device in self._devices:
            if device.get("id") == device_id:
                return device
        return None

    async def send_message(self, payload):
        await self._websocket.send(payload)
