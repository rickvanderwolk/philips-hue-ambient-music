"""Maps Hue lamp and sensor data to musical parameters."""

from dataclasses import dataclass
from typing import Optional
from hue_collector import LampState, SensorState
from config import BASE_FREQUENCY, SCALE_FREQUENCIES


@dataclass
class MusicParams:
    """Musical parameters derived from lamp state."""

    frequency: float  # Hz
    amplitude: float  # 0.0 - 1.0
    playing: bool  # whether to produce sound
    scale_type: str  # major/minor/pentatonic
    reverb_amount: float  # 0.0 - 1.0
    light_name: str  # source lamp name
    # Lamp metadata for personality system
    light_id: int = 0
    model_id: str = ""
    light_type: str = ""
    unique_id: str = ""


@dataclass
class SensorParams:
    """Musical parameters derived from sensor state."""

    sensor_name: str
    sensor_type: str

    # Motion sensor -> percussion trigger
    trigger_hit: bool = False

    # Light level -> filter/brightness
    filter_cutoff: float = 1.0  # 0.0 - 1.0 (low = muffled, high = bright)

    # Temperature -> tempo modifier
    tempo_modifier: float = 1.0  # 0.8 - 1.2

    # Daylight -> ambient layer
    ambient_layer: bool = True  # True = day mode, False = night mode

    # Button -> chord change trigger
    chord_change: bool = False
    button_intensity: int = 0  # 1-4 for different buttons


@dataclass
class EnvironmentState:
    """Combined musical environment from all sensors."""

    filter_cutoff: float = 1.0
    tempo_modifier: float = 1.0
    is_daytime: bool = True
    reverb_boost: float = 0.0  # Extra reverb from dark/night
    pending_hits: list = None  # Motion triggers

    def __post_init__(self):
        if self.pending_hits is None:
            self.pending_hits = []


def hue_to_note(hue_value: int) -> int:
    """Convert Hue color value (0-65535) to semitone offset (0-11)."""
    return int((hue_value / 65535) * 12) % 12


def saturation_to_scale(saturation: int) -> str:
    """Convert saturation to scale type.

    High saturation = major (bright, happy)
    Low saturation = minor (muted, melancholic)
    """
    if saturation > 200:
        return "major"
    elif saturation > 100:
        return "pentatonic"
    else:
        return "minor"


def brightness_to_amplitude(brightness: int) -> float:
    """Convert brightness (0-254) to amplitude (0.0-1.0).

    Maps to a more musical range (not linear).
    """
    normalized = brightness / 254
    # Apply curve for more natural volume response
    # Max 0.6 per voice
    return normalized ** 0.7 * 0.6


def semitone_to_frequency(semitone: int, base_freq: float = BASE_FREQUENCY) -> float:
    """Convert semitone offset to frequency using equal temperament."""
    return base_freq * (2 ** (semitone / 12))


def light_level_to_cutoff(light_level: int) -> float:
    """Convert light level (0-65535 log scale) to filter cutoff.

    Dark = muffled (low cutoff), bright = open (high cutoff)
    """
    # Light level is logarithmic: 10000 = ~1 lux, 40000 = ~100 lux
    normalized = min(1.0, max(0.0, (light_level - 5000) / 40000))
    return 0.2 + normalized * 0.8  # Range: 0.2 - 1.0


def temperature_to_tempo(temperature: int) -> float:
    """Convert temperature (Celsius * 100) to tempo modifier.

    Cold = slower, warm = faster (subtle effect)
    """
    # temperature is in 0.01°C units, so 2000 = 20°C
    celsius = temperature / 100
    # Map 15-25°C to 0.9-1.1 tempo
    normalized = (celsius - 15) / 10
    return 0.9 + max(0.0, min(1.0, normalized)) * 0.2


def map_lamp_to_music(lamp: LampState, octave_offset: int = 0, env: Optional[EnvironmentState] = None) -> MusicParams:
    """Convert a lamp state to musical parameters.

    Args:
        lamp: The lamp state to convert
        octave_offset: Shift the note up/down by octaves (each lamp can have different octave)
        env: Environment state from sensors (affects reverb, filter, etc.)
    """
    if not lamp.on or not lamp.reachable:
        return MusicParams(
            frequency=0,
            amplitude=0,
            playing=False,
            scale_type="major",
            reverb_amount=0,
            light_name=lamp.name,
            light_id=lamp.light_id,
            model_id=lamp.model_id,
            light_type=lamp.light_type,
            unique_id=lamp.unique_id,
        )

    # Determine scale type from saturation
    scale_type = "pentatonic"  # default
    if lamp.saturation is not None:
        scale_type = saturation_to_scale(lamp.saturation)

    # Get note from hue color
    semitone = 0
    if lamp.hue is not None:
        raw_semitone = hue_to_note(lamp.hue)
        # Quantize to scale
        scale = SCALE_FREQUENCIES[scale_type]
        semitone = min(scale, key=lambda x: abs(x - raw_semitone))

    # Add octave offset
    semitone += octave_offset * 12

    frequency = semitone_to_frequency(semitone)
    amplitude = brightness_to_amplitude(lamp.brightness)

    # Apply environment filter (muffles sound when dark)
    if env:
        amplitude *= env.filter_cutoff

    # Reverb: warmer color temps = more reverb
    reverb = 0.3
    if lamp.hue is not None:
        # Red/orange hues (0-10000 and 55000-65535) get more reverb
        if lamp.hue < 10000 or lamp.hue > 55000:
            reverb = 0.6
        # Blue/cool (35000-50000) less reverb
        elif 35000 < lamp.hue < 50000:
            reverb = 0.1

    # Add extra reverb at night
    if env:
        reverb = min(1.0, reverb + env.reverb_boost)

    return MusicParams(
        frequency=frequency,
        amplitude=amplitude,
        playing=True,
        scale_type=scale_type,
        reverb_amount=reverb,
        light_name=lamp.name,
        light_id=lamp.light_id,
        model_id=lamp.model_id,
        light_type=lamp.light_type,
        unique_id=lamp.unique_id,
    )


def map_sensor_to_params(sensor: SensorState) -> SensorParams:
    """Convert a single sensor to musical parameters."""
    params = SensorParams(
        sensor_name=sensor.name,
        sensor_type=sensor.sensor_type,
    )

    # Motion sensor
    if sensor.presence is not None:
        params.trigger_hit = sensor.presence

    # Light level sensor
    if sensor.light_level is not None:
        params.filter_cutoff = light_level_to_cutoff(sensor.light_level)

    # Temperature sensor
    if sensor.temperature is not None:
        params.tempo_modifier = temperature_to_tempo(sensor.temperature)

    # Daylight sensor
    if sensor.is_daylight is not None:
        params.ambient_layer = sensor.is_daylight

    # Button/switch
    if sensor.button_event is not None:
        params.chord_change = True
        # Hue buttons: 1000=button1, 2000=button2, etc.
        params.button_intensity = (sensor.button_event // 1000) % 5

    return params


def map_all_sensors(sensors: list[SensorState]) -> EnvironmentState:
    """Combine all sensor data into environment state."""
    env = EnvironmentState()

    light_levels = []
    temperatures = []
    is_day = None

    for sensor in sensors:
        params = map_sensor_to_params(sensor)

        # Collect light levels (average them)
        if sensor.light_level is not None:
            light_levels.append(params.filter_cutoff)

        # Collect temperatures (average them)
        if sensor.temperature is not None:
            temperatures.append(params.tempo_modifier)

        # Daylight (use first found)
        if sensor.is_daylight is not None and is_day is None:
            is_day = sensor.is_daylight

    # Average light levels
    if light_levels:
        env.filter_cutoff = sum(light_levels) / len(light_levels)

    # Average temperatures
    if temperatures:
        env.tempo_modifier = sum(temperatures) / len(temperatures)

    # Set day/night mode
    if is_day is not None:
        env.is_daytime = is_day
        if not is_day:
            env.reverb_boost = 0.2  # More reverb at night

    return env


def map_all_lamps(lamps: list[LampState], env: Optional[EnvironmentState] = None) -> list[MusicParams]:
    """Map all lamps to music, assigning different octaves.

    Creates a layered arrangement where each lamp plays in a different register.
    """
    params = []
    # Wider octave spread: -2, -1, 0, +1, +2 (5 octaves range)
    octave_pattern = [-2, -1, 0, 1, 2]

    for i, lamp in enumerate(lamps):
        octave = octave_pattern[i % len(octave_pattern)]
        params.append(map_lamp_to_music(lamp, octave_offset=octave, env=env))
    return params
