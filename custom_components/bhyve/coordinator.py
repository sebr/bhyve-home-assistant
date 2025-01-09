"""DataUpdateCoordinator for BHyve."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.bhyve.pybhyve.errors import WebsocketError

from .const import DOMAIN, EVENT_PROGRAM_CHANGED, LOGGER
from .pybhyve.typings import BHyveApiData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import BHyveConfigEntry
    from .pybhyve.client import BHyveClient


class BHyveUpdateCoordinator(DataUpdateCoordinator[BHyveApiData]):
    """Class to manage fetching data from the API."""

    config_entry: BHyveConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BHyveConfigEntry,
        api: BHyveClient,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=DOMAIN,
            always_update=False,
        )
        self.config_entry = entry
        self.api = api

        self.monitor_connected: bool = False

    async def _async_setup(self) -> None:
        self._shutdown_remove_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._async_shutdown
        )

        return await super()._async_setup()

    async def _async_shutdown(self, _event: Any) -> None:
        """Call from Homeassistant shutdown event."""
        # unset remove listener otherwise calling it would raise an exception
        self._shutdown_remove_listener = None
        await self.async_unload()

    async def async_unload(self) -> None:
        """Stop the update monitor."""
        if self._shutdown_remove_listener:
            self._shutdown_remove_listener()

        await self.api.stop()
        self.monitor_connected = False

    async def _async_update_data(self) -> BHyveApiData:
        """Fetch data from the API."""
        try:
            LOGGER.debug("Fetching API Data")
            data = await self.api.get_data()
        except Exception as err:
            LOGGER.debug("Failed to fetch data: %s", err)
            LOGGER.exception("Error fetching data from BHyve")
            raise UpdateFailed(err) from err

        return data

    async def client_listen(
        self,
    ) -> None:
        """Listen with the client."""

        async def async_update_callback(payload: dict) -> None:
            """Handle incoming websocket events."""
            event = payload.get("event")

            device_id: str | None = payload.get("device_id")
            program_id: str | None = None

            if event == EVENT_PROGRAM_CHANGED:
                device_id = payload.get("program", {}).get("device_id")
                program_id = payload.get("program", {}).get("id")

            LOGGER.info("Received event: %s: %s", event, device_id)
            LOGGER.debug("%s", payload)

        try:
            await self.api.listen(async_update_callback)
            # Reset reconnect time after successful connection
            await self.api.start()
        except WebsocketError as err:
            LOGGER.debug(
                "Failed to connect to websocket. Trying to reconnect: %s",
                err,
            )

    @callback
    def callback(self, data: BHyveApiData) -> None:
        """Process webhook callbacks and write them to the DataUpdateCoordinator."""
        self.async_set_updated_data(data)
