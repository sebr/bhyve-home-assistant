"""Config flow for BHyve integration."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_AUTO_ADD,
    CONF_DEVICES,
    CONF_KNOWN_DEVICES,
    DEVICE_BRIDGE,
    DOMAIN,
)
from .pybhyve import BHyveClient
from .pybhyve.errors import AuthenticationError, BHyveError
from .util import unoffered_device_ids

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult


class BHyveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BHyve."""

    VERSION = 1
    # 2: auto-add devices new to the account (see async_migrate_entry).
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.data: dict[str, Any] = {}
        self.client: BHyveClient | None = None
        self.devices: list[Any] | None = None
        self.programs: list[Any] | None = None
        self._reauth_username: str | None = None

    async def async_auth(self, user_input: dict[str, str]) -> dict[str, str] | None:
        """Reusable Auth Helper."""
        self.client = BHyveClient(
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            session=async_get_clientsession(self.hass),
        )

        try:
            await self.client.login()
        except AuthenticationError:
            return {"base": "invalid_auth"}
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("BHyve login failed with an unexpected error")
            return {"base": "cannot_connect"}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] | None = None

        if user_input is not None and not (errors := await self.async_auth(user_input)):
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            self.data = user_input
            self.devices = await self.client.devices  # type: ignore[union-attr]
            self.programs = await self.client.timer_programs  # type: ignore[union-attr]

            return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the optional device selection step."""
        device_options = {
            str(d.get("id")): f"{d.get('name', 'Unnamed device')}"
            for d in (self.devices or [])
            if d.get("type") != DEVICE_BRIDGE
        }
        if user_input is not None:
            options = {
                CONF_DEVICES: user_input[CONF_DEVICES],
                CONF_AUTO_ADD: user_input.get(CONF_AUTO_ADD, True),
                CONF_KNOWN_DEVICES: list(device_options),
            }
            return self.async_create_entry(
                title=self.data[CONF_USERNAME], data=self.data, options=options
            )

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICES, default=list(device_options.keys())
                    ): cv.multi_select(device_options),
                    vol.Optional(CONF_AUTO_ADD, default=True): bool,
                }
            ),
            errors=None,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth."""
        errors: dict[str, str] | None = None
        if user_input and user_input.get(CONF_USERNAME):
            self._reauth_username = user_input[CONF_USERNAME]

        elif self._reauth_username and user_input and user_input.get(CONF_PASSWORD):
            data = {
                CONF_USERNAME: self._reauth_username,
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }

            if not (errors := await self.async_auth(data)):
                entry = await self.async_set_unique_id(self._reauth_username.lower())
                if entry:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data=data,
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")
                return self.async_create_entry(title=self._reauth_username, data=data)

        return self.async_show_form(
            step_id="reauth",
            description_placeholders={"username": self._reauth_username or ""},
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,  # noqa: ARG004
    ) -> BhyveOptionsFlowHandler:
        """Get the options flow for this handler."""
        return BhyveOptionsFlowHandler()


class BhyveOptionsFlowHandler(OptionsFlowWithReload):
    """Options flow for picking devices."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._offered: list[str] = []
        self._saved_when_shown: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            options = self.config_entry.options
            return self.async_create_entry(
                title="",
                data={
                    # A device auto-added while the form was open wasn't on
                    # it, so it can't have been deselected: keep it. Other
                    # saved devices the form didn't offer have left the
                    # account, and are dropped.
                    CONF_DEVICES: [
                        *user_input[CONF_DEVICES],
                        *(
                            d
                            for d in options.get(CONF_DEVICES, [])
                            if d not in self._offered
                            and d not in self._saved_when_shown
                        ),
                    ],
                    CONF_AUTO_ADD: user_input.get(CONF_AUTO_ADD, True),
                    # Everything the form offered is "known": a device left
                    # deselected is one the user chose not to have.
                    CONF_KNOWN_DEVICES: list(
                        dict.fromkeys(
                            [*options.get(CONF_KNOWN_DEVICES, []), *self._offered]
                        )
                    ),
                },
            )

        if self.config_entry.state != ConfigEntryState.LOADED:
            return self.async_abort(reason="unknown")

        data = self.hass.data[DOMAIN][self.config_entry.entry_id]
        try:
            # The client logs in again by itself if its session has expired.
            devices = await data["client"].devices
        except AuthenticationError:
            return self.async_abort(reason="invalid_auth")
        except (BHyveError, TimeoutError):
            return self.async_abort(reason="cannot_connect")

        _LOGGER.debug("Devices: %s", json.dumps(devices))

        device_options = {
            str(d.get("id")): f"{d.get('name', 'Unnamed device')}"
            for d in devices
            if d.get("type") != DEVICE_BRIDGE
        }

        # Filter saved defaults to only include devices that still exist,
        # in case a device was removed from the B-hyve account.
        options = self.config_entry.options
        saved_devices = options.get(CONF_DEVICES, [])
        valid_defaults = [d for d in saved_devices if d in device_options]
        # A device the user has never been offered starts selected, with
        # auto-add on or off: submitting the form records it as known, so
        # leaving it unticked unseen would keep it out for good.
        valid_defaults = list(
            dict.fromkeys([*valid_defaults, *unoffered_device_ids(options, devices)])
        )
        self._offered = list(device_options)
        self._saved_when_shown = list(saved_devices)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICES,
                        default=valid_defaults,
                    ): cv.multi_select(device_options),
                    vol.Optional(
                        CONF_AUTO_ADD,
                        default=options.get(CONF_AUTO_ADD, True),
                    ): bool,
                }
            ),
        )
