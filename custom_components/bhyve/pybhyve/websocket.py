"""Define an object to interact with the Websocket API."""
import asyncio
import logging
import threading

from asyncio import sleep
from typing import Awaitable, Callable, Optional, Union

from aiohttp import ClientError, ClientSession, ClientWebSocketResponse, WSMsgType, WSMessage

from .const import WS_HOST
from .errors import WebsocketError

_LOGGER = logging.getLogger(__name__)


class Websocket:
    """Define the websocket."""

    def __init__(self, token: str, session: ClientSession) -> None:
        """Initialize."""
        self._token: str = token
        self._session: ClientSession = session
        self._websocket: ClientWebSocketResponse = None
        self._user_connect_handler: Optional[Callable] = None
        self._user_disconnect_handler: Optional[Callable] = None
        self._user_message_handler: Optional[Callable] = None
        self._update_interval: int = 5
        self._lock = threading.Condition()

    async def connect(self) -> None:
        """Connect to the socket."""
        try:
            with self._lock:
                self._websocket = await self._session.ws_connect(WS_HOST)

            _LOGGER.info("Sending app token")
            await self.send(
                {"event": "app_connection", "orbit_session_token": self._token}
            )

            if self._user_connect_handler:
                _LOGGER.info("Invoking ws connect handler")
                self._user_connect_handler()

            while True:
                _LOGGER.info("Waiting for messages")
                with self._lock:
                    msg = await self._websocket.receive()

                _LOGGER.info("Received message: %s", msg)
                if msg.type == WSMsgType.TEXT:
                    if self._user_message_handler:
                        self._user_message_handler(msg)
                elif msg.type == WSMsgType.BINARY:
                    pass
                elif msg.type == WSMsgType.PING:
                    self._websocket.pong()
                elif msg.type == WSMsgType.PONG:
                    pass
                else:
                    if msg.type == WSMsgType.CLOSE:
                        _LOGGER.warning('Close code received: {} extra: {}'.format(msg.data, msg.extra))
                        if self._user_disconnect_handler:
                            self._user_disconnect_handler()
                    elif msg.type == WSMsgType.ERROR:
                        _LOGGER.warning('Error during receive {}'.format(self._websocket.exception()))
                    break

                await self._ping()
                await asyncio.sleep(self._update_interval)

        except ClientError as err:
            _LOGGER.info(err)
            raise WebsocketError(err) from None

    async def disconnect(self) -> None:
        """Disconnect from the socket."""
        await self._websocket.close()

    async def send(self, payload: dict) -> None:
        """Send a message via websocket."""
        try:
            _LOGGER.debug("Sending %s", payload)
            await self._websocket.send_json(payload)
        except ClientError as err:
            _LOGGER.info(err)
            raise WebsocketError(err) from None

    def on_connect(self, target: Callable) -> None:
        """Define a method to be called when connecting."""
        self._async_user_connect_handler = None
        self._user_connect_handler = target

    def on_disconnect(self, target: Callable) -> None:
        """Define a method to be called when connecting."""
        self._user_disconnect_handler = target

    def on_message(self, target: Union[Awaitable, Callable]) -> None:
        """Define a method to be called when data is received."""
        self._async_user_message_handler = None
        self._user_message_handler = target

    async def _ping(self) -> None:
        """Ping the websocket."""
        await self.send({"event": "ping"})
