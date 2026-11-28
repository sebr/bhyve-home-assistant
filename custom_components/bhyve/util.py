"""Utility functions for the BHyve integration."""

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, NamedTuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt

from .const import (
    CONF_AUTO_ADD,
    CONF_DEVICES,
    CONF_KNOWN_DEVICES,
    DEVICE_BRIDGE,
    MODE_OFF,
)

# Orbit returns ~2106-02-07 (epoch max) as a sentinel for "nothing scheduled".
# Treat any timestamp from this year on as that sentinel.
_NEXT_WATERING_SENTINEL_YEAR = 2100

# The longest interval program taken at its word; anything longer is not
# guessed (and the day-by-day scan stays short).
_MAX_INTERVAL_DAYS = 366


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

    next_start = _orbit_next_start(status)
    if next_start is None or next_start <= dt.now():
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

    Gen 2 hose timers (and some Gen 1) report ``{"clear_on_idle": true}``
    while idle instead of null, so the dict being present proves nothing.
    """
    watering_status = status.get("watering_status")
    if not isinstance(watering_status, dict):
        return False
    return watering_status.get("current_station") is not None or bool(
        watering_status.get("stations")
    )


def device_time_zone_id(device: Mapping[str, Any]) -> str | None:
    """Return the id of the device's own time zone, if it reports one."""
    timezone = device.get("timezone")
    zone_id = timezone.get("timezone_id") if isinstance(timezone, dict) else None
    return zone_id if isinstance(zone_id, str) else None


def _device_time_zone(device: Mapping[str, Any]) -> tzinfo:
    """Return the device's own time zone (programs run on its wall clock)."""
    zone_id = device_time_zone_id(device)
    # Cached: the coordinator loads each device's zone on every poll.
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
        if (
            not isinstance(interval, int)
            or not 0 < interval <= _MAX_INTERVAL_DAYS
            or anchor is None
        ):
            return None
        days = (day - anchor).days
        return days >= 0 and days % interval == 0
    return None


class NextWatering(NamedTuple):
    """A timer's next watering, as the Next watering sensor shows it."""

    start: datetime | None
    programs: list[str]
    # True when Orbit sent no usable time and this came from the programs.
    computed: bool = False
    # Why a computed time is missing: timer_off, rain_delay, not_computable,
    # no_upcoming_run.
    unavailable: str | None = None


def _waters(program: Mapping[str, Any]) -> bool:
    """Return whether a program is enabled, has a letter and waters something."""
    return (
        program.get("enabled") is True
        and bool(program.get("program"))
        and any((r.get("run_time") or 0) > 0 for r in program.get("run_times") or [])
    )


def _program_next_start(  # noqa: PLR0911
    program: Mapping[str, Any], zone: tzinfo, now: datetime
) -> tuple[datetime | None, bool]:
    """
    Return when one program next starts, and whether that could be worked out.

    A program that doesn't water (disabled, no letter, no run time) is
    readable and has no start.
    """
    if not _waters(program):
        return None, True
    frequency = program.get("frequency")
    if program.get("is_smart_program") or not isinstance(frequency, dict):
        return None, False
    starts = sorted(
        parsed
        for text in program.get("start_times") or []
        if isinstance(text, str) and (parsed := dt.parse_time(text)) is not None
    )
    if not starts:
        return None, False

    first_day = _local_date(program.get("program_start_date"), zone)
    last_day = _local_date(program.get("program_end_date"), zone)
    anchor = _local_date(frequency.get("interval_start_time"), zone) or first_day

    # Start at the first day the program can run, however far off that is.
    candidates = [now.astimezone(zone).date(), first_day]
    if frequency.get("type") == "interval":
        candidates.append(anchor)
    scan_from = max(d for d in candidates if d is not None)
    interval = frequency.get("interval")
    # Far enough to reach the next run of any frequency _runs_on accepts.
    for offset in range(max(interval if isinstance(interval, int) else 0, 31) + 2):
        day = scan_from + timedelta(days=offset)
        if last_day is not None and day > last_day:
            return None, True
        runs = _runs_on(frequency, day, anchor)
        if runs is None:
            return None, False
        if not runs:
            continue
        for start in starts:
            candidate = datetime.combine(day, start, zone)
            # As instants: wall-clock times mislead in the repeated DST hour.
            if dt.as_utc(candidate) > dt.as_utc(now):
                return candidate, True
    return None, True


def next_program_start(
    device: Mapping[str, Any], programs: Iterable[Mapping[str, Any]], now: datetime
) -> NextWatering:
    """
    Return a timer's next start, worked out from its programs.

    For timers Orbit sends no usable ``next_start_time`` for (Gen 2 hose
    timers behind a BH1G2 hub). If any program that waters the timer can't be
    read (a smart program, a frequency this code doesn't know), no time is
    given rather than one that may not be the next. Rain delays and the
    timer's mode are the caller's business.
    """
    zone = _device_time_zone(device)
    device_id = device.get("id")
    best: datetime | None = None
    letters: list[str] = []
    for program in programs:
        if program.get("device_id") != device_id:
            continue
        start, readable = _program_next_start(program, zone, now)
        if not readable:
            return NextWatering(None, [], computed=True, unavailable="not_computable")
        if start is None:
            continue
        if best is None or start < best:
            best, letters = start, [program["program"]]
        elif start == best:
            letters.append(program["program"])
    if best is None:
        return NextWatering(None, [], computed=True, unavailable="no_upcoming_run")
    return NextWatering(best, sorted(letters), computed=True)


def _orbit_next_start(status: Mapping[str, Any]) -> datetime | None:
    """Return Orbit's next_start_time, unless it is missing or its sentinel."""
    next_start = orbit_time_to_local_time(status.get("next_start_time"))
    if next_start is None or next_start.year >= _NEXT_WATERING_SENTINEL_YEAR:
        return None
    return next_start


def next_watering(
    device: Mapping[str, Any], programs: Iterable[Mapping[str, Any]]
) -> NextWatering:
    """
    Return a timer's next watering: Orbit's time, else one from its programs.

    Worked out each time it's read, from the device's current status and
    programs, so a mode change, a run starting or a program edit shows at once.
    """
    status = device.get("status")
    if not isinstance(status, dict):
        status = {}
    if _orbit_next_start(status) is not None:
        start = next_watering_time(status)
        return NextWatering(
            start, list(status.get("next_start_programs") or []) if start else []
        )
    if status.get("run_mode") == MODE_OFF:
        return NextWatering(None, [], computed=True, unavailable="timer_off")
    if rain_delay_active(status):
        return NextWatering(None, [], computed=True, unavailable="rain_delay")
    try:
        return next_program_start(device, programs, dt.now())
    except (AttributeError, TypeError, ValueError):
        # A program field of a type Orbit has not sent before.
        return NextWatering(None, [], computed=True, unavailable="not_computable")


def unoffered_device_ids(
    options: Mapping[str, Any], all_devices: Iterable[Mapping[str, Any]]
) -> list[str]:
    """
    Return the account's devices that the user has not been offered yet.

    Whether or not auto-add is on. Empty for an entry from before auto-add
    until its first setup has recorded which devices count as known.
    Bridges are always included anyway, so never "unoffered".
    """
    known = options.get(CONF_KNOWN_DEVICES)
    if known is None:
        return []
    return [d for d in leaf_device_ids(all_devices) if d not in known]


def new_device_ids(
    options: Mapping[str, Any], all_devices: Iterable[Mapping[str, Any]]
) -> list[str]:
    """Return the devices to auto-add: unoffered ones, while auto-add is on."""
    if not options.get(CONF_AUTO_ADD, True):
        return []
    return unoffered_device_ids(options, all_devices)


def is_gen2_hose_timer(
    device: Mapping[str, Any], all_devices: Iterable[Mapping[str, Any]]
) -> bool:
    """
    Return True for a Gen 2 hose timer (HT25A, behind a BH1G2 hub).

    Before auto-add, these were never set up for anyone whose timer joined
    the account after the integration did (#420).
    """
    if device.get("type") == DEVICE_BRIDGE:
        return False
    if str(device.get("hardware_version") or "").startswith("HT25A"):
        return True
    topic = device.get("device_gateway_topic")
    return topic is not None and any(
        d.get("type") == DEVICE_BRIDGE
        and d.get("device_gateway_topic") == topic
        and str(d.get("hardware_version") or "").startswith("BH1G2")
        for d in all_devices
    )


def migrated_known_device_ids(
    options: Mapping[str, Any], all_devices: Iterable[Mapping[str, Any]]
) -> list[str]:
    """
    Return the devices an entry from before auto-add counts as already offered.

    The user's selection stands for every device except an unselected Gen 2
    hose timer: that one is treated as new (so auto-add selects it), since
    the usual way it got there unselected is being paired after setup.
    """
    devices = list(all_devices)
    selected = set(options.get(CONF_DEVICES, []))
    by_id = {str(d.get("id")): d for d in devices}
    return [
        d
        for d in leaf_device_ids(devices)
        if d in selected or not is_gen2_hose_timer(by_id[d], devices)
    ]


def leaf_device_ids(all_devices: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return the ids of the account's devices other than bridges."""
    return [
        str(d["id"])
        for d in all_devices
        if d.get("id") and d.get("type") != DEVICE_BRIDGE
    ]
