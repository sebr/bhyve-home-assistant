# bhyve-home-assistant

BHyve component for [Home Assistant](https://www.home-assistant.io/).

## Supported Entities
* `sensor` for measuring battery levels of `sprinkler_timer` devices
* `binary_sensor` for tracking rain/weather delays
* `switch` for turning a zone on/off

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
