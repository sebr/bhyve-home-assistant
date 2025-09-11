"""Test BHyve config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import data_entry_flow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.bhyve.config_flow import ConfigFlow, OptionsFlowHandler
from custom_components.bhyve.const import CONF_DEVICES, DEVICE_BRIDGE
from custom_components.bhyve.pybhyve.errors import AuthenticationError, BHyveError

# Test constants
TEST_USERNAME = "test@example.com"
TEST_PASSWORD = "test_password"  # noqa: S105
TEST_DEVICE_ID = "test-device-123"
TEST_DEVICE_NAME = "Test Sprinkler"
TEST_BRIDGE_DEVICE_ID = "bridge-456"

MOCK_DEVICES = [
    {
        "id": TEST_DEVICE_ID,
        "name": TEST_DEVICE_NAME,
        "type": "sprinkler_timer",
    },
    {
        "id": "device-789",
        "name": "Garden Sprinkler",
        "type": "sprinkler_timer",
    },
    {
        "id": TEST_BRIDGE_DEVICE_ID,
        "name": "Bridge Device",
        "type": DEVICE_BRIDGE,
    },
]


@pytest.fixture
def mock_bhyve_client() -> MagicMock:
    """Mock BHyve client."""
    client = MagicMock()
    client.login = AsyncMock(return_value=True)

    # Mock async properties - these need to be coroutines that can be awaited
    async def devices_property() -> list[dict[str, str]]:
        return MOCK_DEVICES

    async def timer_programs_property() -> list:
        return []

    # Set the properties to return the coroutines
    type(client).devices = property(lambda _: devices_property())
    type(client).timer_programs = property(lambda _: timer_programs_property())

    return client


class TestConfigFlow:
    """Test the config flow."""

    async def test_user_flow_success(
        self, hass: HomeAssistant, mock_bhyve_client: MagicMock
    ) -> None:
        """Test successful user flow."""
        with (
            patch(
                "custom_components.bhyve.config_flow.BHyveClient",
                return_value=mock_bhyve_client,
            ),
            patch.object(ConfigFlow, "async_set_unique_id"),
            patch.object(ConfigFlow, "_abort_if_unique_id_configured"),
        ):
            flow = ConfigFlow()
            flow.hass = hass

            # Test user step form
            result = await flow.async_step_user()
            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "user"

            # Test user step with valid credentials
            result = await flow.async_step_user(
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                }
            )

            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "device"

            # Test device selection step
            result = await flow.async_step_device(
                {CONF_DEVICES: [TEST_DEVICE_ID, "device-789"]}
            )

            assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
            assert result["title"] == TEST_USERNAME
            assert result["data"] == {
                CONF_USERNAME: TEST_USERNAME,
                CONF_PASSWORD: TEST_PASSWORD,
            }
            assert result["options"] == {CONF_DEVICES: [TEST_DEVICE_ID, "device-789"]}

    async def test_user_flow_invalid_credentials(self, hass: HomeAssistant) -> None:
        """Test user flow with invalid credentials."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(
            side_effect=AuthenticationError("Invalid credentials")
        )

        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass

            result = await flow.async_step_user(
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: "wrong_password",
                }
            )

            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "user"
            assert result["errors"] == {"base": "invalid_auth"}

    async def test_user_flow_connection_error(self, hass: HomeAssistant) -> None:
        """Test user flow with connection error."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(side_effect=Exception("Connection failed"))

        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass

            result = await flow.async_step_user(
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                }
            )

            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "user"
            assert result["errors"] == {"base": "cannot_connect"}

    async def test_user_flow_login_false(self, hass: HomeAssistant) -> None:
        """Test user flow when login returns False."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(return_value=False)

        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass

            result = await flow.async_step_user(
                {
                    CONF_USERNAME: TEST_USERNAME,
                    CONF_PASSWORD: TEST_PASSWORD,
                }
            )

            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "user"
            assert result["errors"] == {"base": "invalid_auth"}

    async def test_user_flow_show_form(self, hass: HomeAssistant) -> None:
        """Test user flow shows initial form."""
        flow = ConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user()

        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] is None

    async def test_device_step_filters_bridge_devices(
        self, hass: HomeAssistant, mock_bhyve_client: MagicMock
    ) -> None:
        """Test device step filters out bridge devices."""
        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_bhyve_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass
            flow.devices = MOCK_DEVICES

            result = await flow.async_step_device()

            # Check that bridge device is filtered out in device options
            device_schema = result["data_schema"].schema[CONF_DEVICES]
            device_options = device_schema.options

            assert TEST_BRIDGE_DEVICE_ID not in device_options
            assert TEST_DEVICE_ID in device_options
            assert "device-789" in device_options

    async def test_unique_id_already_configured(
        self, hass: HomeAssistant, mock_bhyve_client: MagicMock
    ) -> None:
        """Test that duplicate entries are aborted."""
        with (
            patch(
                "custom_components.bhyve.config_flow.BHyveClient",
                return_value=mock_bhyve_client,
            ),
            patch.object(ConfigFlow, "_abort_if_unique_id_configured"),
        ):
            flow = ConfigFlow()
            flow.hass = hass

            # Mock setting unique id
            with patch.object(flow, "async_set_unique_id"):
                result = await flow.async_step_user(
                    {
                        CONF_USERNAME: TEST_USERNAME,
                        CONF_PASSWORD: TEST_PASSWORD,
                    }
                )

            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "device"

    async def test_reauth_flow_success(
        self, hass: HomeAssistant, mock_bhyve_client: MagicMock
    ) -> None:
        """Test successful reauth flow."""
        with (
            patch(
                "custom_components.bhyve.config_flow.BHyveClient",
                return_value=mock_bhyve_client,
            ),
            patch.object(ConfigFlow, "async_set_unique_id") as mock_set_unique,
            patch("homeassistant.config_entries.ConfigEntries.async_update_entry"),
            patch("homeassistant.config_entries.ConfigEntries.async_reload"),
        ):
            flow = ConfigFlow()
            flow.hass = hass

            # Mock existing entry
            mock_entry = MagicMock()
            mock_set_unique.return_value = mock_entry

            # Start reauth with username
            result = await flow.async_step_reauth({CONF_USERNAME: TEST_USERNAME})

            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "reauth"

            # Complete reauth with password
            result = await flow.async_step_reauth({CONF_PASSWORD: "new_password"})

            assert result["type"] == data_entry_flow.FlowResultType.ABORT
            assert result["reason"] == "reauth_successful"

    async def test_reauth_flow_invalid_auth(self, hass: HomeAssistant) -> None:
        """Test reauth flow with invalid auth."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(side_effect=AuthenticationError("Invalid"))

        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass
            flow._reauth_username = TEST_USERNAME

            result = await flow.async_step_reauth({CONF_PASSWORD: "wrong_password"})

            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "reauth"
            assert result["errors"] == {"base": "invalid_auth"}

    async def test_import_flow_success(
        self, hass: HomeAssistant, mock_bhyve_client: MagicMock
    ) -> None:
        """Test successful import flow."""
        config = {
            CONF_USERNAME: TEST_USERNAME,
            CONF_PASSWORD: TEST_PASSWORD,
        }

        with (
            patch(
                "custom_components.bhyve.config_flow.BHyveClient",
                return_value=mock_bhyve_client,
            ),
            patch.object(ConfigFlow, "async_set_unique_id"),
            patch.object(ConfigFlow, "_abort_if_unique_id_configured"),
        ):
            flow = ConfigFlow()
            flow.hass = hass

            result = await flow.async_step_import(config)

            assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
            assert result["title"] == TEST_USERNAME
            assert result["data"] == config
            # Should auto-select all non-bridge devices
            assert result["options"] == {CONF_DEVICES: [TEST_DEVICE_ID, "device-789"]}

    async def test_import_flow_auth_error(self, hass: HomeAssistant) -> None:
        """Test import flow with auth error."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(side_effect=AuthenticationError("Invalid"))

        config = {
            CONF_USERNAME: TEST_USERNAME,
            CONF_PASSWORD: "wrong_password",
        }

        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass

            result = await flow.async_step_import(config)

            assert result["type"] == data_entry_flow.FlowResultType.ABORT
            assert result["reason"] == "cannot_connect"


@pytest.mark.skip(
    reason="OptionsFlow tests disabled due to Home Assistant framework constraints"
)
class TestOptionsFlow:
    """Test the options flow."""

    async def test_options_flow_success(
        self, hass: HomeAssistant, mock_bhyve_client: MagicMock
    ) -> None:
        """Test successful options flow."""
        # Mock config entry
        mock_config_entry = MagicMock()
        mock_config_entry.state = "loaded"
        mock_config_entry.entry_id = "test_entry_id"
        mock_config_entry.options = {CONF_DEVICES: [TEST_DEVICE_ID]}

        # Setup mock data in hass
        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_bhyve_client,
                }
            }
        }

        with patch(
            "homeassistant.helpers.frame.report_usage"
        ):  # Suppress the deprecation warning
            options_flow = OptionsFlowHandler(mock_config_entry)
            options_flow.hass = hass

        result = await options_flow.async_step_init()

        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "init"

        # Test completing the options flow
        result = await options_flow.async_step_init({CONF_DEVICES: [TEST_DEVICE_ID]})

        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result["data"] == {CONF_DEVICES: [TEST_DEVICE_ID]}

    async def test_options_flow_auth_error(self, hass: HomeAssistant) -> None:
        """Test options flow with authentication error."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(side_effect=AuthenticationError("Invalid"))

        mock_config_entry = MagicMock()
        mock_config_entry.state = "loaded"
        mock_config_entry.entry_id = "test_entry_id"

        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_client,
                }
            }
        }

        with patch(
            "homeassistant.helpers.frame.report_usage"
        ):  # Suppress the deprecation warning
            options_flow = OptionsFlowHandler(mock_config_entry)
            options_flow.hass = hass

        result = await options_flow.async_step_init()

        assert result["type"] == data_entry_flow.FlowResultType.ABORT
        assert result["reason"] == "invalid_auth"

    async def test_options_flow_connection_error(self, hass: HomeAssistant) -> None:
        """Test options flow with connection error."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(side_effect=BHyveError("Connection failed"))

        mock_config_entry = MagicMock()
        mock_config_entry.state = "loaded"
        mock_config_entry.entry_id = "test_entry_id"

        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_client,
                }
            }
        }

        with patch(
            "homeassistant.helpers.frame.report_usage"
        ):  # Suppress the deprecation warning
            options_flow = OptionsFlowHandler(mock_config_entry)
            options_flow.hass = hass

        result = await options_flow.async_step_init()

        assert result["type"] == data_entry_flow.FlowResultType.ABORT
        assert result["reason"] == "cannot_connect"

    async def test_options_flow_config_not_loaded(self, hass: HomeAssistant) -> None:
        """Test options flow when config entry is not loaded."""
        mock_config_entry = MagicMock()
        mock_config_entry.state = "not_loaded"

        with patch(
            "homeassistant.helpers.frame.report_usage"
        ):  # Suppress the deprecation warning
            options_flow = OptionsFlowHandler(mock_config_entry)
            options_flow.hass = hass

        result = await options_flow.async_step_init()

        assert result["type"] == data_entry_flow.FlowResultType.ABORT
        assert result["reason"] == "unknown"

    async def test_options_flow_filters_bridge_devices(
        self, hass: HomeAssistant, mock_bhyve_client: MagicMock
    ) -> None:
        """Test options flow filters out bridge devices."""
        mock_config_entry = MagicMock()
        mock_config_entry.state = "loaded"
        mock_config_entry.entry_id = "test_entry_id"
        mock_config_entry.options = {CONF_DEVICES: [TEST_DEVICE_ID]}

        hass.data = {
            "bhyve": {
                "test_entry_id": {
                    "client": mock_bhyve_client,
                }
            }
        }

        with patch(
            "homeassistant.helpers.frame.report_usage"
        ):  # Suppress the deprecation warning
            options_flow = OptionsFlowHandler(mock_config_entry)
            options_flow.hass = hass

        result = await options_flow.async_step_init()

        # Check that bridge device is filtered out
        device_schema = result["data_schema"].schema[CONF_DEVICES]
        device_options = device_schema.options

        assert TEST_BRIDGE_DEVICE_ID not in device_options
        assert TEST_DEVICE_ID in device_options
        assert "device-789" in device_options


class TestConfigFlowHelpers:
    """Test config flow helper methods."""

    async def test_async_auth_helper_success(
        self, hass: HomeAssistant, mock_bhyve_client: MagicMock
    ) -> None:
        """Test async_auth helper with successful authentication."""
        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_bhyve_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass

            user_input = {
                CONF_USERNAME: TEST_USERNAME,
                CONF_PASSWORD: TEST_PASSWORD,
            }

            result = await flow.async_auth(user_input)

            assert result is None
            assert flow.client is not None

    async def test_async_auth_helper_invalid_auth(self, hass: HomeAssistant) -> None:
        """Test async_auth helper with invalid authentication."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(side_effect=AuthenticationError("Invalid"))

        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass

            user_input = {
                CONF_USERNAME: TEST_USERNAME,
                CONF_PASSWORD: "wrong_password",
            }

            result = await flow.async_auth(user_input)

            assert result == {"base": "invalid_auth"}

    async def test_async_auth_helper_connection_error(
        self, hass: HomeAssistant
    ) -> None:
        """Test async_auth helper with connection error."""
        mock_client = MagicMock()
        mock_client.login = AsyncMock(side_effect=Exception("Connection failed"))

        with patch(
            "custom_components.bhyve.config_flow.BHyveClient",
            return_value=mock_client,
        ):
            flow = ConfigFlow()
            flow.hass = hass

            user_input = {
                CONF_USERNAME: TEST_USERNAME,
                CONF_PASSWORD: TEST_PASSWORD,
            }

            result = await flow.async_auth(user_input)

            assert result == {"base": "cannot_connect"}

    async def test_async_get_options_flow(self) -> None:
        """Test async_get_options_flow static method."""
        mock_entry = MagicMock()

        with patch(
            "custom_components.bhyve.config_flow.OptionsFlowHandler"
        ) as mock_handler:
            ConfigFlow.async_get_options_flow(mock_entry)
            mock_handler.assert_called_once_with(mock_entry)
