"""Test BHyve coordinator."""

from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.core import Event, HomeAssistant

from custom_components.bhyve.coordinator import BHyveDataUpdateCoordinator

TEST_DEVICE_ID = "test-device-123"
TEST_PROGRAM_ID = "test-program-456"


def create_mock_coordinator(hass: HomeAssistant) -> BHyveDataUpdateCoordinator:
    """Create a mock coordinator for testing."""
    client = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    coordinator = BHyveDataUpdateCoordinator(hass, client, entry)
    coordinator.data = {
        "devices": {
            TEST_DEVICE_ID: {
                "device": {"id": TEST_DEVICE_ID, "name": "Test Device"},
                "history": [],
                "landscapes": {},
            }
        },
        "programs": {
            TEST_PROGRAM_ID: {
                "id": TEST_PROGRAM_ID,
                "device_id": TEST_DEVICE_ID,
                "name": "Existing Program",
                "enabled": True,
            }
        },
    }
    return coordinator


class TestProgramEventHandling:
    """Test program event handling in coordinator."""

    async def test_handle_program_create_event(self, hass: HomeAssistant) -> None:
        """Test handling lifecycle_phase: create adds program to data."""
        coordinator = create_mock_coordinator(hass)

        # Track bus events
        fired_events: list[dict[str, Any]] = []

        def track_event(event: Event) -> None:
            fired_events.append({"type": event.event_type, "data": event.data})

        hass.bus.async_listen("bhyve_program_created", track_event)

        new_program_id = "new-program-789"
        event_data = {
            "event": "program_changed",
            "device_id": TEST_DEVICE_ID,
            "lifecycle_phase": "create",
            "program": {
                "id": new_program_id,
                "device_id": TEST_DEVICE_ID,
                "name": "New Program",
                "enabled": True,
                "program": "b",
            },
        }

        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator.async_handle_program_event(event_data)

        # Verify program was added to coordinator data
        assert new_program_id in coordinator.data["programs"]
        assert coordinator.data["programs"][new_program_id]["name"] == "New Program"

        # Wait for events to process
        await hass.async_block_till_done()

        # Verify event was fired
        assert len(fired_events) == 1
        assert fired_events[0]["type"] == "bhyve_program_created"
        assert fired_events[0]["data"]["program_id"] == new_program_id

    async def test_handle_program_delete_event(self, hass: HomeAssistant) -> None:
        """Test handling lifecycle_phase: delete removes program from data."""
        coordinator = create_mock_coordinator(hass)

        # Track bus events
        fired_events: list[dict[str, Any]] = []

        def track_event(event: Event) -> None:
            fired_events.append({"type": event.event_type, "data": event.data})

        hass.bus.async_listen("bhyve_program_deleted", track_event)

        # Verify program exists before deletion
        assert TEST_PROGRAM_ID in coordinator.data["programs"]

        event_data = {
            "event": "program_changed",
            "device_id": TEST_DEVICE_ID,
            "lifecycle_phase": "delete",
            "program": {"id": TEST_PROGRAM_ID},
        }

        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator.async_handle_program_event(event_data)

        # Verify program was removed
        assert TEST_PROGRAM_ID not in coordinator.data["programs"]

        # Wait for events to process
        await hass.async_block_till_done()

        # Verify event was fired
        assert len(fired_events) == 1
        assert fired_events[0]["type"] == "bhyve_program_deleted"
        assert fired_events[0]["data"]["program_id"] == TEST_PROGRAM_ID

    async def test_handle_program_update_event(self, hass: HomeAssistant) -> None:
        """Test handling program update event (no lifecycle_phase)."""
        coordinator = create_mock_coordinator(hass)

        event_data = {
            "event": "program_changed",
            "device_id": TEST_DEVICE_ID,
            "program": {
                "id": TEST_PROGRAM_ID,
                "name": "Updated Program Name",
                "enabled": False,
            },
        }

        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator.async_handle_program_event(event_data)

        # Verify program was updated
        assert (
            coordinator.data["programs"][TEST_PROGRAM_ID]["name"]
            == "Updated Program Name"
        )
        assert coordinator.data["programs"][TEST_PROGRAM_ID]["enabled"] is False

    async def test_handle_program_event_no_program_id(
        self, hass: HomeAssistant
    ) -> None:
        """Test handling event with no program_id is ignored."""
        coordinator = create_mock_coordinator(hass)
        original_programs = dict(coordinator.data["programs"])

        event_data = {
            "event": "program_changed",
            "device_id": TEST_DEVICE_ID,
            # Missing program_id and program.id
        }

        with patch.object(coordinator, "async_set_updated_data") as mock_update:
            await coordinator.async_handle_program_event(event_data)

        # Verify nothing changed
        assert coordinator.data["programs"] == original_programs
        mock_update.assert_not_called()

    async def test_handle_program_event_no_data(self, hass: HomeAssistant) -> None:
        """Test handling event when coordinator data is not initialized."""
        coordinator = create_mock_coordinator(hass)
        coordinator.data = None

        event_data = {
            "event": "program_changed",
            "lifecycle_phase": "create",
            "program": {"id": "some-program"},
        }

        # Should not raise an exception
        await coordinator.async_handle_program_event(event_data)

    async def test_handle_program_update_unknown_program(
        self, hass: HomeAssistant
    ) -> None:
        """Test that update event for unknown program is ignored."""
        coordinator = create_mock_coordinator(hass)

        event_data = {
            "event": "program_changed",
            "device_id": TEST_DEVICE_ID,
            "program": {
                "id": "unknown-program-id",
                "name": "Unknown Program",
            },
        }

        with patch.object(coordinator, "async_set_updated_data") as mock_update:
            await coordinator.async_handle_program_event(event_data)

        # Verify no changes and no update triggered
        assert "unknown-program-id" not in coordinator.data["programs"]
        mock_update.assert_not_called()
