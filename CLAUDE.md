# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for Orbit B-hyve irrigation devices. It provides support for smart sprinkler controllers, flood sensors, and faucet timers through the B-hyve cloud service.

## Development Commands

### Setup
- `./scripts/setup` - Install dependencies and Claude Code
- `pip install -r requirements.txt` - Install Python dependencies

### Development
- `./scripts/develop` - Run Home Assistant in development mode with this integration loaded
- `./scripts/lint` - Format and lint code using ruff

### Testing
- `./scripts/test` - Run all tests with verbose output
- `pytest tests/` - Run tests directly
- `pytest tests/test_valve.py` - Run specific test file
- Testing setup uses `pytest-homeassistant-custom-component`

### Code Quality
- `ruff format .` - Format Python code
- `ruff check . --fix` - Lint and auto-fix issues
- Code formatting follows Black style with pylint integration

## Architecture

### Core Structure
- `custom_components/bhyve/` - Main integration directory
- `custom_components/bhyve/__init__.py` - Integration setup and coordinator
- `custom_components/bhyve/pybhyve/` - B-hyve API client library
- `config/` - Home Assistant configuration for development
- `python_scripts/` - Experimental utility scripts for calculating watering schedules

### Key Components
- **API Client**: `pybhyve/client.py` - Handles authentication and API communication
- **WebSocket**: `pybhyve/websocket.py` - Real-time device updates
- **Platforms**: 
  - `sensor.py` - Battery levels, device state, watering history
  - `switch.py` - Zone controls, rain delays, programs
  - `binary_sensor.py` - Flood detection, temperature alerts
  - `valve.py` - Valve entity implementation
- **Config Flow**: `config_flow.py` - Integration setup UI
- **Services**: Custom services for advanced watering control

### Device Types
The integration supports multiple B-hyve device types:
- **Sprinkler Timers**: Multi-zone controllers with scheduling
- **Faucet Timers**: Single-zone hose faucet controllers  
- **Flood Sensors**: Water detection and temperature monitoring

### Entity Architecture
- Each device creates multiple entities across different platforms
- Zone switches control individual watering zones
- Program switches manage pre-configured watering schedules
- Sensors track battery, device state, and watering history
- Rain delay switches manage weather-based watering postponement

### Configuration
- Uses Home Assistant config flow for setup
- Stores credentials securely in config entries
- No YAML configuration required (legacy YAML support deprecated)
- Integration type: "hub" with "cloud_push" IoT class

### Development Environment
- Uses VS Code dev containers (`.devcontainer.json`)
- Custom PYTHONPATH setup to load integration from source
- Home Assistant runs in debug mode during development
- Configuration stored in `config/` directory

## Important Notes

- This integration communicates with Orbit's cloud service, not local devices
- WiFi hub required for faucet timers and flood sensors
- Integration follows Home Assistant custom component standards
- Version managed in `manifest.json`
- HACS compatible with automatic updates