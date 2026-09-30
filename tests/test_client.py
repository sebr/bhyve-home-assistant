"""Test BHyve pybhyve client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.bhyve.pybhyve.client import BHyveClient


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
