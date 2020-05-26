now = dt_util.now()

zone_entity_id = data.get("entity_id")

zone = hass.states.get(zone_entity_id)

device_name = zone.attributes["device_name"]

logger.info("updating next_watering for zone: ({}: {})".format(device_name, zone))

next_watering_entity = f"sensor.next_watering_{device_name}"
next_watering_attrs = {
    "friendly_name": f"{device_name} next watering"
}

if zone.state == "unavailable":
    hass.states.set(next_watering_entity, "Unavailable", next_watering_attrs)
else:
    next_watering = None

    for timestamp in (zone.attributes.get('watering_program', []) or []):
        watering_time = dt_util.parse_datetime(str(timestamp))
        if watering_time > now and (delay_finishes_at is None or watering_time > delay_finishes_at):
            next_watering = watering_time
            break

    hass.states.set(next_watering_entity, next_watering, next_watering_attrs)
