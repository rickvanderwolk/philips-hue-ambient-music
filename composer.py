"""Generative music composer - creates evolving music from Hue data."""

import time
import random
import math
from dataclasses import dataclass, field
from typing import Optional, List
from config import BASE_FREQUENCY, SCALE_FREQUENCIES


@dataclass
class Note:
    """A single note to be played."""
    frequency: float
    velocity: float  # 0-1
    duration: float  # seconds
    start_time: float


@dataclass
class LampPersonality:
    """Musical personality derived from lamp metadata."""
    light_id: int
    name: str
    model_id: str
    light_type: str
    unique_id: str

    # Derived musical properties
    waveform: str = "sine"  # sine, saw, triangle, square, warm, bell, pad
    octave_offset: int = 0  # -2 to +2
    richness: float = 0.5  # 0-1, harmonic content
    attack: float = 0.1  # Attack time modifier
    character: str = "neutral"  # warm, bright, deep, sparkle, soft, airy
    product_type: str = "bulb"  # bulb, strip, bar, spot, bloom, outdoor, plug

    def __post_init__(self):
        model = self.model_id.upper() if self.model_id else ""

        # === COLOR BULBS (E27/E26/GU10) ===
        # LCT series: Original color bulbs - rich, warm, full sound
        # LCT001, LCT007, LCT010, LCT011, LCT014, LCT015, LCT016
        if model.startswith("LCT"):
            self.waveform = "warm"
            self.richness = 0.7
            self.character = "warm"
            self.product_type = "bulb"

        # LCA series: Newer color bulbs - similar but slightly brighter
        # LCA001, LCA003, LCA006
        elif model.startswith("LCA"):
            self.waveform = "warm"
            self.richness = 0.75
            self.character = "bright"
            self.product_type = "bulb"

        # === LIGHTSTRIPS ===
        # LST series: Lightstrips - sparkly, spread, ambient
        # LST001 (original), LST002 (plus), LST003/LST004 (gradient)
        elif model.startswith("LST"):
            self.waveform = "saw"
            self.richness = 0.8
            self.character = "sparkle"
            self.product_type = "strip"
            # Gradient strips are extra shimmery
            if model in ("LST003", "LST004"):
                self.richness = 0.9

        # === WHITE BULBS ===
        # LWB series: White only - pure, simple, clean
        # LWB004, LWB006, LWB010, LWB014
        elif model.startswith("LWB"):
            self.waveform = "sine"
            self.richness = 0.25
            self.character = "neutral"
            self.product_type = "bulb"

        # LWA series: Newer white - similar
        elif model.startswith("LWA"):
            self.waveform = "sine"
            self.richness = 0.3
            self.character = "soft"
            self.product_type = "bulb"

        # === AMBIANCE (WHITE TEMPERATURE) ===
        # LTW/LTA series: Adjustable white temp - soft, warm
        # LTW001, LTW004, LTW010, LTW012, LTA001, LTA003
        elif model.startswith(("LTW", "LTA")):
            self.waveform = "triangle"
            self.richness = 0.5
            self.character = "warm"
            self.product_type = "bulb"

        # === SPOTS / DOWNLIGHTS ===
        # LCG series: GU10 spots - focused, bright
        # LCG002, LCG001
        elif model.startswith("LCG"):
            self.waveform = "triangle"
            self.richness = 0.6
            self.character = "bright"
            self.product_type = "spot"

        # LCF series: Fuzo outdoor spot - deep, focused
        elif model.startswith("LCF"):
            self.waveform = "triangle"
            self.richness = 0.55
            self.character = "deep"
            self.product_type = "spot"

        # === PLAY BARS / GRADIENT ===
        # LCX series: Play bars - modern, punchy, rhythmic
        # LCX001, LCX002, LCX003
        elif model.startswith("LCX"):
            self.waveform = "square"
            self.richness = 0.65
            self.character = "deep"
            self.product_type = "bar"

        # === BLOOM / IRIS / ACCENT ===
        # LLC series: Bloom, Iris, Friends of Hue
        # LLC010 (Iris), LLC011 (Bloom), LLC012 (Bloom), LLC020 (Go)
        elif model.startswith("LLC"):
            self.waveform = "bell"
            self.richness = 0.7
            self.character = "airy"
            self.product_type = "bloom"
            # Iris is more ethereal
            if model == "LLC010":
                self.richness = 0.8
                self.character = "sparkle"

        # === OUTDOOR ===
        # LCL series: Outdoor lights - deep, atmospheric
        # LCL001 (Lily spot), LCL002
        elif model.startswith("LCL"):
            self.waveform = "pad"
            self.richness = 0.5
            self.character = "deep"
            self.product_type = "outdoor"
            self.octave_offset = -1

        # LCS series: Outdoor strip - spread, ambient
        elif model.startswith("LCS"):
            self.waveform = "saw"
            self.richness = 0.6
            self.character = "sparkle"
            self.product_type = "outdoor"

        # LWO series: White outdoor
        elif model.startswith("LWO"):
            self.waveform = "sine"
            self.richness = 0.35
            self.character = "soft"
            self.product_type = "outdoor"

        # === SMART PLUGS ===
        # LOM series: Smart plugs - percussive, on/off
        # LOM001, LOM002
        elif model.startswith("LOM"):
            self.waveform = "square"
            self.richness = 0.2
            self.character = "neutral"
            self.product_type = "plug"

        # === SIGNE / FLOOR LAMPS ===
        # LCT024: Signe floor lamp - elegant, vertical sound
        elif model == "LCT024":
            self.waveform = "triangle"
            self.richness = 0.65
            self.character = "airy"
            self.product_type = "floor"

        # === DEFAULT ===
        # Check light_type as fallback
        elif "outdoor" in self.light_type.lower():
            self.waveform = "pad"
            self.richness = 0.4
            self.character = "deep"
            self.product_type = "outdoor"
        elif "color" in self.light_type.lower():
            self.waveform = "warm"
            self.richness = 0.6
            self.character = "warm"
        else:
            self.waveform = "sine"
            self.richness = 0.5
            self.character = "neutral"

        # Light ID -> octave spread (keep voices separated)
        self.octave_offset = (self.light_id % 5) - 2  # -2 to +2

        # Use unique_id hash for subtle per-lamp variations
        if self.unique_id:
            hash_val = sum(ord(c) for c in self.unique_id)
            self.attack = 0.05 + (hash_val % 10) * 0.02  # 0.05-0.25
            # Small richness variation per lamp
            self.richness += ((hash_val % 20) - 10) * 0.01

        # Light type modifiers
        if "Extended color" in self.light_type:
            self.richness = min(1.0, self.richness + 0.15)
        elif "Dimmable" in self.light_type:
            self.richness = max(0.15, self.richness - 0.1)


@dataclass
class SensorPersonality:
    """Musical personality derived from sensor metadata."""
    sensor_id: int
    name: str
    model: str
    battery: int

    # Derived musical properties
    melody_seed: int = 0
    instrument_type: str = "sine"  # sine, bell, pluck, pad, chime, mallet, string
    nervousness: float = 0.0  # 0-1, affects speed/variation
    pattern_type: str = "walk"  # walk, up, down, zigzag, jump, repeat, chord, trill
    sensor_category: str = "motion"  # motion, switch, button, temp, light, daylight

    def __post_init__(self):
        # Use sensor_id as seed for consistent personality
        self.melody_seed = self.sensor_id
        model = self.model.upper() if self.model else ""

        # === MOTION SENSORS ===
        # SML001: Indoor motion sensor - soft, atmospheric pad
        if "SML001" in model:
            self.instrument_type = "pad"
            self.sensor_category = "motion"

        # SML002: Outdoor motion sensor - bell-like, alerting
        elif "SML002" in model:
            self.instrument_type = "bell"
            self.sensor_category = "motion"

        # SML003: Newer motion sensor
        elif "SML003" in model:
            self.instrument_type = "pad"
            self.sensor_category = "motion"

        # SML004: Motion sensor lite
        elif "SML004" in model:
            self.instrument_type = "chime"
            self.sensor_category = "motion"

        # === DIMMER SWITCHES ===
        # RWL020, RWL021, RWL022: Dimmer switch v1/v2 - plucky, responsive
        elif model.startswith("RWL"):
            self.instrument_type = "pluck"
            self.sensor_category = "switch"

        # === SMART BUTTONS ===
        # ROM001: Smart button - single hit, mallet sound
        elif "ROM001" in model:
            self.instrument_type = "mallet"
            self.sensor_category = "button"

        # ZGPSWITCH: Hue Tap (4-button, no battery) - percussive
        elif "ZGPSWITCH" in model:
            self.instrument_type = "pluck"
            self.sensor_category = "button"
            self.nervousness = 0.0  # No battery to worry about

        # === TEMPERATURE SENSORS (built into motion sensors) ===
        elif "TEMPERATURE" in model or "ZLLTemperature" in model:
            self.instrument_type = "string"
            self.sensor_category = "temp"

        # === LIGHT LEVEL SENSORS (built into motion sensors) ===
        elif "LIGHTLEVEL" in model or "ZLLLightLevel" in model:
            self.instrument_type = "chime"
            self.sensor_category = "light"

        # === DAYLIGHT SENSOR (software sensor) ===
        elif "DAYLIGHT" in model.upper():
            self.instrument_type = "pad"
            self.sensor_category = "daylight"

        # === PRESENCE SENSORS ===
        elif "PRESENCE" in model or "ZLLPresence" in model or "ZHAPresence" in model:
            self.instrument_type = "pad"
            self.sensor_category = "motion"

        # === DEFAULT ===
        else:
            self.instrument_type = "sine"

        # Battery -> nervousness (low battery = more nervous/erratic)
        if self.battery is None or self.sensor_category == "button":
            # Tap switches have no battery
            self.nervousness = 0.1
        elif self.battery <= 10:
            self.nervousness = 1.0  # Critical!
        elif self.battery <= 20:
            self.nervousness = 0.8
        elif self.battery <= 35:
            self.nervousness = 0.5
        elif self.battery <= 50:
            self.nervousness = 0.3
        else:
            self.nervousness = 0.1

        # Sensor ID -> pattern type (consistent per sensor)
        # More patterns for variety
        patterns = ["walk", "up", "down", "zigzag", "jump", "repeat", "chord", "trill"]
        self.pattern_type = patterns[self.sensor_id % len(patterns)]

        # Adjust pattern based on sensor type
        if self.sensor_category == "button":
            # Buttons are more rhythmic
            self.pattern_type = ["chord", "jump", "trill"][self.sensor_id % 3]
        elif self.sensor_category == "temp":
            # Temperature changes slowly
            self.pattern_type = ["walk", "up", "down"][self.sensor_id % 3]


class Sequencer:
    """Central clock for timing all musical events."""

    def __init__(self, bpm: float = 72):
        self.bpm = bpm
        self.start_time = time.time()
        self._last_beat = -1

    @property
    def beat_duration(self) -> float:
        """Duration of one beat in seconds."""
        return 60.0 / self.bpm

    @property
    def current_time(self) -> float:
        """Time since start in seconds."""
        return time.time() - self.start_time

    @property
    def current_beat(self) -> float:
        """Current beat number (can be fractional)."""
        return self.current_time / self.beat_duration

    def set_tempo(self, bpm: float):
        """Change tempo (clamped to reasonable range)."""
        self.bpm = max(40, min(120, bpm))

    def is_new_beat(self, subdivision: int = 1) -> bool:
        """Check if we've crossed a beat boundary."""
        current = int(self.current_beat * subdivision)
        if current > self._last_beat:
            self._last_beat = current
            return True
        return False


class DroneLayer:
    """Slow evolving drone chords from lamp colors with lamp-specific timbres."""

    def __init__(self):
        self.frequencies: list[float] = []
        self.target_frequencies: list[float] = []
        self.amplitudes: list[float] = []
        self.target_amplitudes: list[float] = []
        self.phases: list[float] = []
        self.lfo_phase = 0.0
        self.lfo_speed = 0.15
        self.lamp_personalities: list[LampPersonality] = []

    def update_from_lamps(self, lamp_frequencies: list[float], lamp_amplitudes: list[float],
                          personalities: list[LampPersonality] = None):
        """Update drone targets from lamp data."""
        self.target_frequencies = lamp_frequencies[:6]
        self.target_amplitudes = lamp_amplitudes[:6]
        self.lamp_personalities = personalities[:6] if personalities else []

        while len(self.frequencies) < len(self.target_frequencies):
            self.frequencies.append(self.target_frequencies[len(self.frequencies)])
            self.amplitudes.append(0.0)
            self.phases.append(random.random() * 2 * math.pi)

    def _generate_waveform(self, phase: float, waveform: str, richness: float) -> float:
        """Generate a sample based on waveform type."""
        if waveform == "sine":
            return math.sin(phase)
        elif waveform == "saw":
            # Sawtooth with harmonics based on richness
            sample = 0.0
            for h in range(1, int(4 + richness * 6)):
                sample += math.sin(phase * h) / h
            return sample * 0.5
        elif waveform == "triangle":
            # Triangle approximation
            sample = math.sin(phase)
            sample += math.sin(phase * 3) / 9 * richness
            return sample
        elif waveform == "square":
            # Soft square (filtered)
            sample = math.sin(phase)
            sample += math.sin(phase * 3) / 3 * richness
            sample += math.sin(phase * 5) / 5 * richness * 0.5
            return sample * 0.7
        elif waveform == "warm":
            # Warm: fundamental + subtle even harmonics
            sample = math.sin(phase) * 0.7
            sample += math.sin(phase * 2) * 0.2 * richness
            sample += math.sin(phase * 0.5) * 0.3  # Sub-octave
            return sample
        elif waveform == "bell":
            # Bell: inharmonic partials for metallic sound
            sample = math.sin(phase) * 0.5
            sample += math.sin(phase * 2.4) * 0.3 * richness
            sample += math.sin(phase * 5.95) * 0.15 * richness
            sample += math.sin(phase * 8.2) * 0.05 * richness
            return sample
        elif waveform == "pad":
            # Pad: detuned unison for thick sound
            sample = math.sin(phase) * 0.4
            sample += math.sin(phase * 1.002) * 0.3  # Slight detune
            sample += math.sin(phase * 0.998) * 0.3  # Other direction
            sample += math.sin(phase * 0.5) * 0.2 * richness  # Sub
            return sample
        return math.sin(phase)

    def get_samples(self, num_samples: int, sample_rate: int) -> list[float]:
        """Generate drone samples with lamp-specific timbres."""
        if not self.frequencies:
            return [0.0] * num_samples

        output = [0.0] * num_samples
        lfo_inc = self.lfo_speed * 2 * math.pi / sample_rate

        for i in range(num_samples):
            self.lfo_phase += lfo_inc
            lfo = 0.7 + 0.3 * math.sin(self.lfo_phase)

            sample = 0.0
            for j, freq in enumerate(self.frequencies):
                if j >= len(self.target_frequencies):
                    break

                self.frequencies[j] += (self.target_frequencies[j] - freq) * 0.0001
                target_amp = self.target_amplitudes[j] if j < len(self.target_amplitudes) else 0
                self.amplitudes[j] += (target_amp - self.amplitudes[j]) * 0.001

                self.phases[j] += 2 * math.pi * self.frequencies[j] / sample_rate

                # Use lamp personality for timbre if available
                if j < len(self.lamp_personalities):
                    p = self.lamp_personalities[j]
                    wave_sample = self._generate_waveform(self.phases[j], p.waveform, p.richness)
                else:
                    wave_sample = math.sin(self.phases[j])

                sample += wave_sample * self.amplitudes[j] * lfo * 0.25

            output[i] = sample

        return output


class ArpLayer:
    """Arpeggiator that cycles through chord notes."""

    def __init__(self):
        self.notes: list[float] = []
        self.pattern_idx = 0
        self.current_note = 0.0
        self.phase = 0.0
        self.envelope = 0.0
        self.patterns = [
            [0, 1, 2, 1],
            [0, 1, 2, 3, 2, 1],
            [0, 2, 1, 3],
            [0, 0, 1, 2],
        ]
        self.current_pattern = 0

    def update_notes(self, frequencies: list[float]):
        """Update available notes from lamp frequencies."""
        self.notes = sorted(set(f for f in frequencies if f > 0))[:4]

    def trigger_next(self):
        """Move to next note in pattern."""
        if not self.notes:
            return

        pattern = self.patterns[self.current_pattern % len(self.patterns)]
        note_idx = pattern[self.pattern_idx % len(pattern)]

        if note_idx < len(self.notes):
            self.current_note = self.notes[note_idx]
            self.envelope = 1.0

        self.pattern_idx += 1

    def get_samples(self, num_samples: int, sample_rate: int) -> list[float]:
        """Generate arpeggio samples."""
        if self.current_note <= 0:
            return [0.0] * num_samples

        output = [0.0] * num_samples

        for i in range(num_samples):
            self.envelope *= 0.9997

            if self.envelope > 0.01:
                self.phase += 2 * math.pi * self.current_note / sample_rate
                sample = math.sin(self.phase) * 0.7
                sample += math.sin(self.phase * 2) * 0.2
                sample += math.sin(self.phase * 3) * 0.1
                output[i] = sample * self.envelope * 0.35

        return output


class MelodyVoice:
    """A single melody voice with its own personality."""

    def __init__(self, personality: SensorPersonality):
        self.personality = personality
        self.scale = SCALE_FREQUENCIES["pentatonic"]
        self.root_freq = BASE_FREQUENCY
        self.current_degree = 2
        self.current_freq = 0.0
        self.phase = 0.0
        self.envelope = 0.0
        self.octave = 1

        # Pattern state
        self.pattern_position = 0
        self.pattern_direction = 1

        # Use sensor ID as random seed for consistent behavior
        self.rng = random.Random(personality.melody_seed)

    def set_scale(self, scale_type: str, root_freq: float):
        """Set the scale and root note."""
        self.scale = SCALE_FREQUENCIES.get(scale_type, SCALE_FREQUENCIES["pentatonic"])
        self.root_freq = root_freq

    def trigger_note(self):
        """Trigger a new note based on personality pattern."""
        pattern = self.personality.pattern_type
        nervousness = self.personality.nervousness

        # More nervous = more variation
        if self.rng.random() < nervousness:
            # Random jump
            step = self.rng.choice([-3, -2, 2, 3])
        else:
            # Follow pattern
            if pattern == "walk":
                step = self.rng.choice([-1, 0, 1])
            elif pattern == "up":
                step = 1 if self.rng.random() > 0.3 else -1
            elif pattern == "down":
                step = -1 if self.rng.random() > 0.3 else 1
            elif pattern == "zigzag":
                step = self.pattern_direction
                self.pattern_direction *= -1
            elif pattern == "jump":
                step = self.rng.choice([-2, 2])
            elif pattern == "repeat":
                step = 0 if self.rng.random() > 0.4 else self.rng.choice([-1, 1])
            elif pattern == "chord":
                # Chord: jump by thirds/fifths
                step = self.rng.choice([0, 2, 4, -2, -4])
            elif pattern == "trill":
                # Trill: alternate between two adjacent notes
                step = 1 if self.pattern_position % 2 == 0 else -1
            else:
                step = 0

        self.current_degree = max(0, min(len(self.scale) - 1, self.current_degree + step))

        semitone = self.scale[self.current_degree]
        self.current_freq = self.root_freq * (2 ** (semitone / 12)) * (2 ** self.octave)
        self.envelope = 1.0
        self.pattern_position += 1

    def get_samples(self, num_samples: int, sample_rate: int) -> list[float]:
        """Generate melody samples with instrument-specific timbre."""
        if self.current_freq <= 0 or self.envelope < 0.01:
            return [0.0] * num_samples

        output = [0.0] * num_samples
        instrument = self.personality.instrument_type

        # Decay rate based on instrument
        if instrument == "pluck":
            decay = 0.9995
        elif instrument == "bell":
            decay = 0.9998
        elif instrument == "pad":
            decay = 0.99995
        elif instrument == "chime":
            decay = 0.9997
        elif instrument == "mallet":
            decay = 0.9993
        elif instrument == "string":
            decay = 0.99992
        else:
            decay = 0.9999

        for i in range(num_samples):
            self.envelope *= decay

            if self.envelope > 0.01:
                self.phase += 2 * math.pi * self.current_freq / sample_rate

                # Instrument-specific timbre
                if instrument == "bell":
                    # Bell: fundamental + inharmonic partials
                    sample = math.sin(self.phase) * 0.5
                    sample += math.sin(self.phase * 2.4) * 0.3
                    sample += math.sin(self.phase * 5.95) * 0.2
                elif instrument == "pluck":
                    # Pluck: bright attack, quick decay
                    sample = math.sin(self.phase) * 0.6
                    sample += math.sin(self.phase * 2) * 0.25
                    sample += math.sin(self.phase * 3) * 0.15
                elif instrument == "chime":
                    # Chime: bright, high partials
                    sample = math.sin(self.phase) * 0.4
                    sample += math.sin(self.phase * 3) * 0.25
                    sample += math.sin(self.phase * 5) * 0.2
                    sample += math.sin(self.phase * 7) * 0.15
                elif instrument == "mallet":
                    # Mallet: woody, quick attack
                    sample = math.sin(self.phase) * 0.7
                    sample += math.sin(self.phase * 4) * 0.2
                    sample += math.sin(self.phase * 0.5) * 0.1
                elif instrument == "string":
                    # String: warm, sustained with vibrato feel
                    sample = math.sin(self.phase) * 0.6
                    sample += math.sin(self.phase * 2) * 0.2
                    sample += math.sin(self.phase * 3) * 0.1
                    sample += math.sin(self.phase * 1.01) * 0.1  # Slight chorus
                elif instrument == "pad":
                    # Pad: soft, warm
                    sample = math.sin(self.phase) * 0.8
                    sample += math.sin(self.phase * 0.5) * 0.2  # Sub
                else:
                    # Sine: pure
                    sample = math.sin(self.phase)

                output[i] = sample * self.envelope * 0.4

        return output


class MelodyLayer:
    """Multi-voice generative melody system."""

    def __init__(self):
        self.voices: dict[int, MelodyVoice] = {}  # sensor_id -> voice
        self.active_scale = "pentatonic"
        self.root_freq = BASE_FREQUENCY

        # Global state
        self.total_nervousness = 0.0
        self.complexity = 0  # Number of active voices

    def update_personalities(self, personalities: list[SensorPersonality]):
        """Update melody voices from sensor personalities."""
        # Create/update voices for each sensor
        active_ids = set()
        total_nerv = 0.0

        for p in personalities:
            active_ids.add(p.sensor_id)
            total_nerv += p.nervousness

            if p.sensor_id not in self.voices:
                self.voices[p.sensor_id] = MelodyVoice(p)

            # Update scale
            self.voices[p.sensor_id].set_scale(self.active_scale, self.root_freq)

        self.total_nervousness = total_nerv / len(personalities) if personalities else 0
        self.complexity = len(personalities)

    def set_scale(self, scale_type: str, root_freq: float):
        """Set scale for all voices."""
        self.active_scale = scale_type
        self.root_freq = root_freq
        for voice in self.voices.values():
            voice.set_scale(scale_type, root_freq)

    def trigger_random_voice(self):
        """Trigger a note on a random voice."""
        if self.voices:
            voice = random.choice(list(self.voices.values()))
            voice.trigger_note()

    def trigger_by_sensor(self, sensor_id: int):
        """Trigger note on specific sensor's voice."""
        if sensor_id in self.voices:
            self.voices[sensor_id].trigger_note()

    def get_samples(self, num_samples: int, sample_rate: int) -> list[float]:
        """Generate combined melody samples from all voices."""
        output = [0.0] * num_samples

        # Mix all active voices
        active_count = 0
        for voice in self.voices.values():
            if voice.envelope > 0.01:
                active_count += 1
                voice_samples = voice.get_samples(num_samples, sample_rate)
                for i in range(num_samples):
                    output[i] += voice_samples[i]

        # Normalize if multiple voices
        if active_count > 1:
            scale = 1.0 / math.sqrt(active_count)
            output = [s * scale for s in output]

        return output


class PercussionLayer:
    """Simple percussion sounds."""

    def __init__(self):
        self.kick_envelope = 0.0
        self.kick_freq = 60.0
        self.kick_phase = 0.0
        self.hat_envelope = 0.0
        self.hat_noise = 0.0

    def trigger_kick(self):
        """Trigger kick drum."""
        self.kick_envelope = 1.0
        self.kick_freq = 150.0

    def trigger_hat(self):
        """Trigger hi-hat."""
        self.hat_envelope = 0.5

    def get_samples(self, num_samples: int, sample_rate: int) -> list[float]:
        """Generate percussion samples."""
        output = [0.0] * num_samples

        for i in range(num_samples):
            sample = 0.0

            if self.kick_envelope > 0.01:
                self.kick_envelope *= 0.997
                self.kick_freq *= 0.999
                self.kick_freq = max(40, self.kick_freq)
                self.kick_phase += 2 * math.pi * self.kick_freq / sample_rate
                sample += math.sin(self.kick_phase) * self.kick_envelope * 0.5

            if self.hat_envelope > 0.01:
                self.hat_envelope *= 0.995
                noise = random.random() * 2 - 1
                self.hat_noise = self.hat_noise * 0.7 + noise * 0.3
                sample += self.hat_noise * self.hat_envelope * 0.25

            output[i] = sample

        return output


class Composer:
    """Main composer that combines all layers."""

    def __init__(self):
        self.sequencer = Sequencer(bpm=72)
        self.drone = DroneLayer()
        self.arp = ArpLayer()
        self.melody = MelodyLayer()
        self.percussion = PercussionLayer()

        # Timing
        self.last_arp_beat = -1
        self.last_melody_beat = -1
        self.arp_subdivision = 2
        self.melody_interval = 4

        # State
        self.active_scale = "pentatonic"
        self.sensor_personalities: list[SensorPersonality] = []
        self.lamp_personalities: list[LampPersonality] = []
        self.avg_battery = 100
        self.avg_nervousness = 0.0

    def update_from_lamps(self, frequencies: list[float], amplitudes: list[float],
                          scale: str = "pentatonic", personalities: list[LampPersonality] = None):
        """Update all layers from lamp data."""
        self.lamp_personalities = personalities or []
        self.drone.update_from_lamps(frequencies, amplitudes, self.lamp_personalities)
        self.arp.update_notes(frequencies)
        self.active_scale = scale

        if frequencies:
            root = min(f for f in frequencies if f > 0) if any(f > 0 for f in frequencies) else BASE_FREQUENCY
            self.melody.set_scale(scale, root)

    def update_from_sensors(self, personalities: list[SensorPersonality]):
        """Update from sensor metadata."""
        self.sensor_personalities = personalities
        self.melody.update_personalities(personalities)

        if personalities:
            self.avg_battery = sum(p.battery for p in personalities) / len(personalities)
            self.avg_nervousness = sum(p.nervousness for p in personalities) / len(personalities)

            # Adjust arp speed based on nervousness
            if self.avg_nervousness > 0.5:
                self.arp_subdivision = 4  # Faster
                self.melody_interval = 2
            elif self.avg_nervousness > 0.2:
                self.arp_subdivision = 2  # Normal
                self.melody_interval = 4
            else:
                self.arp_subdivision = 1  # Slower
                self.melody_interval = 8

    def update_tempo(self, tempo_modifier: float):
        """Update tempo from sensor data."""
        base_bpm = 72
        # Also factor in nervousness
        nervousness_boost = 1 + (self.avg_nervousness * 0.3)
        self.sequencer.set_tempo(base_bpm * tempo_modifier * nervousness_boost)

    def trigger_motion(self, sensor_id: int = None):
        """Handle motion sensor trigger."""
        if sensor_id and sensor_id in self.melody.voices:
            self.melody.trigger_by_sensor(sensor_id)
        else:
            self.melody.trigger_random_voice()

        if random.random() < 0.3:
            self.percussion.trigger_kick()

    def trigger_button(self, button: int):
        """Handle button press."""
        self.percussion.trigger_hat()
        self.arp.current_pattern = button % len(self.arp.patterns)

    def process(self, num_samples: int, sample_rate: int) -> list[float]:
        """Generate mixed audio samples."""
        # Timed events
        current_beat = int(self.sequencer.current_beat * self.arp_subdivision)
        if current_beat > self.last_arp_beat:
            self.last_arp_beat = current_beat
            self.arp.trigger_next()

        melody_beat = int(self.sequencer.current_beat / self.melody_interval)
        if melody_beat > self.last_melody_beat:
            self.last_melody_beat = melody_beat
            # Trigger chance based on nervousness
            trigger_chance = 0.3 + (self.avg_nervousness * 0.4)
            if random.random() < trigger_chance:
                self.melody.trigger_random_voice()

        # Generate all layers
        drone_out = self.drone.get_samples(num_samples, sample_rate)
        arp_out = self.arp.get_samples(num_samples, sample_rate)
        melody_out = self.melody.get_samples(num_samples, sample_rate)
        perc_out = self.percussion.get_samples(num_samples, sample_rate)

        # Mix
        output = []
        for i in range(num_samples):
            mixed = drone_out[i] + arp_out[i] + melody_out[i] + perc_out[i]
            output.append(mixed)

        return output
