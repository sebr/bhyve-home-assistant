---
name: Support a new device
about: Create a request to support a new BHyve device
title: ''
labels: ''
assignees:
  - sebr

---

**Describe the new device**
<!-- A clear and concise description of the device, including any reference links. -->

**Logs**
<!--
Attach device logs.

Step 1: Enable debugging.

Add the following to `configuration.yaml` and then restart Home Assistant.
```
logger:
  logs:
    custom_components.bhyve: debug
```

Step 2: Check Home Assistant logs

1. Open `home-assistant.log`
2. Identify lines which begin with:
```log
DEBUG (MainThread) [custom_components.bhyve] Devices:
DEBUG (MainThread) [custom_components.bhyve] Programs:
```

Copy these two lines and paste them below.
 -->

```log
DEBUG (MainThread) [custom_components.bhyve] Devices:
DEBUG (MainThread) [custom_components.bhyve] Programs:
```
