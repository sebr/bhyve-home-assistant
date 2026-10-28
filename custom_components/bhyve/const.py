"""Define constants for the BHyve component."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "bhyve"
MANUFACTURER = "Orbit BHyve"

CONF_CLIENT = "client"
CONF_DEVICES = "devices"
# Add devices that are new to the B-hyve account without asking again.
CONF_AUTO_ADD = "auto_add_devices"
# Every device id the device picker has offered (selected or not), so a
# device the user turned off is never auto-added back.
CONF_KNOWN_DEVICES = "known_devices"

# Marks a status next_start_time this integration computed from the timer's
# programs because Orbit didn't report one (Gen 2 / Bluetooth hose timers).
NEXT_START_COMPUTED = "next_start_time_computed"
# Why a computed next start is missing: timer_off, not_computable (a smart
# program or a frequency the code doesn't know), no_upcoming_run.
NEXT_START_MISSING = "next_start_time_missing"

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
