# bhyve-home-assistant

BHyve component for [Home Assistant](https://www.home-assistant.io/).

## Supported Features
* Battery sensor for `sprinkler_timer` devices
* Rain delay binary_sensor

## Installation

Recommended installation is via HACS
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

### Sample Configuration

```yaml
bhyve:
  username: !secret bhyve_username
  password: !secret bhyve_password

sensor:
  - platform: bhyve

binary_sensor:
  - platform: bhyve
```

