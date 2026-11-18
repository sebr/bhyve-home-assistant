"""Define constants for the BHyve component."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "bhyve"
MANUFACTURER = "Orbit BHyve"

CONF_CLIENT = "client"
CONF_DEVICES = "devices"
# Add devices that are new to the B-hyve account without asking again.
CONF_AUTO_ADD = "auto_add_devices"
# Every device id the user has been offered (selected or not), so a device
# they deselected is never auto-added back. An entry from before auto-add
# records the devices on the account at its first setup.
CONF_KNOWN_DEVICES = "known_devices"

# Dispatcher signal (formatted with the entry id) carrying devices newly
# added to the entry, for each platform to add their entities.
SIGNAL_NEW_DEVICES = "bhyve_new_devices_{}"

DEVICE_BRIDGE = "bridge"
DEVICE_SPRINKLER = "sprinkler_timer"
DEVICE_FLOOD = "flood_sensor"

MODE_AUTO = "auto"
MODE_OFF = "off"
MODE_MANUAL = "manual"

EVENT_BATTERY_STATUS = "battery_status"
EVENT_FAULT = "fault"
EVENT_CHANGE_MODE = "change_mode"
EVENT_DEVICE_IDLE = "device_idle"
EVENT_FS_ALARM = "fs_status_update"
EVENT_PROGRAM_CHANGED = "program_changed"
EVENT_RAIN_DELAY = "rain_delay"
EVENT_SET_MANUAL_PRESET_TIME = "set_manual_preset_runtime"
EVENT_WATERING_COMPLETE = "watering_complete"
EVENT_WATERING_IN_PROGRESS = "watering_in_progress_notification"
