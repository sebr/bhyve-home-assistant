"""Classes for Orbit devices."""

from dataclasses import dataclass
from typing import Any, TypedDict


@dataclass
class BHyveDevice(TypedDict):
    """Orbit Device Class."""

    id: str
    name: str
    type: str


@dataclass
class BHyveTimerProgram(dict):
    """Orbit Timer Program Class."""


@dataclass
class BHyveZone(dict):
    """Orbit Zone Class."""


@dataclass
class BHyveZoneLandscape(dict):
    """Orbit Zone Landscape Class."""


@dataclass
class BHyveApiData:
    """Data for the BHyve API."""

    devices: list[BHyveDevice]
    programs: list[BHyveTimerProgram]
    histories: dict[str, Any]
    landscapes: list[BHyveZoneLandscape]

    def get_device(self, device_id: str) -> BHyveDevice | None:
        """Get device by id."""
        return next((d for d in self.devices if d.get("id") == device_id), None)

    def get_history(self, device_id: str) -> dict | None:
        """Get device watering history by id."""
        return self.histories.get(device_id)
