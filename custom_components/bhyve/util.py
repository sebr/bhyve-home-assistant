import hashlib
from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt

from .const import CONF_DEVICES


def orbit_time_to_local_time(timestamp: str):
    """Converts the Orbit API timestamp to local time."""
    if timestamp is not None:
        return dt.as_local(dt.parse_datetime(timestamp))
    return None


def filter_configured_devices(entry: ConfigEntry, all_devices):
    """Filter the device list to those that are enabled in options."""
    return [d for d in all_devices if str(d["id"]) in entry.options[CONF_DEVICES]]


def constant_program_id(device_id, program_id, is_smart_program: bool = False):
    """For devices with multiple zones, Smart program id changes depending on the zone/s that are included.
    Generate a constant id so that it is updated on change."""
    if is_smart_program:
        program_id = hashlib.md5(
            "{}:smart_program".format(device_id).encode("utf-8")
        ).hexdigest()
    return program_id
