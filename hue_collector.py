"""Philips Hue data collector with auto-discovery and key storage."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from phue import Bridge, PhueRegistrationException


# Config file location
CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / ".hue_config.json"


@dataclass
class LampState:
    """Represents the state of a single Hue lamp."""

    name: str
    light_id: int
    on: bool
    brightness: int  # 0-254
    hue: Optional[int]  # 0-65535 (None for non-color lights)
    saturation: Optional[int]  # 0-254 (None for non-color lights)
    reachable: bool
    # Extended metadata
    model_id: str = ""  # e.g., LCT007, LST002, LWB010
    product_name: str = ""  # e.g., "Hue color lamp", "Hue lightstrip"
    manufacturer: str = ""
    light_type: str = ""  # e.g., "Extended color light", "Dimmable light"
    unique_id: str = ""  # MAC-based unique identifier


@dataclass
class SensorState:
    """Represents the state of a Hue sensor."""

    name: str
    sensor_id: int
    sensor_type: str  # ZLLPresence, ZLLLightLevel, ZLLTemperature, Daylight, ZLLSwitch
    # Motion sensor
    presence: Optional[bool] = None
    # Light level sensor
    light_level: Optional[int] = None  # 0-65535 (log scale lux)
    dark: Optional[bool] = None
    daylight: Optional[bool] = None
    # Temperature sensor
    temperature: Optional[int] = None  # Celsius * 100
    # Switch/button
    button_event: Optional[int] = None  # Button code
    # Daylight sensor
    is_daylight: Optional[bool] = None
    # Common
    battery: Optional[int] = None  # Battery percentage
    last_updated: Optional[str] = None
    reachable: bool = True


def discover_bridge() -> Optional[str]:
    """Auto-discover Hue Bridge on the network using mDNS/SSDP."""
    print("Searching for Hue Bridge...")

    # Method 1: Philips discovery endpoint (requires internet)
    try:
        response = requests.get("https://discovery.meethue.com", timeout=5)
        bridges = response.json()
        if bridges:
            ip = bridges[0].get("internalipaddress")
            print(f"Found bridge via Philips discovery: {ip}")
            return ip
    except Exception:
        pass

    # Method 2: Try common local IPs
    common_ips = [
        "192.168.1.1", "192.168.0.1",
        "192.168.1.2", "192.168.0.2",
        "10.0.0.1", "10.0.0.2",
    ]

    for ip in common_ips:
        try:
            response = requests.get(f"http://{ip}/api/config", timeout=1)
            if "bridgeid" in response.text.lower():
                print(f"Found bridge at: {ip}")
                return ip
        except Exception:
            continue

    print("Could not auto-discover bridge.")
    return None


def load_config() -> dict:
    """Load saved configuration."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(config: dict):
    """Save configuration to file."""
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    print(f"Config saved to {CONFIG_FILE}")


class HueCollector:
    """Collects state data from Philips Hue Bridge."""

    def __init__(self, bridge_ip: str):
        self.bridge_ip = bridge_ip
        self.bridge: Optional[Bridge] = None
        self._prev_motion: dict[int, bool] = {}  # Track motion changes
        self._prev_button: dict[int, int] = {}  # Track button presses

    @classmethod
    def auto_connect(cls) -> Optional["HueCollector"]:
        """Auto-discover bridge or use saved config.

        Returns a connected HueCollector or None if connection fails.
        """
        config = load_config()

        # Try saved IP first
        bridge_ip = config.get("bridge_ip")

        if not bridge_ip:
            # Auto-discover
            bridge_ip = discover_bridge()
            if not bridge_ip:
                # Ask user for IP
                bridge_ip = input("Enter Hue Bridge IP address: ").strip()

        if not bridge_ip:
            return None

        collector = cls(bridge_ip)

        # Try connecting with saved username
        username = config.get("username")
        if username:
            try:
                collector.bridge = Bridge(bridge_ip, username=username)
                collector.bridge.connect()
                print(f"Connected to Hue Bridge at {bridge_ip}")
                return collector
            except Exception:
                print("Saved credentials invalid, need to re-register.")

        # First time setup - wait for button press
        print("\n" + "=" * 50)
        print("FIRST TIME SETUP")
        print("=" * 50)
        print(f"\nFound Hue Bridge at: {bridge_ip}")
        print("\n>>> Press the button on your Hue Bridge <<<")
        print("\nWaiting", end="", flush=True)

        for _ in range(30):  # Try for 30 seconds
            print(".", end="", flush=True)
            try:
                collector.bridge = Bridge(bridge_ip)
                collector.bridge.connect()

                # Success! Save config
                username = collector.bridge.username
                save_config({
                    "bridge_ip": bridge_ip,
                    "username": username,
                })
                print(f"\n\nConnected! Username saved for next time.")
                return collector

            except PhueRegistrationException:
                time.sleep(1)
            except Exception as e:
                print(f"\nError: {e}")
                return None

        print("\n\nTimeout - button was not pressed.")
        return None

    def connect(self) -> bool:
        """Connect to the Hue Bridge.

        First time: press the button on your Hue Bridge before calling.
        """
        if self.bridge:
            return True

        try:
            self.bridge = Bridge(self.bridge_ip)
            self.bridge.connect()
            return True
        except Exception as e:
            print(f"Failed to connect to Hue Bridge: {e}")
            return False

    def get_all_lights(self) -> list[LampState]:
        """Get current state of all lights."""
        if not self.bridge:
            return []

        lights = []
        api = self.bridge.get_api()

        for light_id, light_data in api.get("lights", {}).items():
            state = light_data.get("state", {})
            lights.append(LampState(
                name=light_data.get("name", f"Light {light_id}"),
                light_id=int(light_id),
                on=state.get("on", False),
                brightness=state.get("bri", 0),
                hue=state.get("hue"),
                saturation=state.get("sat"),
                reachable=state.get("reachable", False),
                # Extended metadata
                model_id=light_data.get("modelid", ""),
                product_name=light_data.get("productname", ""),
                manufacturer=light_data.get("manufacturername", ""),
                light_type=light_data.get("type", ""),
                unique_id=light_data.get("uniqueid", ""),
            ))

        return lights

    def get_all_sensors(self) -> list[SensorState]:
        """Get current state of all sensors."""
        if not self.bridge:
            return []

        sensors = []
        api = self.bridge.get_api()

        for sensor_id, sensor_data in api.get("sensors", {}).items():
            sensor_type = sensor_data.get("type", "")
            state = sensor_data.get("state", {})
            config = sensor_data.get("config", {})

            sensor = SensorState(
                name=sensor_data.get("name", f"Sensor {sensor_id}"),
                sensor_id=int(sensor_id),
                sensor_type=sensor_type,
                battery=config.get("battery"),
                last_updated=state.get("lastupdated"),
                reachable=config.get("reachable", True),
            )

            # Motion/presence sensor
            if sensor_type in ("ZLLPresence", "ZHAPresence"):
                sensor.presence = state.get("presence", False)

            # Light level sensor
            elif sensor_type in ("ZLLLightLevel", "ZHALightLevel"):
                sensor.light_level = state.get("lightlevel", 0)
                sensor.dark = state.get("dark", False)
                sensor.daylight = state.get("daylight", False)

            # Temperature sensor
            elif sensor_type in ("ZLLTemperature", "ZHATemperature"):
                sensor.temperature = state.get("temperature", 0)

            # Switch/button
            elif sensor_type in ("ZLLSwitch", "ZHASwitch", "ZGPSwitch"):
                sensor.button_event = state.get("buttonevent")

            # Daylight sensor (built-in)
            elif sensor_type == "Daylight":
                sensor.is_daylight = state.get("daylight", False)

            sensors.append(sensor)

        return sensors

    def get_motion_events(self) -> list[SensorState]:
        """Get sensors where motion was just detected (edge detection)."""
        sensors = self.get_all_sensors()
        motion_events = []

        for sensor in sensors:
            if sensor.presence is not None:
                prev = self._prev_motion.get(sensor.sensor_id, False)
                if sensor.presence and not prev:
                    motion_events.append(sensor)
                self._prev_motion[sensor.sensor_id] = sensor.presence

        return motion_events

    def get_button_events(self) -> list[SensorState]:
        """Get sensors where a button was just pressed (edge detection)."""
        sensors = self.get_all_sensors()
        button_events = []

        for sensor in sensors:
            if sensor.button_event is not None:
                prev = self._prev_button.get(sensor.sensor_id)
                if sensor.button_event != prev:
                    button_events.append(sensor)
                self._prev_button[sensor.sensor_id] = sensor.button_event

        return button_events

    def get_light(self, light_id: int) -> Optional[LampState]:
        """Get state of a specific light."""
        lights = self.get_all_lights()
        for light in lights:
            if light.light_id == light_id:
                return light
        return None


# Demo/mock data for testing without actual Hue Bridge
class MockHueCollector:
    """Mock collector for testing without Hue hardware."""

    def __init__(self):
        self._time = 0
        self._prev_motion: dict[int, bool] = {}
        self._prev_button: dict[int, int] = {}

    def connect(self) -> bool:
        print("Using mock Hue data (no bridge connected)")
        return True

    def get_all_lights(self) -> list[LampState]:
        """Generate slowly changing mock light data."""
        import math
        self._time += 0.1

        return [
            LampState(
                name="Living Room",
                light_id=1,
                on=True,
                brightness=int(127 + 127 * math.sin(self._time * 0.5)),
                hue=int(32767 + 32767 * math.sin(self._time * 0.2)),
                saturation=200,
                reachable=True,
                model_id="LCT007",
                product_name="Hue color lamp",
                manufacturer="Philips",
                light_type="Extended color light",
                unique_id="00:17:88:01:00:bd:c7:b9-0b",
            ),
            LampState(
                name="Bedroom",
                light_id=2,
                on=True,
                brightness=int(127 + 127 * math.cos(self._time * 0.3)),
                hue=int(32767 + 32767 * math.cos(self._time * 0.15)),
                saturation=150,
                reachable=True,
                model_id="LST002",
                product_name="Hue lightstrip plus",
                manufacturer="Philips",
                light_type="Extended color light",
                unique_id="00:17:88:01:01:15:4a:2c-0b",
            ),
            LampState(
                name="Kitchen",
                light_id=3,
                on=self._time % 10 < 7,  # blinks occasionally
                brightness=180,
                hue=int(50000 + 15000 * math.sin(self._time * 0.1)),
                saturation=254,
                reachable=True,
                model_id="LWB010",
                product_name="Hue white lamp",
                manufacturer="Philips",
                light_type="Dimmable light",
                unique_id="00:17:88:01:02:3a:8e:12-0b",
            ),
        ]

    def get_all_sensors(self) -> list[SensorState]:
        """Generate mock sensor data."""
        import math

        # Motion triggers every ~8 seconds
        motion_active = (self._time % 8) < 0.5

        # Temperature varies slowly
        temp = int(2100 + 200 * math.sin(self._time * 0.05))  # 19-23°C

        # Light level varies
        light_level = int(20000 + 15000 * math.sin(self._time * 0.02))

        return [
            SensorState(
                name="Hallway Motion",
                sensor_id=1,
                sensor_type="ZLLPresence",
                presence=motion_active,
                battery=85,
                reachable=True,
            ),
            SensorState(
                name="Living Room Light",
                sensor_id=2,
                sensor_type="ZLLLightLevel",
                light_level=light_level,
                dark=light_level < 10000,
                daylight=light_level > 30000,
                battery=90,
                reachable=True,
            ),
            SensorState(
                name="Bedroom Temp",
                sensor_id=3,
                sensor_type="ZLLTemperature",
                temperature=temp,
                battery=75,
                reachable=True,
            ),
            SensorState(
                name="Daylight",
                sensor_id=4,
                sensor_type="Daylight",
                is_daylight=8 < (self._time % 24) < 20,
                reachable=True,
            ),
        ]

    def get_motion_events(self) -> list[SensorState]:
        """Get sensors where motion was just detected."""
        sensors = self.get_all_sensors()
        motion_events = []

        for sensor in sensors:
            if sensor.presence is not None:
                prev = self._prev_motion.get(sensor.sensor_id, False)
                if sensor.presence and not prev:
                    motion_events.append(sensor)
                self._prev_motion[sensor.sensor_id] = sensor.presence

        return motion_events

    def get_button_events(self) -> list[SensorState]:
        """No buttons in mock mode."""
        return []
