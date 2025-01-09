"""Custom types for bhyve."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .coordinator import BHyveUpdateCoordinator
    from .pybhyve import BHyveClient


type BHyveConfigEntry = ConfigEntry[BHyveEntryData]


@dataclass
class BHyveEntryData:
    """Data for the BHyve integration."""

    client: BHyveClient
    coordinator: BHyveUpdateCoordinator
    integration: Integration
