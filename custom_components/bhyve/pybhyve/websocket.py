"""Define an object to interact with the Websocket API."""
import logging
from typing import Awaitable, Callable, Optional, Union

from aiohttp import ClientError, ClientSession, ClientWebSocketResponse

from .const import WS_HOST
from .errors import WebsocketError

_LOGGER = logging.getLogger()


class Websocket:
    """Define the websocket."""

    def __init__(self, token: str, session: ClientSession) -> None:
        """Initialize."""
        self._token: str = token
        self._session: ClientSession = session
        self._websocket: ClientWebSocketResponse = None
        self._async_user_connect_handler: Optional[Awaitable] = None
        self._user_connect_handler: Optional[Callable] = None
        self._async_user_message_handler: Optional[Awaitable] = None
        self._user_message_handler: Optional[Callable] = None

    async def connect(self) -> None:
        """Connect to the socket."""
        try:
            self._websocket = await self._session.ws_connect(WS_HOST)

            await self.send({
                'event': 'app_connection',
                'orbit_session_token': self._token
            })

            if self._async_user_connect_handler:
                await self._async_user_connect_handler()  # type: ignore
            elif self._user_connect_handler:
                self._user_connect_handler()

            async for msg in self._websocket:
                _LOGGER.info("Received message: %s", msg)
                if self._async_user_message_handler:
                    await self._async_user_message_handler(msg)  # type: ignore
                elif self._user_message_handler:
                    self._user_message_handler(msg)

        except ClientError as err:
            _LOGGER.info(err)
            raise WebsocketError(err) from None

    async def disconnect(self) -> None:
        """Disconnect from the socket."""
        await self._websocket.close()

    async def send(self, payload: dict) -> None:
        """Send a message via websocket."""
        try:
            _LOGGER.info("Sending %s", payload)
            await self._websocket.send_json(payload)
        except ClientError as err:
            _LOGGER.info(err)
            raise WebsocketError(err) from None

    def async_on_connect(self, target: Awaitable) -> None:
        """Define a coroutine to be called when connecting."""
        self._async_user_connect_handler = target
        self._user_connect_handler = None

    def on_connect(self, target: Callable) -> None:
        """Define a method to be called when connecting."""
        self._async_user_connect_handler = None
        self._user_connect_handler = target

    def async_on_message(self, target: Awaitable) -> None:
        """Define a coroutine to be called when data is received."""
        self._async_user_message_handler = target
        self._user_message_handler = None

    def on_message(self, target: Union[Awaitable, Callable]) -> None:
        """Define a method to be called when data is received."""
        self._async_user_message_handler = None
        self._user_message_handler = target

    async def _ping(self) -> None:
        """Ping the websocket."""
        _LOGGER.info("Ping")
        await self.send({"event": "ping"})

