# 1.1.0

## New Features

- Sensor entities for zone history, including water consumption stats

# 1.0.0

## New Features

- Program switches
- Rain delay can now be triggered on/off with a switch (default is 24 hours)
- Services to:
  - Start watering for a specified number of minutes
  - Stop watering
  - Enable rain delay for specified number of hours
  - Disable rain delay
  - Set the manual watering preset runtime for a device

## Breaking Changes

- Rain delay `binary_sensor` entities are now `switch` entities which enables them to be toggled on/off. This integration no longer provides the `binary_sensor` platform and it should be removed from configuration
- Battery level `sensor` entities are renamed to be consistent with other entities (from `sensor.battery_level_{}` to `sensor.{}_battery_level`)
- Switch `watering_program` attribute has been moved to be a property the Smart Watering program attribute (`program_e.watering_program`) as this was not relevant to regular programs
