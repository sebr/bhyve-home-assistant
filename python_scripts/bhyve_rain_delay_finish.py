now = dt_util.now()

zone_entity_id = data.get("entity_id")
zone = hass.states.get(zone_entity_id)

device_name = zone.attributes["device_name"]

logger.info("updating rain_delay_finishing for zone: ({}: {})".format(device_name, zone))

rain_delay_finishing_entity = f"sensor.rain_delay_finishing_{device_name}"
rain_delay_finishing_attrs = {
    "friendly_name": f"{device_name} rain delay finishing"
}

rain_delay = hass.states.get(f"binary_sensor.rain_delay_{device_name}")

if zone.state == "unavailable":
    hass.states.set(rain_delay_finishing_entity, "Unavailable", rain_delay_finishing_attrs)
else:
    delay_finishes_at = None
    if rain_delay.state == "on":
        started_at = dt_util.as_timestamp(rain_delay.attributes.get("started_at"))
        delay_seconds = rain_delay.attributes.get("delay") * 3600
        delay_finishes_at = dt_util.as_local(dt_util.utc_from_timestamp(started_at + delay_seconds))
        hass.states.set(rain_delay_finishing_entity, delay_finishes_at, rain_delay_finishing_attrs)
    else:
        hass.states.set(rain_delay_finishing_entity, None, rain_delay_finishing_attrs)

