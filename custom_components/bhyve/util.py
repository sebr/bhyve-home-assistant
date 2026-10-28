"""Utility functions for the BHyve integration."""

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt

from .const import CONF_AUTO_ADD, CONF_DEVICES, CONF_KNOWN_DEVICES, DEVICE_BRIDGE

# Orbit returns ~2106-02-07 (epoch max) as a sentinel for "nothing scheduled".
# Treat any timestamp from this year on as that sentinel.
_NEXT_WATERING_SENTINEL_YEAR = 2100


def rain_delay_active(status: dict) -> bool:
    """Return True when the device status has a rain delay in force."""
    return (status.get("rain_delay") or 0) > 0


def next_watering_time(status: dict) -> datetime | None:
    """
    Return the device's next watering time, or None when it is known to be wrong.

    Orbit only refreshes next_start_time on the 5-minute poll, and does not
    always clear it, so hide it when (#430):
    - a rain delay is active, since Orbit won't water through it;
    - it is Orbit's "nothing scheduled" sentinel;
    - it is in the past, e.g. the skipped run just after a rain delay ends.
    """
    if rain_delay_active(status):
        return None

    next_start = orbit_time_to_local_time(status.get("next_start_time"))
    if next_start is None or next_start.year >= _NEXT_WATERING_SENTINEL_YEAR:
        return None
    if next_start <= dt.now():
        return None
    return next_start


def orbit_time_to_local_time(timestamp: str | None) -> datetime | None:
    """Convert the Orbit API timestamp to local time."""
    if timestamp is not None:
        parsed = dt.parse_datetime(timestamp)
        if parsed is not None:
            return dt.as_local(parsed)
    return None


def orbit_timestamp_now() -> str:
    """Return the current UTC time in the format Orbit expects in commands."""
    return dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def filter_configured_devices(entry: ConfigEntry, all_devices: list) -> list:
    """
    Filter the device list to those that are enabled in options.

    Bridge devices are always included since they are not user-selectable
    but are needed to register the hub in Home Assistant.
    """
    configured_devices = entry.options.get(CONF_DEVICES, [])
    filtered_devices = [
        d
        for d in all_devices
        if str(d["id"]) in configured_devices or d.get("type") == DEVICE_BRIDGE
    ]

    # Ensure that all devices have a name
    for device in filtered_devices:
        if device.get("name") is None:
            device["name"] = "Unknown Device"

    return filtered_devices


def watering_in_progress(status: dict) -> bool:
    """
    Return True when the status says a station is watering.

    Gen 2 hose timers report ``{"clear_on_idle": true}`` while idle, where
    Gen 1 timers report null, so the dict being present proves nothing.
    """
    watering_status = status.get("watering_status")
    if not isinstance(watering_status, dict):
        return False
    return watering_status.get("current_station") is not None or bool(
        watering_status.get("stations")
    )


def _device_time_zone(device: Mapping[str, Any]) -> tzinfo:
    """Return the device's own time zone (programs run on its wall clock)."""
    timezone = device.get("timezone")
    zone_id = timezone.get("timezone_id") if isinstance(timezone, dict) else None
    if zone_id and (zone := dt.get_time_zone(zone_id)) is not None:
        return zone
    return dt.get_default_time_zone()


def _local_date(timestamp: Any, zone: tzinfo) -> date | None:
    """Return an Orbit timestamp's calendar date on the device's clock."""
    if not isinstance(timestamp, str):
        return None
    parsed = dt.parse_datetime(timestamp)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone).date()


def _runs_on(
    frequency: Mapping[str, Any], day: date, anchor: date | None
) -> bool | None:
    """
    Return whether a program's frequency waters on ``day``.

    None for a frequency this code doesn't know, so no time gets guessed.
    """
    kind = frequency.get("type")
    if kind == "days":
        # Orbit numbers days 0 = Sunday ... 6 = Saturday.
        return (day.weekday() + 1) % 7 in (frequency.get("days") or [])
    if kind == "even":
        return day.day % 2 == 0
    if kind == "odd":
        return day.day % 2 == 1
    if kind == "interval":
        interval = frequency.get("interval")
        if not isinstance(interval, int) or interval <= 0 or anchor is None:
            return None
        days = (day - anchor).days
        return days >= 0 and days % interval == 0
    return None


def _program_next_start(  # noqa: PLR0911
    program: Mapping[str, Any], zone: tzinfo, now: datetime
) -> datetime | None:
    """Return when one (non-smart, enabled) program next starts, if known."""
    if not _counts(program) or program.get("is_smart_program"):
        return None
    frequency = program.get("frequency")
    if not isinstance(frequency, dict):
        return None
    starts = sorted(
        parsed
        for text in program.get("start_times") or []
        if isinstance(text, str) and (parsed := dt.parse_time(text)) is not None
    )
    if not starts:
        return None

    first_day = _local_date(program.get("program_start_date"), zone)
    last_day = _local_date(program.get("program_end_date"), zone)
    anchor = _local_date(frequency.get("interval_start_time"), zone) or first_day

    today = now.astimezone(zone).date()
    interval = frequency.get("interval")
    horizon = max(interval if isinstance(interval, int) else 0, 31) + 1
    for offset in range(horizon + 1):
        day = today + timedelta(days=offset)
        if first_day is not None and day < first_day:
            continue
        if last_day is not None and day > last_day:
            return None
        runs = _runs_on(frequency, day, anchor)
        if runs is None:
            return None
        if not runs:
            continue
        for start in starts:
            candidate = datetime.combine(day, time(start.hour, start.minute), zone)
            if candidate > now:
                return candidate
    return None


def _counts(program: Mapping[str, Any]) -> bool:
    """Return whether a program is enabled, has a letter and waters something."""
    return (
        program.get("enabled") is True
        and bool(program.get("program"))
        and any((r.get("run_time") or 0) > 0 for r in program.get("run_times") or [])
    )


def _guessable(program: Mapping[str, Any]) -> bool:
    """next_program_start knows how this program's days work."""
    if program.get("is_smart_program"):
        return False
    frequency = program.get("frequency")
    if not isinstance(frequency, dict):
        return False
    kind = frequency.get("type")
    if kind in ("days", "even", "odd"):
        return True
    if kind == "interval":
        interval = frequency.get("interval")
        anchor = frequency.get("interval_start_time") or program.get(
            "program_start_date"
        )
        return isinstance(interval, int) and interval > 0 and anchor is not None
    return False


def programs_computable(
    device: Mapping[str, Any], programs: Iterable[Mapping[str, Any]]
) -> bool:
    """Every program that would water this timer is one next_program_start can read."""
    device_id = device.get("id")
    return all(
        _guessable(p)
        for p in programs
        if p.get("device_id") == device_id and _counts(p)
    )


def next_program_start(
    device: Mapping[str, Any], programs: Iterable[Mapping[str, Any]], now: datetime
) -> tuple[datetime, list[str]] | None:
    """
    Return a timer's next scheduled start and the program letters starting then.

    For timers whose status has no ``next_start_time`` (Gen 2 hose timers
    behind a BH1G2 hub). Uses the timer's enabled, non-smart programs:
    frequency ``days`` (0 = Sunday), ``even``, ``odd`` (calendar parity) or
    ``interval`` (counted from ``interval_start_time``, else the program's
    start date), its ``start_times`` on the timer's own clock, and the
    program's start/end dates. Smart programs and unknown frequencies are
    not guessed. Rain delays and the timer's mode are the caller's business.
    """
    zone = _device_time_zone(device)
    device_id = device.get("id")
    best: datetime | None = None
    letters: list[str] = []
    for program in programs:
        if program.get("device_id") != device_id:
            continue
        start = _program_next_start(program, zone, now)
        if start is None:
            continue
        if best is None or start < best:
            best, letters = start, [program["program"]]
        elif start == best:
            letters.append(program["program"])
    if best is None:
        return None
    return best, sorted(letters)


def new_leaf_device_ids(
    options: Mapping[str, Any], all_devices: Iterable[Mapping[str, Any]]
) -> list[str]:
    """
    Return the account's devices that the device picker has never offered.

    Only when auto-add is on and the entry records what it offered; an entry
    from before auto-add existed keeps its selection until its options are
    saved once. Bridges are always included anyway, so never "new".
    """
    if options.get(CONF_AUTO_ADD) is not True:
        return []
    known = options.get(CONF_KNOWN_DEVICES)
    if known is None:
        return []
    return [
        str(d["id"])
        for d in all_devices
        if d.get("id") and d.get("type") != DEVICE_BRIDGE and str(d["id"]) not in known
    ]


def options_with_new_devices(
    options: Mapping[str, Any], new_ids: list[str]
) -> dict[str, Any]:
    """Return the options with new devices selected and remembered as offered."""
    return {
        **options,
        CONF_DEVICES: [*options.get(CONF_DEVICES, []), *new_ids],
        CONF_KNOWN_DEVICES: [*options.get(CONF_KNOWN_DEVICES, []), *new_ids],
    }
