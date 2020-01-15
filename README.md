# bhyve-home-assistant

BHyve component for [Home Assistant](https://www.home-assistant.io/).

If this integration has been useful to you, please consider chipping in and buying me a coffee!

<a href="https://www.buymeacoffee.com/sebr" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

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

