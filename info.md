# bhyve-home-assistant

BHyve component for [Home Assistant](https://www.home-assistant.io/).

## Supported Features
* Battery sensor for `sprinkler_timer` devices

## Configuration

```yaml
bhyve:
  username: !secret bhyve_username
  password: !secret bhyve_password

sensor:
  - platform: bhyve
```

