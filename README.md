# bhyve-home-assistant

Orbit BHyve component for [Home Assistant](https://www.home-assistant.io/).

If this integration has been useful to you, please consider chipping in and buying me a coffee!

<a href="https://www.buymeacoffee.com/sebr" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee"></a>

## Supported Entities

- `sensor` for measuring battery levels of `sprinkler_timer` devices as well as the device on/off state (not to be confused with zone on/off switches)
- `binary_sensor` for tracking rain/weather delays
- `switch` for turning a zone on/off

## Python Script

-

## Installation

Recommended installation is via HACS.

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

## Configuration

```yaml
bhyve:
  username: !secret bhyve_username
  password: !secret bhyve_password

sensor:
  - platform: bhyve

binary_sensor:
  - platform: bhyve

switch:
  - platform: bhyve
```

## Sensor Entities

A **battery** `sensor` entity is created for any device which has a battery level to report.

A **zone state** `sensor` entity is created for each zone. This reports the state of the zone, for example `auto` or `off`. A zone may be switched to `off` either manually through the BHyve app, or may be automatically set when battery levels are too low to operate the device correctly.

## Binary Sensor Entities

A **Rain Delay** `binary sensor` will be created for each discovered `sprinkler_timer` device. This entity will be **on** whenever BHyve reports that a device's watering schedule will be delayed due to weather conditions.

### Rain Delay Attributes

The following attributes are set on `binary_sensor.*_rain_delay` entities, if the sensor is on:

| Attribute      | Type     | Notes                                                                                     |
| -------------- | -------- | ----------------------------------------------------------------------------------------- |
| `cause`        | `string` | Why a delay was put in place. Values seen: `auto`. May be empty.                          |
| `delay`        | `number` | The number of hours the delay is in place. NB: This is hours from `started_at` attribute. |
| `weather_type` | `string` | The reported cause of the weather delay. Values seen: `wind`, `rain`. May be empty.       |
| `started_at`   | `string` | The timestamp the delay was put in place.                                                 |

### Rain Delay Template Sensors

It is possible to create template sensors from these attributes. Here are two examples which provide a sensor to report:

1. When the current rain delay for a device is ending
2. The number of hours remaining on the current rain delay

```yaml
sensor:
  - platform: template
    sensors:
      rain_delay_lawn_finishing:
        friendly_name: "Rain Delay Lawn Finishing"
        availability_template: "{{ states('binary_sensor.rain_delay_lawn') != 'unavailable' }}"
        value_template: "{{(as_timestamp(state_attr('binary_sensor.rain_delay_lawn', 'started_at')) + state_attr('binary_sensor.rain_delay_lawn', 'delay') * 3600) | timestamp_local }}"

      rain_delay_lawn_remaining:
        friendly_name: "Rain Delay Lawn Remaining"
        unit_of_measurement: "h"
        availability_template: "{{ states('binary_sensor.rain_delay_lawn') != 'unavailable' }}"
        value_template: "{{((as_timestamp(state_attr('binary_sensor.rain_delay_lawn', 'started_at')) + state_attr('binary_sensor.rain_delay_lawn', 'delay') * 3600 - as_timestamp(now())) / 3600) | round(0) }}"
```

## Switch Entities

A `switch` entity is created for each zones of a `sprinkler_timer` device. This switch enables starting/stopping irrigation of a zone.

Turning on the switch will enable watering of the zone for the amount of time configured in the BHyve app.

### Switch Attributes

The following attributes are set on `switch` entities:

| Attribute                     | Type           | Notes                                                                                             |
| ----------------------------- | -------------- | ------------------------------------------------------------------------------------------------- |
| `manual_preset_runtime`       | `number`       | The number of seconds to run zone watering when switch is turned on.                              |
| `smart_watering_enabled`      | `boolean`      | True if the zone has a smart water schedule enabled.                                              |
| `sprinkler_type`              | `string`       | The configured type of sprinker.                                                                  |
| `image_url`                   | `string`       | The url to zone image.                                                                            |
| `started_watering_station_at` | `string`       | The timestamp the zone started watering.                                                          |
| `watering_program`            | `list[string]` | List of timestamps for future/scheduled watering times.<sup>†</sup>                               |
| `program_x`                   | `Object`       | Provides details on any configured watering programs for the given switch. See below for details. |

<sup>†</sup> Only applicable if a Smart Watering program is enabled. Any rain delays or other custom programs must be considered separately.

#### `program_x` attribute

Any watering programs which are configured for a zone switch are made available as an attribute. The `X` denotes the letter of the program slot. Values `A`, `B` and `C` are well known custom slots. Program `E` is reserved for the Smart Watering plan. Slot `D` does not have a known use at this stage.

```json
{
  "enabled": true,
  "name": "Backyard",
  "is_smart_program": false,
  "start_times": ["07:30"],
  "frequency": {
    "type": "days",
    "days": [1, 4]
  },
  "run_times": [
    {
      "run_time": 20,
      "station": 1
    }
  ]
}
```

- `start_times`, `frequency` and `run_time` are not present on `program_e` (Smart Watering program)
- `frequency` days: `0` is Sunday, `1` is Monday etc...
- `run_time` is in minutes

### Switch Template Sensors

It's possible to create a sensor to extract the next watering time, for example:

```yaml
sensor:
  - platform: template
    sensors:
      lawn_next_watering:
        friendly_name: "Next watering"
        availability_template: "{{ states('switch.backyard_zone') != 'unavailable' }}"
        value_template: >-
          {% set program = state_attr('switch.backyard_zone', 'watering_program') -%}
          {% if program and (program | count > 0) %}
            {{ as_timestamp(program[0]) | timestamp_local }}
          {% else %}
            unknown
          {% endif %}
```

# Debugging

To debug this integration and provide device integration for future improvements, please enable debugging in Home Assistant's `configuration.yaml`

```yaml
logger:
  logs:
    custom_components.bhyve: debug

bhyve:
  username: !secret bhyve_username
  password: !secret bhyve_password
  packet_dump: true # Save all websocket event data to a file
  conf_dir: "" # Storage directory for packet dump file. Usually not needed, defaults to hass_config_dir/.bhyve
```
