<!-- markdownlint-disable no-inline-html -->
# bhyve-home-assistant

Orbit B-hyve component for [Home Assistant](https://www.home-assistant.io/).

If this integration has been useful to you, please consider chipping in and buying me a coffee!

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

- `sensor` for measuring battery levels and watering history of `sprinkler_timer` devices as well as the device on/off state (not to be confused with zone on/off switches).
- `temperature sensor` for measuring the temperature at the device.
- `switch` for turning a zone on/off, enabling/disabling rain delays and toggling pre-configured programs.
- `binary_sensor` for `flood_sensor` devices which provide liquid detection and temperature alerts when out of threshold.

## Installation

Recommended installation is via the [Home Assistant Community Store (HACS)](https://hacs.xyz/). [![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

### 1. Install via HACS

If you do not wish to use HACS, then please download the latest version from the [releases page](https://github.com/sebr/bhyve-home-assistant/releases) and proceed to Step 2.

1. Navigate to the HACS add-on
2. Search for the `Orbit B-hyve` integration and install it
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

A **device state** `sensor` entity is created for each device. This reports the state of the device, for example `auto` or `off`. A device may be switched to `off` either manually through the B-hyve app, or may be automatically set when battery levels are too low to operate the device correctly.

### Zone Watering History sensor

A **zone history** `sensor` entity is created for each zone. This reports the history of zone watering.

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

## Binary Sensor Entities

The BHyve flood sensor provides the following `binary_sensor` entities:

### Water/Flood

A **binary_sensor** that turns on if water is detected.

### Temperature Alert

A **binary_sensor** that turns on if the detected temperature is over or under the set threshold. The threshold values should be set using the BHyve app.

## Switch Entities

### Zone Switch

A **zone** `switch` entity is created for each zone of a `sprinkler_timer` device. This switch enables starting/stopping irrigation of a zone. Turning on the switch will enable watering of the zone for a "default" amount of time.

This default is often indicated by the `manual_preset_runtime` attribute, and this can be set using the `set_manual_preset_runtime` service or configured in the B-hyve app.

> [!NOTE]  
> Some BHyve devices do not have the ability to set the default watering time, and it is recommended that you use the `bhyve.start_watering` service to start the watering zone with the desired number of minutes.

The following attributes are set on zone switch entities:

| Attribute                     | Type           | Notes                                                                      |
| ----------------------------- | -------------- | -------------------------------------------------------------------------- |
| `zone_name`                   | `string`       | The name of the zone                                                       |
| `device_id`                   | `string`       | The id of the device which this zone belongs to                            |
| `device_name`                 | `string`       | The name of the device which this zone belongs to                          |
| `manual_preset_runtime`       | `number`       | The number of seconds to run zone watering when switch is turned on.       |
| `smart_watering_enabled`      | `boolean`      | True if the zone has a smart water schedule enabled.                       |
| `sprinkler_type`              | `string`       | The configured type of sprinker.                                           |
| `image_url`                   | `string`       | The url to zone image.                                                     |
| `started_watering_station_at` | `string`       | The timestamp the zone started watering.                                   |
| `program_x`                   | `object`       | Provides details on any configured watering programs for the given switch. |
| `program_e[watering_program]` | `list[string]` | List of timestamps for future/scheduled watering times.<sup>†</sup>        |

<sup>†</sup> Only applicable if a Smart Watering program is enabled. Any rain delays or other custom programs must be considered separately.

#### `program_x` attribute

Any watering programs which are configured for a zone switch are made available as an attribute. The `X` denotes the letter of the program slot. Values `A`, `B` and `C` are well known custom slots. Program `E` is reserved for the Smart Watering plan. Slot `D` does not have a known use at this stage.

Please see [program switches](#program-switch) below for more details.

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
| `frequency.type`       | `string`       | Type of configuration. `days` is the only known value.            |
| `frequency.days`       | `list[int]`    | Configured days for watering. `0` is Sunday, `1` is Monday etc... |
| `run_times`            | `list[object]` | Configured watering run times.<sup>†</sup>                        |
| `run_times[].run_time` | `int`          | Minutes of watering.                                              |
| `run_times[].station`  | `int`          | Zone id to water.                                                 |

<sup>†</sup> Not available on _Smart Watering_ programs

## Services

This integration provides the following services:

| Service                           | Parameters                                                                                                                                                  | Description                                                      |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `bhyve.start_watering`            | `entity_id` - zone(s) entity to start watering. This should be a reference to a zone switch entity <br/> `minutes` - number of minutes to water for         | Start watering a zone for a specific number of minutes           |
| `bhyve.stop_watering`             | `entity_id` - zone(s) entity to stop watering. This should be a reference to a zone switch entity                                                           | Stop watering a zone                                             |
| `bhyve.enable_rain_delay`         | `entity_id` - device to enable a rain delay. This can reference either a zone or rain delay switch <br/> `hours` - number of hours to enable a rain delay   | Enable a rain delay for a device for a specified number of hours |
| `bhyve.disable_rain_delay`        | `entity_id` - device to enable a rain delay. This can reference either a zone or rain delay switch                                                          | Cancel a rain delay on a given device                            |
| `bhyve.set_manual_preset_runtime` | `entity_id` - zone(s) entity to set the preset runtime. This should be a reference to a zone switch entity <br/> `minutes` - number of minutes to water for | Set the default time a switch is activated for when enabled. Support for this service appears to be patchy, and it has been difficult to identify the devices or under which conditions it works      |
| `bhyve.set_smart_watering_soil_moisture` | `entity_id` - zone(s) entity to set the moisture level for. This should be a reference to a zone switch entity <br/> `percentage` - soil moisture level between 0 - 100 | Set Smart Watering soil moisture level for a zone     |
| `bhyve.start_program` | `entity_id` - program entity to start. This should be a reference to a program switch entity | Starts a pre-configured watering program. Watering programs cannot be created nor configured via this integration, and require the B-Hyve app to create or modify |

## Python Script

> [!CAUTION]
> These scripts are expermintal and not supported. YMMV and any support issues will be closed as won't fix.

Bundled in this repository is a [`python_script`](https://www.home-assistant.io/integrations/python_script) which calculates a device's next watering time and when a rain delay is scheduled to finish.

_Note: HACS does not install the script automatically and they must be added manually to your HA instance._

### Scripts

#### [`bhyve_next_watering.py`](https://github.com/sebr/bhyve-home-assistant/blob/master/python_scripts/bhyve_next_watering.py)

Calculates:

1. When the next scheduled watering is for a zone by considering all enabled watering programs
2. When a device's active rain delay will finish, or `None` if there is no active delay

This script creates or updates entities named `sensor.{zone_name}_next_watering` and `sensor.{device_name}_rain_delay_finishing`.

Usage:

```yaml
service: python_script.bhyve_next_watering
data:
  entity_id: switch.backyard_zone
```

| Argument    | Type     | Required | Notes                            |
| ----------- | -------- | -------- | -------------------------------- |
| `entity_id` | `string` | `True`   | The entity id for a zone switch. |

### Automation

Hook these scripts up to automations to update as required:

```yaml
automation:
  - alias: B-hyve next watering & rain delay finishing updater
    trigger:
      - platform: state
        entity_id: switch.backyard_zone, switch.rain_delay_lawn
      - platform: homeassistant
        event: start
    action:
      - service: python_script.bhyve_next_watering
        data:
          entity_id: switch.backyard_zone
```

## Debugging

To debug this integration and provide device integration for future improvements, please enable debugging in Home Assistant's `configuration.yaml`

```yaml
logger:
  logs:
    custom_components.bhyve: debug
    pybhyve: debug
```
