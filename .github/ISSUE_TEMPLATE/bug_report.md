---
name: Bug report
about: Create a report to help us improve
title: ''
labels: ''
assignees: ''

---

**Describe the bug**
<!-- A clear and concise description of what the bug is. -->

**Expected behaviour**
<!-- A clear and concise description of what you expected to happen. -->

**BHyve devices**
<!-- Please detail the number and types of devices in your BHyve configuration. -->

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
