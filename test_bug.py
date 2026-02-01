
import unittest
import os
from main import process_audio, play_audio
from record import speech_to_text

class TestBug(unittest.TestCase):
    def test_play_audio_exists(self):
        try:
            self.assertTrue(callable(play_audio))
        except AttributeError:
            self.fail("play_audio function does not exist in main.py")

    def test_process_audio_returns_valid_path(self):
        # Create a dummy audio file
        with open("test_audio.wav", "w") as f:
            f.write("dummy audio data")

        # Call process_audio with the dummy file
        _, _, _, audio_path = process_audio("test_audio.wav", "")

        # Check if the returned path is valid
        self.assertTrue(os.path.exists(audio_path))

        # Clean up the dummy file
        os.remove("test_audio.wav")

if __name__ == '__main__':
    unittest.main()
