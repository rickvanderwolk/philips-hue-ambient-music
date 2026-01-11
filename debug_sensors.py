#!/usr/bin/env python3
"""Debug script to see all raw sensor data from Hue Bridge."""

import json
from hue_collector import HueCollector, load_config

def main():
    config = load_config()
    if not config.get("bridge_ip"):
        print("No saved config found. Run main.py first to connect to bridge.")
        return

    collector = HueCollector(config["bridge_ip"])
    if not collector.connect():
        print("Could not connect to bridge")
        return

    # Get raw API data
    api = collector.bridge.get_api()

    print("=" * 60)
    print("RAW SENSOR DATA FROM HUE BRIDGE")
    print("=" * 60)

    sensors = api.get("sensors", {})
    print(f"\nTotal sensors found: {len(sensors)}\n")

    for sensor_id, data in sensors.items():
        print(f"--- Sensor {sensor_id}: {data.get('name', 'Unknown')} ---")
        print(f"  Type: {data.get('type', 'Unknown')}")
        print(f"  Model: {data.get('modelid', 'Unknown')}")
        print(f"  Manufacturer: {data.get('manufacturername', 'Unknown')}")
        print(f"  State: {json.dumps(data.get('state', {}), indent=4)}")
        print(f"  Config: {json.dumps(data.get('config', {}), indent=4)}")
        print()

    print("=" * 60)
    print("PARSED SENSORS (what our code sees)")
    print("=" * 60)

    parsed = collector.get_all_sensors()
    print(f"\nParsed sensors: {len(parsed)}\n")

    for s in parsed:
        print(f"--- {s.name} (ID: {s.sensor_id}) ---")
        print(f"  Type: {s.sensor_type}")
        print(f"  Presence: {s.presence}")
        print(f"  Light level: {s.light_level}")
        print(f"  Temperature: {s.temperature}")
        print(f"  Daylight: {s.is_daylight}")
        print(f"  Button event: {s.button_event}")
        print(f"  Battery: {s.battery}%")
        print(f"  Reachable: {s.reachable}")
        print()


if __name__ == "__main__":
    main()
