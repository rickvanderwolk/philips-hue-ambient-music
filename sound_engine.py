"""Audio synthesis engine using sounddevice + numpy with composer."""

import numpy as np
import sounddevice as sd
from threading import Lock
from typing import Optional

from composer import Composer, SensorPersonality, LampPersonality
from mapper import MusicParams, EnvironmentState
from hue_collector import SensorState, LampState
from config import SAMPLE_RATE, BUFFER_SIZE


class SoundEngine:
    """Generates ambient audio using the composer."""

    def __init__(self):
        self.composer = Composer()
        self.master_volume = 0.7
        self._running = False
        self._stream: Optional[sd.OutputStream] = None
        self._lock = Lock()

    def _audio_callback(self, outdata, frames, time_info, status):
        """Generate audio samples via composer."""
        with self._lock:
            samples = self.composer.process(frames, SAMPLE_RATE)

        output = np.array(samples, dtype=np.float32) * self.master_volume
        output = np.tanh(output)
        outdata[:] = output.reshape(-1, 1)

    def start(self) -> bool:
        """Initialize and start the audio stream."""
        try:
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BUFFER_SIZE,
                channels=1,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._running = True
            return True
        except Exception as e:
            print(f"Failed to start audio: {e}")
            return False

    def stop(self):
        """Stop the audio stream."""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def update(self, params_list: list[MusicParams]):
        """Update composer from lamp parameters."""
        playing_params = [p for p in params_list if p.playing]
        frequencies = [p.frequency for p in playing_params]
        amplitudes = [p.amplitude for p in playing_params]

        scales = [p.scale_type for p in playing_params]
        scale = max(set(scales), key=scales.count) if scales else "pentatonic"

        # Create lamp personalities from metadata
        personalities = []
        for p in playing_params:
            personality = LampPersonality(
                light_id=p.light_id,
                name=p.light_name,
                model_id=p.model_id,
                light_type=p.light_type,
                unique_id=p.unique_id,
            )
            personalities.append(personality)

        with self._lock:
            self.composer.update_from_lamps(frequencies, amplitudes, scale, personalities)

    def update_sensors(self, sensors: list[SensorState]):
        """Update composer from sensor metadata."""
        # Create personalities from sensors with motion capability
        personalities = []
        for s in sensors:
            if s.presence is not None:  # Motion sensors
                p = SensorPersonality(
                    sensor_id=s.sensor_id,
                    name=s.name,
                    model=s.sensor_type,  # Using type as model proxy
                    battery=s.battery or 100,
                )
                personalities.append(p)

        with self._lock:
            self.composer.update_from_sensors(personalities)

    def update_environment(self, env: EnvironmentState):
        """Update composer from environment/sensor data."""
        with self._lock:
            self.composer.update_tempo(env.tempo_modifier)

    def trigger_percussion(self, sensor_id: int = None):
        """Trigger percussion from motion sensor."""
        with self._lock:
            self.composer.trigger_motion(sensor_id)

    def trigger_chord_change(self, button: int):
        """Trigger from button press."""
        with self._lock:
            self.composer.trigger_button(button)

    def set_master_volume(self, volume: float):
        """Set master volume (0.0 - 1.0)."""
        self.master_volume = max(0.0, min(1.0, volume))


# Alias for compatibility
SimpleSoundEngine = SoundEngine
