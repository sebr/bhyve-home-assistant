#!/usr/bin/env python3
# ruff: noqa: T201
"""
Read-only smoke test of the bundled pybhyve client against the real Orbit cloud.

It checks the assumptions the integration relies on and that unit tests can
only mock:

  1. which session token field Orbit's login response carries (#474)
  2. that login, devices, programs, history and landscapes work with it
  3. that Orbit rejects a bad token with 401/403, and the client recovers by
     logging in again
  4. that the event websocket accepts the session and stays connected

Nothing is changed on the account or devices: it only reads, and the
websocket is listened to without sending commands. Credentials, tokens and
device ids are never printed, so the report is safe to paste into an issue.

Usage (credentials from the environment, or prompted if unset):

    BHYVE_EMAIL=you@example.com BHYVE_PASSWORD=... python debug/live_smoke.py
    python debug/live_smoke.py --listen 120

Only aiohttp is needed; Home Assistant does not have to be installed.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

# Import pybhyve on its own, without custom_components/bhyve/__init__.py,
# which needs Home Assistant.
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "bhyve")
)

from pybhyve.client import BHyveClient
from pybhyve.const import API_HOST, LOGIN_PATH, WEB_HOST
from pybhyve.errors import BHyveError

TOKEN_FIELDS = ("orbit_session_token", "orbit_api_key")
BOGUS_TOKEN = "live-smoke-test-invalid-token"  # noqa: S105


@dataclass
class Report:
    """Collected check results."""

    results: list[tuple[str, bool, str]] = field(default_factory=list)

    def check(self, name: str, *, ok: bool, detail: str = "") -> bool:
        """Record and print one check."""
        self.results.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}" + (f": {detail}" if detail else ""))
        return ok

    def info(self, text: str) -> None:
        """Print an informational line."""
        print(f"       {text}")


class _StatusCapture(logging.Handler):
    """Capture the HTTP status pybhyve logs when Orbit rejects a session."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.auth_statuses: list[str] = []
        self.ws_errors: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message.startswith("Authentication error from"):
            self.auth_statuses.append(message.rsplit(":", 1)[-1].strip())
        elif record.name.endswith("websocket"):
            self.ws_errors.append(message)


async def check_login_response(
    session: aiohttp.ClientSession, email: str, password: str, report: Report
) -> None:
    """Report which token field Orbit's login response carries."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
        "Origin": WEB_HOST,
        "Referer": f"{WEB_HOST}/",
        "orbit-app-id": "Bhyve Dashboard",
        "orbit-api-key": "null",
    }
    body = {"session": {"email": email, "password": password}}
    async with session.request(
        "post", f"{API_HOST}{LOGIN_PATH}", json=body, headers=headers
    ) as resp:
        status = resp.status
        data = await resp.json(content_type=None) if status < 400 else None  # noqa: PLR2004

    if not report.check("login accepted", ok=status < 300, detail=f"HTTP {status}"):  # noqa: PLR2004
        return
    keys = sorted(data) if isinstance(data, dict) else []
    present = [f for f in TOKEN_FIELDS if keys and data.get(f)]
    report.info(f"response fields: {', '.join(keys)}")
    report.check(
        "session token field",
        ok=bool(present),
        detail=", ".join(present) or "neither orbit_session_token nor orbit_api_key",
    )


async def check_rest(client: BHyveClient, report: Report) -> list[dict[str, Any]]:
    """Log in through the client and read every endpoint the integration uses."""
    try:
        await client.login()
    except BHyveError as err:
        report.check("client login", ok=False, detail=str(err) or type(err).__name__)
        return []
    report.check("client login", ok=True)

    devices = await client.devices
    report.check(
        "devices", ok=isinstance(devices, list), detail=f"{len(devices)} found"
    )
    for device in devices:
        zones = len(device.get("zones") or [])
        connected = "connected" if device.get("is_connected") else "offline"
        paired = (
            ""
            if device.get("status") or device.get("type") == "bridge"
            else ", no status"
        )
        report.info(
            f"{device.get('type')}: {device.get('name')!r} "
            f"({connected}, {zones} zones, hw {device.get('hardware_version')}{paired})"
        )

    programs = await client.timer_programs
    smart = sum(1 for p in programs if p.get("is_smart_program"))
    report.check(
        "programs",
        ok=isinstance(programs, list),
        detail=f"{len(programs)} ({smart} smart)",
    )

    for device in devices:
        if device.get("type") != "sprinkler_timer":
            continue
        history = await client.get_device_history(device["id"]) or []
        runs = [i for h in history for i in h.get("irrigation", [])]
        with_volume = sum(1 for i in runs if i.get("water_volume_gal") is not None)
        report.check(
            f"history for {device.get('name')!r}",
            ok=isinstance(history, list),
            detail=f"{len(runs)} runs, {with_volume} with water volume",
        )
        zones = device.get("zones") or []
        if zones:
            landscape = await client.get_landscape(
                device["id"], zones[0].get("station")
            )
            fields = sorted(landscape) if landscape else []
            report.check(
                f"landscape for {device.get('name')!r}",
                ok=True,
                detail=(
                    "soil moisture fields present"
                    if {"current_water_level", "field_capacity_depth"} <= set(fields)
                    else "no landscape data (smart watering may be off)"
                ),
            )
    return devices


async def check_relogin(
    client: BHyveClient, capture: _StatusCapture, report: Report
) -> None:
    """Make Orbit reject the session and check the client logs in again."""
    logins = 0
    real_login = client.login

    async def counting_login() -> bool:
        nonlocal logins
        logins += 1
        return await real_login()

    client.login = counting_login  # type: ignore[method-assign]
    client._token = BOGUS_TOKEN  # noqa: SLF001
    capture.auth_statuses.clear()
    try:
        device = await client.get_device("__none__", force_update=True)
    except BHyveError as err:
        report.check("re-login after rejected token", ok=False, detail=str(err))
        return
    finally:
        client.login = real_login  # type: ignore[method-assign]

    status = capture.auth_statuses[0] if capture.auth_statuses else "not rejected"
    report.check(
        "Orbit rejects a bad token with 401/403",
        ok=status in ("401", "403"),
        detail=f"HTTP {status}",
    )
    report.check(
        "re-login after rejected token",
        ok=logins == 1 and client._token not in (None, BOGUS_TOKEN) and device is None,  # noqa: SLF001
        detail=f"{logins} login(s), devices fetched again",
    )


async def check_websocket(
    client: BHyveClient, capture: _StatusCapture, seconds: int, report: Report
) -> None:
    """Listen to the event websocket without sending any commands."""
    events: Counter[str] = Counter()

    async def on_event(data: dict[str, Any]) -> None:
        events[str(data.get("event"))] += 1

    capture.ws_errors.clear()
    client.listen(asyncio.get_running_loop(), on_event)
    websocket = client._websocket  # noqa: SLF001
    print(f"       listening to the event websocket for {seconds}s...")

    states = []
    for _ in range(seconds):
        await asyncio.sleep(1)
        states.append(websocket.state)
    warnings = list(capture.ws_errors)
    # Closing logs "websocket connection closed" as an error; it is expected here.
    logging.getLogger("pybhyve.websocket").disabled = True
    await client.stop()
    await asyncio.sleep(0.1)

    connected = states.count("running")
    report.check(
        "websocket stayed connected",
        ok=connected >= len(states) - 2,
        detail=f"running {connected}/{len(states)}s, {len(warnings)} warnings",
    )
    for message in warnings[:5]:
        report.info(f"websocket: {message}")
    summary = ", ".join(f"{name} x{count}" for name, count in events.most_common())
    report.info(
        f"events received: {summary}"
        if events
        else "no events received (normal when nothing is watering or changing)"
    )


async def run(email: str, password: str, listen: int) -> bool:
    """Run every check and return whether all passed."""
    capture = _StatusCapture()
    logging.getLogger("pybhyve").addHandler(capture)
    report = Report()

    async with aiohttp.ClientSession() as session:
        print("== Login response (#474)")
        await check_login_response(session, email, password, report)

        client = BHyveClient(email, password, session=session)
        print("\n== REST endpoints")
        devices = await check_rest(client, report)
        if devices:
            print("\n== Expired session")
            await check_relogin(client, capture, report)
            if listen > 0:
                print("\n== Event websocket")
                await check_websocket(client, capture, listen, report)

    failed = [name for name, ok, _ in report.results if not ok]
    print(f"\n{len(report.results) - len(failed)}/{len(report.results)} checks passed")
    if failed:
        print("Failed: " + "; ".join(failed))
    return not failed


def main() -> int:
    """Parse arguments, prompt for missing credentials, and run."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--listen",
        type=int,
        default=60,
        help="seconds to listen to the websocket (0 to skip, default 60)",
    )
    args = parser.parse_args()

    email = os.environ.get("BHYVE_EMAIL") or input("B-hyve email: ")
    password = os.environ.get("BHYVE_PASSWORD") or getpass.getpass("B-hyve password: ")
    # Show pybhyve's warnings, not its info chatter; the report prints the rest.
    handler = logging.StreamHandler()
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("       log: %(message)s"))
    logging.getLogger().addHandler(handler)
    return 0 if asyncio.run(run(email, password, args.listen)) else 1


if __name__ == "__main__":
    sys.exit(main())
