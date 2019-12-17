import base64
import datetime
import logging
import os
import threading
import time

from .backend import BHyveBackEnd
from .config import BHyveConfig
from .constant import (DEVICES_PATH, API_POLL_PERIOD)
from .device import BHyveDevice

logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger('pybhyve')

__version__ = '0.0.1'


class PyBHyve(object):

    def __init__(self, **kwargs):

        self.info('pybhyve loading')
        # Set up the config first.
        self._cfg = BHyveConfig(self, **kwargs)

        self._be = BHyveBackEnd(self)

        self._devices = []

        self.info('pybhyve starting')
        self._last_poll = 0
        self._refresh_devices()

    def __repr__(self):
        # Representation string of object.
        return "<{0}: {1}>".format(self.__class__.__name__, self._cfg.name)

    def _refresh_devices(self):
        now = time.time()
        if (now - self._last_poll < API_POLL_PERIOD):
            self.debug('Skipping refresh, not enough time has passed')
            return

        self._devices = []
        devices = self._be.get(DEVICES_PATH + "?t={}".format(time.time()))

        for device in devices:
            deviceName = device.get('name')
            deviceType = device.get('type')
            self.info('Created device: {} [{}]'.format(deviceType, deviceName))
            self._devices.append(BHyveDevice(deviceName, self, device))
        
        self._last_poll = now

    @property
    def cfg(self):
        return self._cfg

    @property
    def devices(self):
        return self._devices

    @property
    def is_connected(self):
        return self._be.is_connected()

    def get_device(self, device_id):
        self._refresh_devices()
        for device in self._devices:
            if device.device_id == device_id:
                return device
        return None

    def update(self):
        pass

    def error(self, msg):
        _LOGGER.error(msg)

    def warning(self, msg):
        _LOGGER.warning(msg)

    def info(self, msg):
        _LOGGER.info(msg)

    def debug(self, msg):
        _LOGGER.debug(msg)
