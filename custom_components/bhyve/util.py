from homeassistant.util import dt


def orbit_time_to_local_time(timestamp: str):
    return dt.as_local(dt.parse_datetime(timestamp))
