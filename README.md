# bhyve-home-assistant

BHyve component for [Home Assistant](https://www.home-assistant.io/).

## Supported Features
* Battery sensor for `sprinkler_timer` devices
* Rain delay binary_sensor

## Installation

Recommended installation is via HACS - add this repo to [custom repositories](https://hacs.xyz/docs/navigation/settings#custom-repositories).

## Configuration

```yaml
bhyve:
  username: !secret bhyve_username
  password: !secret bhyve_password

sensor:
  - platform: bhyve

binary_sensor:
  - platform: bhyve
```

