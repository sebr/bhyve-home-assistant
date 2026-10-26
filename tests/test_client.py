"""Test BHyve pybhyve client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.bhyve.pybhyve.client import BHyveClient
from custom_components.bhyve.pybhyve.errors import (
    AuthenticationError,
    RequestError,
    WebsocketError,
)

from .fake_orbit import FakeResponse


@pytest.fixture
def client() -> BHyveClient:
    """Create a BHyveClient with a mocked session."""
    session = MagicMock()
    return BHyveClient("user", "pass", session)


class TestRefreshDeviceHistory:
    """Test per-device rate limiting of history refresh."""

    async def test_fetches_history_for_each_device(self, client: BHyveClient) -> None:
        """
        Back-to-back calls for different devices must each fetch history.

        Regression test for issue #393: a shared rate-limit timestamp caused
        the second sprinkler_timer in a multi-device account to never have
        its history populated, so its zone history sensor stayed unknown.
        """
        client._request = AsyncMock(
            side_effect=lambda *_args, **_kwargs: [{"fetched_for": "ok"}]
        )

        await client._refresh_device_history("device-a")
        await client._refresh_device_history("device-b")

        assert client._request.await_count == 2
        assert "device-a" in client._device_histories
        assert "device-b" in client._device_histories

    async def test_rate_limits_same_device(self, client: BHyveClient) -> None:
        """A second call for the same device within the poll period is skipped."""
        client._request = AsyncMock(return_value=[{"fetched_for": "ok"}])

        await client._refresh_device_history("device-a")
        await client._refresh_device_history("device-a")

        assert client._request.await_count == 1

    async def test_force_update_bypasses_rate_limit(self, client: BHyveClient) -> None:
        """force_update=True refetches even within the poll period."""
        client._request = AsyncMock(return_value=[{"fetched_for": "ok"}])

        await client._refresh_device_history("device-a")
        await client._refresh_device_history("device-a", force_update=True)

        assert client._request.await_count == 2


class TestGetLandscape:
    """Test per-device landscape fetching and caching."""

    async def test_fetches_landscapes_for_each_device(
        self, client: BHyveClient
    ) -> None:
        """
        Back-to-back landscape fetches for different devices must each hit the API.

        Regression test for the same-shape bug as issue #393 on the landscape
        refresh path: a shared rate-limit timestamp and shared landscapes list
        meant only the last-fetched device's data survived.
        """
        device_a_landscape = [{"station": 1, "device_id": "device-a"}]
        device_b_landscape = [{"station": 1, "device_id": "device-b"}]
        client._request = AsyncMock(
            side_effect=[device_a_landscape, device_b_landscape]
        )

        zone_a = await client.get_landscape("device-a", 1)
        zone_b = await client.get_landscape("device-b", 1)

        assert client._request.await_count == 2
        assert zone_a == {"station": 1, "device_id": "device-a"}
        assert zone_b == {"station": 1, "device_id": "device-b"}

    async def test_does_not_return_another_devices_landscape(
        self, client: BHyveClient
    ) -> None:
        """A zone lookup must only search within the requested device's landscapes."""
        client._request = AsyncMock(
            side_effect=[
                [{"station": 1, "device_id": "device-a"}],
                [{"station": 2, "device_id": "device-b"}],
            ]
        )

        await client.get_landscape("device-a", 1)
        # device-b has no station 1 — must not fall back to device-a's entry
        result = await client.get_landscape("device-b", 1)

        assert result is None

    async def test_rate_limits_same_device(self, client: BHyveClient) -> None:
        """A second landscape call for the same device within the period is skipped."""
        client._request = AsyncMock(return_value=[{"station": 1}])

        await client.get_landscape("device-a", 1)
        await client.get_landscape("device-a", 1)

        assert client._request.await_count == 1

    async def test_concurrent_calls_dedupe_to_single_request(
        self, client: BHyveClient
    ) -> None:
        """
        Concurrent get_landscape calls for the same device share one HTTP request.

        The coordinator fans out per-zone landscape lookups in parallel. Without
        single-flight locking, N zones trigger N duplicate requests to the same
        endpoint.
        """
        call_started = asyncio.Event()
        release = asyncio.Event()

        async def slow_request(*_args: object, **_kwargs: object) -> list:
            call_started.set()
            await release.wait()
            return [{"station": 1}, {"station": 2}, {"station": 3}]

        client._request = AsyncMock(side_effect=slow_request)

        tasks = [
            asyncio.create_task(client.get_landscape("device-a", zone_id))
            for zone_id in (1, 2, 3)
        ]
        await call_started.wait()
        release.set()
        await asyncio.gather(*tasks)

        assert client._request.await_count == 1


def client_with_responses(*responses: FakeResponse) -> BHyveClient:
    """Create a client whose session answers requests with responses in order."""
    session = MagicMock()
    session.request = MagicMock(side_effect=list(responses))
    return BHyveClient("user", "pass", session)


class TestLogin:
    """Test reading the session token from the login response."""

    async def test_reads_orbit_session_token(self) -> None:
        """Regression for #474: Orbit renamed orbit_api_key."""
        client = client_with_responses(
            FakeResponse(200, {"orbit_session_token": "session", "user_id": "u1"})
        )

        await client.login()

        assert client._token == "session"

    async def test_falls_back_to_orbit_api_key(self) -> None:
        """The old field still works if Orbit serves it."""
        client = client_with_responses(FakeResponse(200, {"orbit_api_key": "legacy"}))

        await client.login()

        assert client._token == "legacy"

    async def test_missing_token_raises_request_error(self) -> None:
        """A response without either field is reported, not a KeyError."""
        client = client_with_responses(FakeResponse(200, {"user_id": "u1"}))

        with pytest.raises(RequestError):
            await client.login()
        assert client._token is None

    async def test_rejected_credentials_raise_authentication_error(self) -> None:
        """A 401 from the session endpoint means the credentials are wrong."""
        client = client_with_responses(FakeResponse(401))

        # The message reaches the user through bhyve_command, so it can't be empty.
        with pytest.raises(AuthenticationError, match="rejected the login"):
            await client.login()

    async def test_server_error_has_a_message(self) -> None:
        """A 5xx from the session endpoint says what failed."""
        client = client_with_responses(FakeResponse(500))

        with pytest.raises(RequestError, match="Error logging in"):
            await client.login()

    async def test_hands_new_token_to_websocket(self) -> None:
        """A running websocket reconnects with the new session token."""
        client = client_with_responses(
            FakeResponse(200, {"orbit_session_token": "new"})
        )
        client._websocket = MagicMock()
        client._websocket.token = "old"

        await client.login()

        assert client._websocket.token == "new"


class TestRequestRelogin:
    """Test that an expired session logs in again instead of failing."""

    async def test_relogs_in_and_retries_once(self) -> None:
        """A 401 triggers one login, then the request is retried."""
        client = client_with_responses(
            FakeResponse(401),
            FakeResponse(200, {"orbit_session_token": "new"}),
            FakeResponse(200, [{"id": "device-1"}]),
        )
        client._token = "expired"

        result = await client._request("get", "/v1/devices")

        assert result == [{"id": "device-1"}]
        assert client._token == "new"
        retry_headers = client._session.request.call_args.kwargs["headers"]
        assert retry_headers["Orbit-Session-Token"] == "new"

    async def test_rejected_credentials_still_raise(self) -> None:
        """If the stored password no longer works, reauth is still needed."""
        client = client_with_responses(
            FakeResponse(401),
            FakeResponse(401),
        )
        client._token = "expired"

        with pytest.raises(AuthenticationError, match="rejected the login"):
            await client._request("get", "/v1/devices")

    async def test_rejected_session_has_a_message(self) -> None:
        """An authentication error from a request says what failed."""
        client = client_with_responses(FakeResponse(403))

        with pytest.raises(AuthenticationError, match="rejected the session"):
            await client._send_request("get", "/v1/devices")

    async def test_other_errors_do_not_relogin(self) -> None:
        """Only authentication errors log in again."""
        client = client_with_responses(FakeResponse(500))
        client._token = "token"
        client.login = AsyncMock()

        with pytest.raises(RequestError):
            await client._request("get", "/v1/devices")
        client.login.assert_not_awaited()

    async def test_skips_login_when_token_already_refreshed(self) -> None:
        """Concurrent 401s share the login that the first one made."""
        client = client_with_responses()
        client._token = "new"
        client.login = AsyncMock()

        await client._relogin("expired")

        client.login.assert_not_awaited()


async def test_send_message_without_websocket_raises() -> None:
    """Commands are not silently dropped before the websocket starts."""
    client = client_with_responses()

    with pytest.raises(WebsocketError):
        await client.send_message({"event": "rain_delay"})
