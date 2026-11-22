"""
Audio Recognizer & Recorder for NVDA Wispr Flow Add-on.
Uses pure Windows winmm.dll via ctypes (16kHz 16-bit Mono PCM).
Completely avoids Windows Audio Ducking so NVDA is never muted.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


class AudioRecorder:
    def __init__(self):
        self._winmm = None
        self._process = None
        if sys.platform == "win32":
            import ctypes
            self._winmm = ctypes.windll.winmm
        self.current_wav_path = None
        self.is_recording = False

    def start(self):
        unique_id = str(uuid.uuid4())
        self.current_wav_path = os.path.join(tempfile.gettempdir(), f"wispr_flow_{unique_id}.wav")

        if sys.platform != "win32":
            self._start_linux()
            self.is_recording = True
            return

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

        if sys.platform != "win32":
            if self._process is not None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
                self._process = None
            return wav_path
        if wav_path:
            self._winmm.mciSendStringW(f'save recsound "{wav_path}"', None, 0, 0)
        self._winmm.mciSendStringW("close recsound", None, 0, 0)
        return wav_path

    def _start_linux(self) -> None:
        """Record standard PCM WAV through ALSA without touching PulseAudio/PipeWire playback."""
        arecord = shutil.which("arecord")
        if arecord is None:
            raise RuntimeError(
                "Microphone recording needs the ALSA arecord command. Install alsa-utils and try again."
            )
        self._process = subprocess.Popen(
            [
                arecord,
                "--file-type=wav",
                "--format=S16_LE",
                "--rate=16000",
                "--channels=1",
                self.current_wav_path,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.1)
        if self._process.poll() is not None:
            error = self._process.stderr.read().decode(errors="replace").strip()
            self._process = None
            raise RuntimeError(f"Failed to start microphone recording: {error or 'arecord exited'}")
