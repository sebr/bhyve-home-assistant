from homeassistant.util import dt


def orbit_time_to_local_time(timestamp: str):
    """Converts the Orbit API timestamp to local time."""
    if timestamp is not None:
        return dt.as_local(dt.parse_datetime(timestamp))
    return None


def anonymize(device):
    """Removes PII from Orbit API device response."""
    device["address"] = "REDACTED"
    device["full_location"] = "REDACTED"
    device["location"] = "REDACTED"
    return device
