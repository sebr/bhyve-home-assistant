"""Define a client to interact with the Orbit BHyve APIs."""
import logging

from aiohttp import ClientSession

from .api import API

_LOGGER = logging.getLogger(__name__)


class Client:  # pylint: disable=too-few-public-methods
    """Define the client."""

    def __init__(self, username: str, password: str, session: ClientSession) -> None:
        """Initialize."""
        self.api: API = API(username, password, session)
