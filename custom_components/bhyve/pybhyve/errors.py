"""Define package errors."""


class BHyveError(Exception):
    """Define a base error."""

    pass


class RequestError(BHyveError):
    """Define an error related to invalid requests."""

    pass


class WebsocketError(BHyveError):
    """Define an error related to generic websocket errors."""

    pass
