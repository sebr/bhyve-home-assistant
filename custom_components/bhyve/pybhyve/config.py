from .constant import DEFAULT_HOST

class BHyveConfig(object):
    def __init__(self, bhyve, **kwargs):
        """ The constructor.

        Args:
            kwargs (kwargs): Configuration options.

        """
        self._bhyve = bhyve
        self._kw = kwargs

    @property
    def name(self, default='bhyve'):
        return self._kw.get('name', default)

    @property
    def username(self, default='unknown'):
        return self._kw.get('username', default)

    @property
    def password(self, default='unknown'):
        return self._kw.get('password', default)

    @property
    def host(self, default=DEFAULT_HOST):
        return self._kw.get('host', default)

    @property
    def request_timeout(self, default=60):
        return self._kw.get('request_timeout', default)

