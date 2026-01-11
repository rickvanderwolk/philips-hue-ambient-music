#!/usr/bin/env python3
"""Debug script to see what tones would be generated from lights."""

from hue_collector import HueCollector, load_config
from mapper import map_all_lamps, map_all_sensors

def main():
    config = load_config()
    if not config.get("bridge_ip"):
        print("No saved config. Run main.py first.")
        return

    collector = HueCollector(config["bridge_ip"])
    if not collector.connect():
        print("Could not connect")
        return

    lamps = collector.get_all_lights()
    sensors = collector.get_all_sensors()
    env = map_all_sensors(sensors)
    params = map_all_lamps(lamps, env)

    print("=" * 70)
    print("LIGHTS -> MUSIC MAPPING")
    print("=" * 70)

    print(f"\n{'Light':<25} {'On':<5} {'Hue':<8} {'Bri':<5} {'Freq Hz':<10} {'Note':<8} {'Vol'}")
    print("-" * 70)

    # Note names for reference
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    for lamp, p in zip(lamps, params):
        if p.playing:
            # Calculate note name
            if p.frequency > 0:
                # Find closest note
                from math import log2
                midi = 69 + 12 * log2(p.frequency / 440)
                note_idx = int(round(midi)) % 12
                octave = int(round(midi)) // 12 - 1
                note_name = f"{notes[note_idx]}{octave}"
            else:
                note_name = "-"

            print(f"{lamp.name:<25} {'ON':<5} {lamp.hue or '-':<8} {lamp.brightness:<5} {p.frequency:<10.1f} {note_name:<8} {p.amplitude:.2f}")
        else:
            print(f"{lamp.name:<25} {'off':<5} {'-':<8} {'-':<5} {'-':<10} {'-':<8} -")

    print(f"\nActive voices: {sum(1 for p in params if p.playing)}")
    print(f"Unique frequencies: {len(set(p.frequency for p in params if p.playing))}")


if __name__ == "__main__":
    main()
