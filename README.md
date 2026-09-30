<!-- markdownlint-disable no-inline-html -->
# bhyve-home-assistant

Orbit B-hyve component for [Home Assistant](https://www.home-assistant.io/).

<!-- If this integration has been useful to you, please consider chipping in and buying me a coffee! -->

<a href="https://www.buymeacoffee.com/sebr" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee"></a>

## Supported Devices

This integration works with:

### Faucet / Tap / Sprinkler controllers

The following controllers have been verified as compatible with this integration, either by the author or members of the community. By virtue that this is an unofficial project which is not supported by the company, there is no guarantee of continued compatibility for current or future devices.

- [Orbit 21004 B-hyve Smart Hose Faucet Timer with Wi-Fi Hub](https://www.amazon.com/dp/B0758NR8DJ). The Wifi hub is required to provide the faucet timer with internet connectivity. Bluetooth connectivity with the timer is not supported.
- [Orbit 57946 B-hyve Smart Indoor/Outdoor 6-Station WiFi Sprinkler System Controller](https://www.amazon.com/gp/product/B01D15HOIQ).
- [Orbit 57925 B-hyve Smart 8-Zone Indoor-Mount Sprinkler Controller](https://www.amazon.com/dp/B07DJ628XH).
- [Orbit 57995 B-hyve XR](https://www.amazon.com/Orbit-57995-16-Zone-Sprinkler-Controller/dp/B08J2C3FL5).
- [Orbit B-hyve XD](https://www.amazon.com/Orbit-24516-B-hyve-Smart-Watering/dp/B09KKFLN1D/) (with the Gen 2 Wifi hub).

_Note_: The Wifi hub is required to provide the faucet controllers with internet connectivity.

### Flood sensors

- [Orbit 71000 B-hyve Smart Flood Sensors with Wi-Fi Hub](https://www.orbitonline.com/product/b-hyve-smart-flood-sensor/).

_Note_: The Wifi hub is required to provide the flood sensors with internet connectivity.

## Supported Entities

- `valve` for opening/closing individual zones on `sprinkler_timer` devices.
- `sensor` for battery levels, zone watering history, device next watering time, device run-mode state, flood-sensor temperature and flood-sensor signal strength.
- `switch` for enabling/disabling rain delays, toggling pre-configured programs and enabling/disabling per-zone smart watering.
- `select` for the device run-mode (auto/off) on `sprinkler_timer` devices.
- `binary_sensor` for flood detection, temperature alerts, sprinkler station faults and Wi-Fi bridge connectivity.

## Installation

Recommended installation is via the [Home Assistant Community Store (HACS)](https://hacs.xyz/). [![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

### 1. Install via HACS

If you do not wish to use HACS, then please download the latest version from the [releases page](https://github.com/sebr/bhyve-home-assistant/releases) and proceed to Step 2.

1. Navigate to the HACS add-on
2. Search for the `Orbit BHyve` integration and install it
3. Restart Home Assistant

<img width="450" alt="Install B-hyve from HACS" src="https://user-images.githubusercontent.com/81972/177079621-a66a8ab3-ceee-44de-b539-4c65ad921640.png">

### 2. Configure via Home Assistant

1. Navigate to Home Assistant Settings > Devices & Services
2. Click `+ Add Integration`
3. Search for `Orbit B-hyve`
4. Complete the guided configuration

<img width="450" alt="Configure B-hyve from Home Assistant" src="https://user-images.githubusercontent.com/81972/177079633-672ef7be-3b20-4350-bc46-9dc6cd9c8e19.png">

### Help

Some common errors in set up include:

- Assuming that installing the integration via HACS is all that is required - it still needs to be configured!
- Not restarting Home Assistant after installing the integraion via HACS

## Sensor Entities

### Device Battery Sensor

A **battery** `sensor` entity is created for any device which has a battery level to report.

### Device State sensor

A **device state** `sensor` entity is created for each `sprinkler_timer` device. This reports the state of the device, for example `auto` or `off`. A device may be switched to `off` either manually through the B-hyve app, or may be automatically set when battery levels are too low to operate the device correctly.

### Zone Watering History sensor

A **zone history** `sensor` entity is created for each zone on a `sprinkler_timer` device. This reports the history of zone watering.

The following attributes are set on zone history sensor entities:

| Attribute             | Type     | Notes                                                       |
| --------------------- | -------- | ----------------------------------------------------------- |
| `budget`              | `number` | The watering budget used.                                   |
| `program`             | `string` | The program letter which triggered the watering event.      |
| `program_name`        | `string` | The name of the program which triggered the watering event. |
| `run_time`            | `number` | The number of minutes the watering was active.              |
| `status`              | `string` | The watering status.                                        |
| `consumption_gallons` | `number` | The amount of water consumed, in gallons.                   |
| `consumption_litres`  | `number` | The amount of water consumed, in litres.                    |
| `start_time`          | `string` | The start time of the watering.                             |

### Device Next Watering sensor

A **next watering** `sensor` entity is created for each `sprinkler_timer` device. This reports the next scheduled watering time as a timestamp, allowing relative-time rendering ("in 14 hours"), long-term statistics, and direct use in automations and dashboard cards.

The existing `next_start_time` valve attribute is preserved for backward compatibility.

The following attributes are set on next watering sensor entities:

| Attribute  | Type           | Notes                                                          |
| ---------- | -------------- | -------------------------------------------------------------- |
| `programs` | `list[string]` | The programs scheduled to run at this time, if any.            |

### Temperature sensor

A **temperature** `sensor` entity is created for each `flood_sensor` device, reporting the ambient temperature in degrees Fahrenheit.

### Signal strength sensor

A **signal strength** `sensor` entity is created for each `flood_sensor` device, reporting the Wi-Fi RSSI in dBm.

## Binary Sensor Entities

### Water/Flood

A **binary_sensor** is created for each `flood_sensor` device. It turns on if water is detected.

### Temperature Alert

A **binary_sensor** is created for each `flood_sensor` device. It turns on if the detected temperature is over or under the set threshold. The threshold values should be set using the BHyve app.

### Fault

A **binary_sensor** is created for each `sprinkler_timer` device. It turns on when B-hyve reports one or more station faults, with the raw fault list exposed via the `station_faults` attribute.

### Connectivity

A **binary_sensor** is created for each Wi-Fi hub / bridge device, reporting whether the bridge is currently online.

## Valve Entities

### Zone Valve

A **zone** `valve` entity is created for each zone of a `sprinkler_timer` device. Opening the valve starts watering the zone for a "default" amount of time; closing it stops watering.

The default run time is often indicated by the `manual_preset_runtime` attribute, and this can be set using the `set_manual_preset_runtime` service or configured in the B-hyve app.

> [!NOTE]
> Some BHyve devices do not have the ability to set the default watering time, and it is recommended that you use the `bhyve.start_watering` service to start the watering zone with the desired number of minutes.

The following attributes are set on zone valve entities:

| Attribute                     | Type           | Notes                                                                      |
| ----------------------------- | -------------- | -------------------------------------------------------------------------- |
| `zone_name`                   | `string`       | The name of the zone                                                       |
| `device_id`                   | `string`       | The id of the device which this zone belongs to                            |
| `device_name`                 | `string`       | The name of the device which this zone belongs to                          |
| `station`                     | `number`       | The station number of the zone on the device.                              |
| `manual_preset_runtime`       | `number`       | The number of seconds to run zone watering when the valve is opened.       |
| `smart_watering_enabled`      | `boolean`      | True if the zone has a smart water schedule enabled.                       |
| `sprinkler_type`              | `string`       | The configured type of sprinkler.                                          |
| `image_url`                   | `string`       | The url to zone image.                                                     |
| `started_watering_station_at` | `string`       | The timestamp the zone started watering.                                   |
| `next_start_time`             | `string`       | ISO-8601 timestamp of the next scheduled watering, if any.                 |
| `next_start_programs`         | `list[string]` | The programs scheduled to run at `next_start_time`.                        |
| `program_x`                   | `object`       | Provides details on any configured watering programs for the given zone.   |
| `program_e[watering_program]` | `list[string]` | List of timestamps for future/scheduled watering times.<sup>†</sup>        |

<sup>†</sup> Only applicable if a Smart Watering program is enabled. Any rain delays or other custom programs must be considered separately.

#### `program_x` attribute

Any watering programs which are configured for a zone are made available as an attribute. The `x` denotes the (lowercase) letter of the program slot. Values `a`, `b` and `c` are well-known custom slots. Program `e` is reserved for the Smart Watering plan. Slot `d` does not have a known use at this stage.

Please see [program switches](#program-switch) below for more details.

## Switch Entities

### Rain Delay Switch

A **rain delay** `switch` entity is created for each discovered `sprinkler_timer` device. This entity will be **on** whenever B-hyve reports that a device's watering schedule will be delayed due to weather conditions.

Enabling the switch will set a 24 hour rain delay on the device &mdash; for a custom rain delay, please use the `enable_rain_delay` service.

The following attributes are set on `switch.*_rain_delay` entities, if the sensor is on:

| Attribute      | Type     | Notes                                                                                     |
| -------------- | -------- | ----------------------------------------------------------------------------------------- |
| `cause`        | `string` | Why a delay was put in place. Values seen: `auto`. May be empty.                          |
| `delay`        | `number` | The number of hours the delay is in place. NB: This is hours from `started_at` attribute. |
| `weather_type` | `string` | The reported cause of the weather delay. Values seen: `wind`, `rain`. May be empty.       |
| `started_at`   | `string` | The timestamp the delay was put in place.                                                 |

### Program Switch

A **program** `switch` entity is created for each program attached to each zone. These switches can be switched on or off. They can be configured using the official B-hyve app.

| Attribute              | Type           | Notes                                                             |
| ---------------------- | -------------- | ----------------------------------------------------------------- |
| `device_id`            | `string`       | The id of the device which this zone belongs to.                  |
| `is_smart_program`     | `boolean`      | True if this is a _Smart Watering_ program.                       |
| `start_times`          | `string`       | Configured start time for the program.<sup>†</sup>                |
| `frequency`            | `object`       | Watering schedule configuration.<sup>†</sup>                      |
| `frequency.type`       | `string`       | Type of schedule. Known values: `days`, `interval`.               |
| `frequency.days`       | `list[int]`    | Configured days for watering (when `type` is `days`). `0` is Sunday, `1` is Monday etc... |
| `frequency.interval`   | `int`          | Number of days between watering (when `type` is `interval`).      |
| `budget`               | `int`          | Watering budget as a percentage. Scales each zone's run time.<sup>†</sup> |
| `run_times`            | `list[object]` | Configured watering run times.<sup>†</sup>                        |
| `run_times[].run_time` | `int`          | Minutes of watering.                                              |
| `run_times[].station`  | `int`          | Zone id to water.                                                 |

<sup>†</sup> Not available on _Smart Watering_ programs

### Smart Watering Switch

A **smart watering** `switch` entity is created for each zone that has smart watering as an available feature. Toggling the switch enables or disables the Smart Watering schedule for that zone.

## Select Entities

### Device Mode

A **device mode** `select` entity is created for each `sprinkler_timer` device, with options `auto` and `off`. This mirrors the device-level run mode exposed by the B-hyve app.

## Services

This integration provides the following services:

| Service                           | Parameters                                                                                                                                                  | Description                                                      |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `bhyve.start_watering`            | `entity_id` - zone(s) entity to start watering. This should be a reference to a zone valve entity <br/> `minutes` - number of minutes to water for         | Start watering a zone for a specific number of minutes           |
| `bhyve.stop_watering`             | `entity_id` - zone(s) entity to stop watering. This should be a reference to a zone valve entity                                                           | Stop watering a zone                                             |
| `bhyve.enable_rain_delay`         | `entity_id` - device to enable a rain delay. This can reference either a zone valve or rain delay switch <br/> `hours` - number of hours to enable a rain delay   | Enable a rain delay for a device for a specified number of hours |
| `bhyve.disable_rain_delay`        | `entity_id` - device to disable a rain delay. This can reference either a zone valve or rain delay switch                                                          | Cancel a rain delay on a given device                            |
| `bhyve.set_manual_preset_runtime` | `entity_id` - zone(s) entity to set the preset runtime. This should be a reference to a zone valve entity <br/> `minutes` - number of minutes to water for | Set the default time a zone is watered for when the valve is opened. Support for this service appears to be patchy, and it has been difficult to identify the devices or under which conditions it works      |
| `bhyve.set_smart_watering_soil_moisture` | `entity_id` - zone(s) entity to set the moisture level for. This should be a reference to a zone valve entity <br/> `percentage` - soil moisture level between 0 - 100 | Set Smart Watering soil moisture level for a zone     |
| `bhyve.start_program` | `entity_id` - program entity to start. This should be a reference to a program switch entity | Starts a pre-configured watering program. Watering programs cannot be created via this integration and must first be set up in the B-Hyve app |
| `bhyve.update_program` | `entity_id` - program switch to update <br/> `start_times` - _(optional)_ list of watering start times in `HH:MM` format <br/> `frequency` - _(optional)_ frequency configuration object (must include a `type`, known values: `days`, `interval`) <br/> `budget` - _(optional)_ watering budget as a percentage (0-200) | Update the configuration of an existing non-smart program. At least one of `start_times`, `frequency` or `budget` must be provided |

### `bhyve.update_program` example

```yaml
service: bhyve.update_program
data:
  entity_id: switch.front_yard_usual_programming_program
  start_times:
    - "06:00"
    - "18:30"
  frequency:
    type: days
    days: [1, 3, 5]
    interval: 1
    interval_hours: 0
  budget: 75
```

The `frequency` object mirrors the B-Hyve API structure. Known `type` values:

- `days` with `days: [0-6]` (where `0` is Sunday, `1` is Monday etc.) to water on specific weekdays
- `interval` with `interval: N` to water every N days

The `budget` is a percentage that scales each zone's run time. `100` means unchanged, `50` halves every run time, `200` doubles it. Valid range is 0&ndash;200.

