#!/usr/bin/env python3
"""Ambient Music Generator - Creates music from Philips Hue lamp states and sensors."""

import time
import argparse
import sys
from datetime import datetime

from hue_collector import HueCollector, MockHueCollector
from mapper import map_all_lamps, map_all_sensors
from sound_engine import SoundEngine
from config import POLL_INTERVAL

# Note names for display
NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def freq_to_note(freq: float) -> str:
    """Convert frequency to note name."""
    if freq <= 0:
        return "-"
    from math import log2
    midi = 69 + 12 * log2(freq / 440)
    note_idx = int(round(midi)) % 12
    octave = int(round(midi)) // 12 - 1
    return f"{NOTES[note_idx]}{octave}"


# Display width (inner content width, total box width = WIDTH + 2 for borders)
WIDTH = 83


def truncate(s: str, max_len: int) -> str:
    """Truncate string to max length with ellipsis."""
    if len(s) <= max_len:
        return s
    return s[:max_len-1] + "…"


def box_line(content: str) -> str:
    """Format a line inside a box with proper padding. Total width = WIDTH + 2."""
    return f"│ {content:<{WIDTH-1}}│"


def box_top(title: str) -> str:
    """Format top border with title. Total width = WIDTH + 2."""
    padding = WIDTH - len(title) - 1
    return f"┌─{title}{'─' * padding}┐"


def box_bottom() -> str:
    """Format bottom border. Total width = WIDTH + 2."""
    return "└" + "─" * WIDTH + "┘"


def box_separator() -> str:
    """Format separator line. Total width = WIDTH + 2."""
    return "│" + "-" * WIDTH + "│"


def print_status(params_list, env, sensors, engine, bridge_ip: str = "", last_poll: str = "", poll_count: int = 0):
    """Print current status to terminal with clear input->output mapping."""
    print("\033[H\033[J", end="")  # Clear screen

    composer = engine.composer
    bpm = composer.sequencer.bpm
    lamp_pers = composer.lamp_personalities

    total_width = WIDTH + 2  # Total box width including borders
    print("=" * total_width)
    title = "AMBIENT MUSIC GENERATOR"
    padding = (total_width - len(title)) // 2
    print(" " * padding + title)
    print("=" * total_width)

    # Connection info
    print("\n" + box_top("CONNECTION "))
    bridge_display = bridge_ip if bridge_ip else "(mock mode)"
    print(box_line(f"Bridge: {bridge_display:<20} Last poll: {last_poll:<12} Polls: {poll_count}"))
    print(box_bottom())

    # === LIGHTS SECTION ===
    print("\n" + box_top("LIGHTS → DRONE VOICES "))
    print(box_line(f"{'Name':<14} {'Model':<8} {'→Wave':<8} {'Char':<8} {'Note':<6} {'Vol':<5} {'Scale':<10}"))
    print(box_separator())

    for i, p in enumerate(params_list):
        name = truncate(p.light_name, 14)
        model = truncate(p.model_id, 8) if p.model_id else "-"

        # Get personality info if available
        wave = "-"
        char = "-"
        if i < len(lamp_pers):
            wave = truncate(lamp_pers[i].waveform, 8)
            char = truncate(lamp_pers[i].character, 8)

        if p.playing:
            note = freq_to_note(p.frequency)
            print(box_line(f"{name:<14} {model:<8} {wave:<8} {char:<8} {note:<6} {p.amplitude:.2f}  {p.scale_type:<10}"))
        else:
            print(box_line(f"{name:<14} {model:<8} {'-':<8} {'-':<8} {'-':<6} {'-':<5} {'-':<10}"))
    print(box_bottom())

    # === SENSOR PERSONALITIES SECTION ===
    print("\n" + box_top("MOTION SENSORS → MELODY VOICES "))
    print(box_line(f"{'Name':<16} {'ID':<4} {'Pattern':<8} {'Bat':<5} {'Nerv':<6} {'Category':<10} {'Sound':<10}"))
    print(box_separator())

    for p in composer.sensor_personalities:
        name = truncate(p.name, 16)
        nerv_bar = "!" * int(p.nervousness * 5) + "·" * (5 - int(p.nervousness * 5))
        cat = truncate(getattr(p, 'sensor_category', 'motion'), 10)
        print(box_line(f"{name:<16} {p.sensor_id:<4} {p.pattern_type:<8} {p.battery:>3}%  {nerv_bar:<6} {cat:<10} {p.instrument_type:<10}"))

    if not composer.sensor_personalities:
        print(box_line("(no motion sensors)"))

    print(box_bottom())

    # === ENVIRONMENT SECTION ===
    print("\n" + box_top("ENVIRONMENT SENSORS → MUSIC FEEL "))

    # Temperature
    temp_sensors = [s for s in sensors if s.temperature is not None]
    if temp_sensors:
        avg_temp = sum(s.temperature for s in temp_sensors) / len(temp_sensors) / 100
        print(box_line(f"Temperature: {avg_temp:.1f}°C  ──→  BPM: {bpm:.0f} (warm=fast, cold=slow)"))
    else:
        print(box_line(f"Temperature: -        ──→  BPM: {bpm:.0f} (default)"))

    # Battery -> Nervousness
    avg_batt = composer.avg_battery
    avg_nerv = composer.avg_nervousness
    speed = "fast" if avg_nerv > 0.5 else "normal" if avg_nerv > 0.2 else "slow"
    print(box_line(f"Avg Battery: {avg_batt:.0f}%     ──→  Nervousness: {avg_nerv:.1%} → arp={speed}"))

    # Light level
    light_sensors = [s for s in sensors if s.light_level is not None]
    if light_sensors:
        avg_light = sum(s.light_level for s in light_sensors) / len(light_sensors)
        filter_desc = "bright" if env.filter_cutoff > 0.7 else "muffled" if env.filter_cutoff < 0.4 else "normal"
        print(box_line(f"Light Level: {avg_light:.0f}    ──→  Filter: {filter_desc}"))

    # Daylight
    daylight = next((s for s in sensors if s.is_daylight is not None), None)
    if daylight:
        mode = "Day (less reverb)" if daylight.is_daylight else "Night (+reverb)"
        print(box_line(f"Daylight: {daylight.is_daylight}    ──→  {mode}"))

    print(box_bottom())

    # === CURRENT OUTPUT SECTION ===
    print("\n" + box_top("CURRENT OUTPUT "))

    # Drone
    drone_notes = [freq_to_note(f) for f in composer.drone.frequencies[:6] if f > 0]
    print(box_line(f"DRONE:    {', '.join(drone_notes) if drone_notes else '-'}"))

    # Arp
    arp_patterns = ["up-down", "extended", "alternating", "repeated"]
    arp_name = arp_patterns[composer.arp.current_pattern % len(arp_patterns)]
    arp_notes = [freq_to_note(f) for f in composer.arp.notes[:4]]
    print(box_line(f"ARP:      pattern={arp_name}, notes={', '.join(arp_notes) if arp_notes else '-'}"))

    # Melody voices
    active_voices = [(sid, v) for sid, v in composer.melody.voices.items() if v.envelope > 0.01]
    if active_voices:
        voice_str = ", ".join(f"{truncate(v.personality.name, 10)}:{freq_to_note(v.current_freq)}" for sid, v in active_voices[:4])
        print(box_line(f"MELODY:   {voice_str}"))
    else:
        print(box_line("MELODY:   (waiting for trigger)"))

    print(box_line(f"BPM:      {bpm:.0f}  |  Beat: {composer.sequencer.current_beat:.1f}"))
    print(box_bottom())

    # === TRIGGERS ===
    print("\n" + box_top("LIVE TRIGGERS "))
    motion_active = [s for s in sensors if s.presence]
    motion_total = len([s for s in sensors if s.presence is not None])
    print(box_line(f"Motion: {len(motion_active)}/{motion_total} active → triggers melody note + kick"))
    print(box_line("Button: press dimmer → changes arp pattern"))
    print(box_bottom())

    print("\n[Ctrl+C to stop]")


def main():
    parser = argparse.ArgumentParser(description="Generate ambient music from Philips Hue")
    parser.add_argument("--mock", action="store_true", help="Use mock data (no Hue Bridge needed)")
    parser.add_argument("--quiet", action="store_true", help="Don't print status")
    args = parser.parse_args()

    # Initialize Hue collector
    if args.mock:
        collector = MockHueCollector()
    else:
        collector = HueCollector.auto_connect()
        if collector is None:
            print("Could not connect to Hue Bridge. Use --mock for demo mode.")
            sys.exit(1)

    collector.connect()

    # Initialize sound engine
    engine = SoundEngine()

    if not engine.start():
        print("Failed to start audio engine")
        sys.exit(1)

    print("Ambient Music Generator started!")
    print("Listening to your lights and sensors...\n")

    # Track connection errors and stats
    consecutive_errors = 0
    max_errors = 5
    last_lamps = []
    last_sensors = []
    last_env = None
    last_params = []
    poll_count = 0
    last_poll = ""

    # Get bridge IP for display
    bridge_ip = getattr(collector, 'bridge_ip', '')

    try:
        while True:
            try:
                # Get current lamp states
                lamps = collector.get_all_lights()

                # Get current sensor states
                sensors = collector.get_all_sensors()

                # Update poll stats
                poll_count += 1
                last_poll = datetime.now().strftime("%H:%M:%S")

                # Reset error counter on success
                consecutive_errors = 0

                # Cache last known good state
                last_lamps = lamps
                last_sensors = sensors

                # Map sensors to environment
                env = map_all_sensors(sensors)
                last_env = env

                # Update sensor personalities in engine
                engine.update_sensors(sensors)

                # Check for motion events (edge detection)
                motion_events = collector.get_motion_events()
                for event in motion_events:
                    engine.trigger_percussion(sensor_id=event.sensor_id)

                # Check for button events
                button_events = collector.get_button_events()
                for event in button_events:
                    if event.button_event:
                        button_num = (event.button_event // 1000) % 5
                        engine.trigger_chord_change(button_num)

                # Map lamps to musical parameters (with environment effects)
                params = map_all_lamps(lamps, env)
                last_params = params

                # Update sound engine
                engine.update(params)
                engine.update_environment(env)

                # Display status
                if not args.quiet:
                    print_status(params, env, sensors, engine, bridge_ip, last_poll, poll_count)

            except (ConnectionResetError, ConnectionError, OSError) as e:
                consecutive_errors += 1
                if not args.quiet:
                    print(f"\033[H\033[J", end="")  # Clear screen
                    print(f"⚠ Connection error ({consecutive_errors}/{max_errors}): {e}")
                    print("Retrying... (music continues with last known state)")

                if consecutive_errors >= max_errors:
                    print(f"\nToo many connection errors. Check your Hue Bridge.")
                    break

                # Use cached state to keep music going
                if last_params and last_env:
                    engine.update(last_params)
                    engine.update_environment(last_env)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        engine.stop()
        print("Goodbye!")


if __name__ == "__main__":
    main()
