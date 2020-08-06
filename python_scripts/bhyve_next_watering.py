# pylint: disable=undefined-variable


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


now = dt_util.now()

zone_entity_id = data.get("entity_id")

if not zone_entity_id:
    raise Exception("entity_id is required to execute this script")

zone = hass.states.get(zone_entity_id)

if not zone:
    raise Exception("Entity with id {} does not exist".format(zone_entity_id))

device_name = zone.attributes.get("device_name")
zone_name = zone.attributes.get("zone_name")

if not device_name:
    raise Exception(
        "Could not find zone's device name on entity {}. Is this a BHyve zone switch entity?".format(
            zone_entity_id
        )
    )

logger.info("updating next_watering for zone: ({}: {})".format(zone_name, zone))

next_watering_entity = f"sensor.{zone_name}_next_watering".replace(" ", "_").lower()
next_watering_attrs = {"friendly_name": f"{zone_name} next watering"}

rain_delay_finishing_entity = f"sensor.{device_name}_rain_delay_finishing".replace(
    " ", "_"
).lower()
rain_delay_finishing_attrs = {"friendly_name": f"{device_name} rain delay finishing"}

rain_delay = hass.states.get(f"switch.{device_name}_rain_delay")

if zone.state == "unavailable":
    hass.states.set(next_watering_entity, "Unavailable", next_watering_attrs)
    hass.states.set(
        rain_delay_finishing_entity, "Unavailable", rain_delay_finishing_attrs
    )
else:
    delay_finishes_at = None
    next_watering = None

    if rain_delay.state == "on":
        started_at = dt_util.as_timestamp(rain_delay.attributes.get("started_at"))
        delay_seconds = rain_delay.attributes.get("delay") * 3600
        delay_finishes_at = dt_util.as_local(
            dt_util.utc_from_timestamp(started_at + delay_seconds)
        )
        hass.states.set(
            rain_delay_finishing_entity, delay_finishes_at, rain_delay_finishing_attrs
        )
    else:
        hass.states.set(rain_delay_finishing_entity, None, rain_delay_finishing_attrs)

    for program_id in ["a", "b", "c", "e"]:
        program = zone.attributes.get(f"program_{program_id}")
        logger.info("program: %s", program)
        if program is None or program.get("enabled", False) is False:
            continue

        if program.get("is_smart_program"):
            for timestamp in program.get("watering_program", []):
                watering_time = dt_util.parse_datetime(str(timestamp))
                if watering_time > now and (
                    delay_finishes_at is None or watering_time > delay_finishes_at
                ):
                    next_watering = watering_time
                    break
        else:
            """ find the next manual watering time """
            """
                Orbit day: `0` is Sunday, `1` is Monday
                Python day: `0` is Monday, `2` is Tuesday
            """

            """
                ************
                    TODO
                ************
            """

            logger.info("Checking manual program: %s", program)
            configured_days = program.get("frequency", {}).get("days")
            start_times = program.get("start_times")
            if configured_days is None:
                continue

            next_watering_dates = get_next_times(today, program)

            # next_watering_day = (
            #         filter(lambda day: (day > now_weekday), configured_days)
            #     )[0]# else configured_days[0]

    hass.states.set(next_watering_entity, next_watering, next_watering_attrs)
