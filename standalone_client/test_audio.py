"""
Unit test for AudioRecorder WAV formatting.
"""

import io
import time
import unittest
import wave
import numpy as np
from audio_recorder import AudioRecorder, SAMPLE_RATE, CHANNELS


class TestAudioRecorder(unittest.TestCase):
    def test_wav_structure_and_conversion(self):
        recorder = AudioRecorder()
        
        # Inject synthetic frames directly into frames buffer
        dummy_chunk = np.zeros((1600, 1), dtype=np.int16)  # 0.1s of audio
        recorder.frames = [dummy_chunk, dummy_chunk]
        
        wav_bytes = recorder.stop()
        self.assertGreater(len(wav_bytes), 44)  # Larger than WAV header
        
        # Parse back with standard wave module
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            self.assertEqual(wf.getnchannels(), CHANNELS)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), SAMPLE_RATE)
            self.assertEqual(wf.getnframes(), 3200)


if __name__ == "__main__":
    unittest.main()
