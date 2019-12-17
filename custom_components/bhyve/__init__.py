import logging
from datetime import timedelta

import voluptuous as vol
from requests.exceptions import HTTPError, ConnectTimeout

from homeassistant.const import (
    CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_HOST)
from homeassistant.helpers import config_validation as cv

__version__ = '0.0.1'

_LOGGER = logging.getLogger(__name__)

CONF_ATTRIBUTION = "Data provided by api.orbitbhyve.com"
DATA_BHYVE = 'data_bhyve'
DEFAULT_BRAND = 'Orbit BHyve'
DOMAIN = 'bhyve'

NOTIFICATION_ID = 'bhyve_notification'
NOTIFICATION_TITLE = 'Orbit BHyve Component Setup'

DEFAULT_HOST = 'https://api.orbitbhyve.com'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.url
    }),
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    """Set up the BHyve component."""

    _LOGGER.info('bhyve loading')

    # Read config
    conf = config[DOMAIN]
    username = conf.get(CONF_USERNAME)
    password = conf.get(CONF_PASSWORD)
    host = conf.get(CONF_HOST)

    _LOGGER.info(host)
    
    try:
        from .pybhyve import PyBHyve

        bhyve = PyBHyve(username=username, password=password)
        if not bhyve.is_connected:
            return False

        hass.data[DATA_BHYVE] = bhyve

    except (ConnectTimeout, HTTPError) as ex:
        _LOGGER.error("Unable to connect to Orbit BHyve: %s", str(ex))
        hass.components.persistent_notification.create(
            'Error: {}<br />You will need to restart hass after fixing.'.format(ex),
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID)
        return False

    return True
