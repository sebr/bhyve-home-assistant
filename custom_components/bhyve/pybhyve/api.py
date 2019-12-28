"""Define an object to interact with the REST API."""

import logging
import re
import time

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

from .const import API_HOST, API_POLL_PERIOD, DEVICES_PATH, LOGIN_PATH
from .errors import RequestError
from .websocket import Websocket

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)


class API:
    """Define the API object."""

    def __init__(self, username: str, password: str, session: ClientSession) -> None:
        """Initialize."""
        self._username: str = username
        self._password: int = password
        self._token: str = None
        self._websocket: Websocket = None
        self._session: ClientSession = session
        self._devices = []
        self._last_poll = 0

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

        _LOGGER.debug("Making request: %s: %s %s", method, endpoint, params)

        async with self._session.request(
            method, url, params=params, headers=headers
        ) as resp:
            try:
                resp.raise_for_status()
                return await resp.json(content_type=None)
            except ClientError as err:
                raise RequestError(f"Error requesting data from {url}: {err}")

    async def _refresh_devices(self):
        now = time.time()
        if now - self._last_poll < API_POLL_PERIOD:
            _LOGGER.debug("Skipping refresh, not enough time has passed")
            return

        params = {"t": str(time.time())}
        self._devices = await self._request("get", DEVICES_PATH, params=params)

        for device in self._devices:
            deviceName = device.get("name")
            deviceType = device.get("type")
            _LOGGER.info("Created device: {} [{}]".format(deviceType, deviceName))

        self._last_poll = now

    @property
    def websocket(self) -> Websocket:
        """Return websocket connection."""
        if self._websocket is None:
            self._websocket: Websocket = Websocket(self._token, self._session)
        return self._websocket

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

                return True
            except ClientError as err:
                raise RequestError(f"Error requesting data from {url}: {err}")

        return False

    @property
    async def devices(self):
        """Get all devices."""
        await self._refresh_devices()
        return self._devices

    async def get_device(self, device_id):
        """Get device by id."""
        await self._refresh_devices()
        for device in self._devices:
            if device.get("id") == device_id:
                return device
        return None
