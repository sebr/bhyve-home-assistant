"""Base entity classes."""

import logging

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.bhyve.coordinator import BHyveUpdateCoordinator
from custom_components.bhyve.pybhyve.typings import BHyveDevice

from .const import (
    ATTRIBUTION,
    DOMAIN,
    EVENT_RAIN_DELAY,
    EVENT_SET_MANUAL_PRESET_TIME,
    MANUFACTURER,
)
from .pybhyve.errors import BHyveError

_LOGGER = logging.getLogger(__name__)


class BHyveDeviceEntity(CoordinatorEntity[BHyveUpdateCoordinator]):
    """Define a base BHyve entity with a device."""

    def __init__(
        self,
        coordinator: BHyveUpdateCoordinator,
        entity_description: EntityDescription,
        device: BHyveDevice,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        _LOGGER.info(
            "Creating %s: %s", self.__class__.__name__, entity_description.name
        )

        self.device = device
        self._mac_address = device.get("mac_address")
        self.entity_description = entity_description
        self._attr_attribution = ATTRIBUTION

        self._device_id: str = device.get("id")
        self._device_type: str = device.get("type")
        self._device_name: str = device.get("name")

        self._attr_unique_id = (
            f"{self._mac_address}:{self._device_id}:{entity_description.key}"
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=MANUFACTURER,
            configuration_url=f"https://techsupport.orbitbhyve.com/dashboard/support/device/{self._device_id}",
            name=self._device_name,
            model=device.get("hardware_version"),
            hw_version=device.get("hardware_version"),
            sw_version=device.get("firmware_version"),
        )
        self._update_attrs(device)

    def _update_attrs(self, device: BHyveDevice) -> None:
        """Update state attributes."""
        self._attr_available = device.get("is_connected", False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        device = self.coordinator.data.get_device(self._device_id)
        if device:
            self._update_attrs(device)
        return super()._handle_coordinator_update()

    """
    # async def async_added_to_hass(self) -> None:

    #     @callback
    #     def update(_device_id: str, data: dict) -> None:
    #         event = data.get("event", "")
    #         if event == "device_disconnected":
    #             _LOGGER.warning(
    #                 "Device %s disconnected and is no longer available", self.name
    #             )
    #             self._available = False
    #         elif event == "device_connected":
    #             _LOGGER.info("Device %s reconnected and is now available", self.name)
    #             self._available = True
    #         if self._should_handle_event(event, data):
    #             _LOGGER.info(
    #                 "Message received: %s - %s - %s",
    #                 self.name,
    #                 self._device_id,
    #                 str(data),
    #             )
    #             self._ws_unprocessed_events.append(data)
    #             self.async_schedule_update_ha_state(True)  # noqa: FBT003

    #     self._async_unsub_dispatcher_connect = async_dispatcher_connect(
    #         self.hass, SIGNAL_UPDATE_DEVICE.format(self._device_id), update
    #     )
    """

    async def set_manual_preset_runtime(self, minutes: int) -> None:
        """
        Set the default watering runtime for the device.

        # {event: "set_manual_preset_runtime", device_id: "abc", seconds: 900}
        """
        payload = {
            "event": EVENT_SET_MANUAL_PRESET_TIME,
            "device_id": self._device_id,
            "seconds": minutes * 60,
        }
        _LOGGER.info("Setting manual preset runtime: %s", payload)
        await self.coordinator.api.send_message(payload)

    async def enable_rain_delay(self, hours: int = 24) -> None:
        """Enable rain delay."""
        await self._set_rain_delay(hours)

    async def disable_rain_delay(self) -> None:
        """Disable rain delay."""
        await self._set_rain_delay(0)

    async def _set_rain_delay(self, hours: int) -> None:
        try:
            """
            # {event: "rain_delay", device_id: "abc", delay: 48}
            """
            payload = {
                "event": EVENT_RAIN_DELAY,
                "device_id": self._device_id,
                "delay": hours,
            }
            _LOGGER.info("Setting rain delay: %s", payload)
            await self.coordinator.api.send_message(payload)

        except BHyveError as err:
            _LOGGER.warning("Failed to send to BHyve websocket message %s", err)
            raise BHyveError(err) from err
