# ruff: noqa
#! /usr/bin/env python3
# Script utility to debug device/program info from logs

import glob
import json
import os
import sys

if len(sys.argv) < 2:
    print("Not enough arguments")
    sys.exit()

FOLDER = sys.argv[1]

script_dir = os.path.dirname(os.path.realpath(__file__))

config_entry_files = glob.glob(os.path.join(script_dir, FOLDER, "config_entry*"))
if not config_entry_files:
    print("No config_entry file found")
    sys.exit()
diagnostics_json = config_entry_files[0]

with open(diagnostics_json, encoding="utf8") as diagnosticsFile:
    diagnostics = json.load(diagnosticsFile)
    diagnosticsFile.close()

for device in diagnostics.get("data").get("devices"):
    if device.get("type") == "bridge":
        continue

    name = device.get("name", "Unknown Name")
    print()
    print(f"===============  {name}  ====================")
    print(f"{'Type':>10}: {device.get('type')}")
    print(f"{'id':>10}: {device.get('id')}")
    print(f"{'Last seen':>10}: {device.get('last_connected_at')}")
    print(f"{'Battery':>10}: {device.get('battery')}")

    if device.get("type") == "sprinkler_timer":
        zones = device.get("zones")
        print(f"{'Zones':>10}: {len(zones)}")
        for zone in device.get("zones"):
            zn = zone.get("name", "Unknown Zone")
            zid = zone.get("station")
            print(f"            [{zid:>2}] {zn}")
