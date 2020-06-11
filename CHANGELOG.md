# 0.2.0

## New Features

- Program switches
- Rain delay can now be triggered on/off with a switch (default is 24 hours)
- Services to:
  - Start watering for a specified number of minutes
  - Stop watering
  - Enable rain delay for specified number of hours
  - Disable rain delay

## Breaking Changes

- Rain delay `binary_sensor` entities are now `switch` entities which enables them to be toggled on/off
