# bhyve-home-assistant

Orbit BHyve component for [Home Assistant](https://www.home-assistant.io/).

If this integration has been useful to you, please consider chipping in and buying me a coffee!

<a href="https://www.buymeacoffee.com/sebr" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee"></a>

## Supported Entities
* `sensor` for measuring battery levels of `sprinkler_timer` devices
* `binary_sensor` for tracking rain/weather delays
* `switch` for turning a zone on/off


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

Sensor entities are automatically created for any device which has a battery level to report.

## Binary Sensor Entities

A **Rain Delay** binary sensor will be created for each discovered `sprinkler_timer` device. This entity will be **on** whenever BHyve reports that a device's watering schedule will be delayed due to weather conditions.

### Rain Delay Attributes

The following attributes are set on `binary_sensor.rain_delay_*` entities, if the sensor is on:

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
        value_template: "{{(as_timestamp(state_attr('binary_sensor.rain_delay_lawn', 'started_at')) + state_attr('binary_sensor.rain_delay_lawn', 'delay') * 3600) | timestamp_local }}"

      rain_delay_lawn_remaining:
        friendly_name: "Rain Delay Lawn Remaining"
        unit_of_measurement: 'h'
        value_template: "{{((as_timestamp(state_attr('binary_sensor.rain_delay_lawn', 'started_at')) + state_attr('binary_sensor.rain_delay_lawn', 'delay') * 3600 - as_timestamp(now())) / 3600) | round(0) }}"
```

