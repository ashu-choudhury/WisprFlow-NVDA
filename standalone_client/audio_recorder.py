"""
Zero-Ducking 16kHz Audio Capture for Accessible Wispr Flow.
Captures microphone audio via standard WASAPI shared mode to prevent Windows Audio Ducking.
Outputs 16kHz Mono 16-bit PCM WAV in memory.
"""

import io
import threading
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # 16 kHz required by Wispr backend
CHANNELS = 1         # Mono
DTYPE = "int16"      # 16-bit signed PCM


class AudioRecorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.frames = []
        self.lock = threading.Lock()
        self.stream: Optional[sd.InputStream] = None

    def _audio_callback(self, indata, frame_count, time_info, status):
        """Accumulate audio frames while recording is active."""
        if self.recording:
            with self.lock:
                self.frames.append(indata.copy())

    def start(self):
        """Start capturing audio."""
        with self.lock:
            self.frames = []
            self.recording = True

        if self.stream is None:
            # Open stream with shared WASAPI mode, avoiding Communications ducking
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=DTYPE,
                callback=self._audio_callback
            )
            self.stream.start()

    def stop(self) -> bytes:
        """
        Stop recording and return captured audio as a 16kHz WAV byte buffer.
        """
        with self.lock:
            self.recording = False
            captured = list(self.frames)
            self.frames = []

        if not captured:
            return b""

        # Concatenate numpy arrays
        audio_data = np.concatenate(captured, axis=0)
        pcm_bytes = audio_data.tobytes()

        # Build in-memory 16kHz WAV
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)

        return wav_buffer.getvalue()

    def close(self):
        """Close audio device stream."""
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
