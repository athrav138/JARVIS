import numpy as np
from scipy.io.wavfile import write

# Set the parameters for the sine wave
frequency = 440  # Hz (A4 note)
duration = 5  # seconds
sample_rate = 44100  # Hz

# Generate the time values
t = np.linspace(0, duration, int(sample_rate * duration), False)

# Generate the sine wave
sine_wave = 0.5 * np.sin(2 * np.pi * frequency * t)

# Convert to 16-bit data
sine_wave_16bit = np.int16(sine_wave * 32767)

# Write the sine wave to a .wav file
write("music/placeholder.wav", sample_rate, sine_wave_16bit)
