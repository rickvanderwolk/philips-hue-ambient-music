"""Configuration for Ambient Music generator.

All Hue Bridge settings (IP, API key) are auto-discovered and stored
in .hue_config.json which is gitignored.
"""

# Audio settings
SAMPLE_RATE = 44100
BUFFER_SIZE = 512

# Polling interval in seconds (2x per second)
POLL_INTERVAL = 0.5

# Musical settings
BASE_FREQUENCY = 261.63  # C4
SCALE_FREQUENCIES = {
    "major": [0, 2, 4, 5, 7, 9, 11],  # semitone intervals
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "pentatonic": [0, 2, 4, 7, 9],
}
