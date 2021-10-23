from homeassistant.util import dt


def orbit_time_to_local_time(timestamp: str):
    if timestamp is not None:
        return dt.as_local(dt.parse_datetime(timestamp))
    return None

#Get last run date as age
def orbit_get_age(timestamp: str):
    if timestamp is not None:
        return dt.get_age(dt.parse_datetime(timestamp))
    return None

def anonymize(device):
    device["address"] = "REDACTED"
    device["full_location"] = "REDACTED"
    device["location"] = "REDACTED"
    return device
