import datetime
import logging

_LOGGER = logging.getLogger(__name__)


def next_weekday(day, weekday: int, start_time: datetime):
    days_ahead = weekday - day.weekday()
    if days_ahead < 0:  # Target day already happened this week
        days_ahead += 7
    d = day + datetime.timedelta(days=days_ahead)
    return d.replace(hour=start_time.hour, minute=start_time.minute)


"""
    Orbit day: `0` is Sunday, `1` is Monday
    Python day: `0` is Monday, `2` is Tuesday
"""


def get_next_times(today, program):
    configured_days = program.get("frequency", {}).get("days")
    start_times = program.get("start_times")

    next_watering_dates = list()
    for day in configured_days:
        day = day - 1 if day > 0 else 6
        for start_time in start_times:
            time = datetime.datetime.strptime(start_time, "%H:%M")
            next_day = next_weekday(today, day, time)
            _LOGGER.info(f"{today}, {next_day}")
            if next_day > today:
                next_watering_dates.append(next_day)
    return next_watering_dates


def test_two_days_one_time():
    program = {
        "start_times": ["07:30"],
        "frequency": {"type": "days", "days": [1, 4]},
        "run_times": [{"run_time": 20, "station": 1}],
    }

    today = datetime.datetime(2020, 7, 17)

    next_watering_dates = get_next_times(today, program)

    assert len(next_watering_dates) == 2
    assert next_watering_dates[0].strftime("%Y-%m-%d %H:%M") == "2020-07-20 07:30"
    assert next_watering_dates[1].strftime("%Y-%m-%d %H:%M") == "2020-07-23 07:30"


def test_two_days_two_times():
    program = {
        "start_times": ["07:30", "09:15"],
        "frequency": {"type": "days", "days": [1, 4]},
        "run_times": [{"run_time": 20, "station": 1}],
    }

    today = datetime.datetime(2020, 7, 17)

    next_watering_dates = get_next_times(today, program)

    assert len(next_watering_dates) == 4
    assert next_watering_dates[0].strftime("%Y-%m-%d %H:%M") == "2020-07-20 07:30"
    assert next_watering_dates[1].strftime("%Y-%m-%d %H:%M") == "2020-07-20 09:15"
    assert next_watering_dates[2].strftime("%Y-%m-%d %H:%M") == "2020-07-23 07:30"
    assert next_watering_dates[3].strftime("%Y-%m-%d %H:%M") == "2020-07-23 09:15"


def test_next_time_is_same_day():
    program = {
        "start_times": ["07:30", "09:15"],
        "frequency": {"type": "days", "days": [1, 3]},
        "run_times": [{"run_time": 20, "station": 1}],
    }

    today = datetime.datetime(2020, 7, 13, 8, 0, 0)

    next_watering_dates = get_next_times(today, program)

    assert len(next_watering_dates) == 3
    assert next_watering_dates[0].strftime("%Y-%m-%d %H:%M") == "2020-07-13 09:15"
    assert next_watering_dates[1].strftime("%Y-%m-%d %H:%M") == "2020-07-15 07:30"
    assert next_watering_dates[2].strftime("%Y-%m-%d %H:%M") == "2020-07-15 09:15"
