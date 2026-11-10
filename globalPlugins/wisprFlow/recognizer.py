"""
Audio Recognizer & Recorder for NVDA Wispr Flow Add-on.
Uses pure Windows winmm.dll via ctypes (16kHz 16-bit Mono PCM).
Completely avoids Windows Audio Ducking so NVDA is never muted.
"""

import ctypes
import os
import tempfile
import uuid


class AudioRecorder:
    def __init__(self):
        self._winmm = ctypes.windll.winmm
        self.current_wav_path = None
        self.is_recording = False

    def start(self):
        unique_id = str(uuid.uuid4())
        self.current_wav_path = os.path.join(tempfile.gettempdir(), f"wispr_flow_{unique_id}.wav")

        self._winmm.mciSendStringW("close recsound", None, 0, 0)
        err = self._winmm.mciSendStringW("open new type waveaudio alias recsound", None, 0, 0)
        if err:
            raise RuntimeError("Failed to open microphone device.")

        # Configure 16,000 Hz, 16-bit, Mono (2 bytes per sample, 32,000 bytes per second)
        err = self._winmm.mciSendStringW(
            "set recsound time format ms bitspersample 16 channels 1 samplespersec 16000 bytespersec 32000 alignment 2",
            None, 0, 0
        )
        if err:
            self._winmm.mciSendStringW("close recsound", None, 0, 0)
            raise RuntimeError("Failed to set 16kHz audio format.")

        err = self._winmm.mciSendStringW("record recsound", None, 0, 0)
        if err:
            self._winmm.mciSendStringW("close recsound", None, 0, 0)
            raise RuntimeError("Failed to start recording.")

        self.is_recording = True

    def stop(self) -> str:
        self.is_recording = False
        wav_path = self.current_wav_path
        self.current_wav_path = None

        if wav_path:
            self._winmm.mciSendStringW(f'save recsound "{wav_path}"', None, 0, 0)
        self._winmm.mciSendStringW("close recsound", None, 0, 0)
        return wav_path
