"""
Wispr Flow NVDA Global Plugin.
Integrates Wispr Flow AI Voice Dictation seamlessly into NVDA.
Toggle Mode: Press once to start recording, press again to stop, transcribe, and paste.
Includes resilient audio backup and instant retry/cancel fail-safe.
"""

import ctypes
import os
import shutil
import sys
import threading
import time

# Ensure plugin directory is in sys.path
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

import globalPluginHandler
import gui
import config
import ui
import core
import scriptHandler

from .settings import WisprFlowSettingsPanel, confspec
from .sound import play_sound
from .keyboard import paste_text, type_text
from .recognizer import AudioRecorder
from .flow_client import FlowClient
from .session_store import SessionStore
from .auth import AuthManager
from .updater import check_for_updates

user32 = ctypes.windll.user32

if hasattr(config.conf, "spec"):
    config.conf.spec["wisprFlow"] = confspec


def notify(msg: str):
    if config.conf.get("wisprFlow", {}).get("voiceFeedback", True):
        core.callLater(0, ui.message, msg)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = "Wispr Flow"

    def __init__(self):
        super(GlobalPlugin, self).__init__()
        try:
            gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(WisprFlowSettingsPanel)
        except (AttributeError, ValueError):
            pass

        self.store = SessionStore()
        self.auth = AuthManager(self.store)
        self.client = FlowClient(self.store, self.auth)
        self.recognizer = AudioRecorder()

        self.lock = threading.Lock()
        self._last_toggle_time = 0.0

        # Permanent fail-safe backup audio location
        self._backup_wav_path = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "nvda",
            "last_dictation.wav"
        )
        self._pending_retry = False
        self._is_retrying = False
        self._last_fail_time = 0.0

        if config.conf.get("wisprFlow", {}).get("autoCheckUpdates", True):
            core.callLater(4000, check_for_updates, False)

    def terminate(self):
        try:
            gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(WisprFlowSettingsPanel)
        except (AttributeError, ValueError):
            pass

        if self.recognizer.is_recording:
            try:
                self.recognizer.stop()
            except Exception:
                pass
        super(GlobalPlugin, self).terminate()

    @scriptHandler.script(
        description="Toggle Wispr Flow voice dictation (Press once to start, press again to stop & paste).",
        category="Wispr Flow",
        gestures=[
            "kb:windows+space",
            "kb:leftWindows+space",
            "kb:rightWindows+space",
            "kb:control+leftWindows",
            "kb:control+rightWindows",
            "kb:windows+control",
            "kb:leftWindows+control",
            "kb:rightWindows+control",
        ]
    )
    def script_dictate(self, gesture):
        now = time.time()
        # Suppress rapid repeat events from keyboard auto-repeat (500ms debounce)
        if now - self._last_toggle_time < 0.50:
            return

        with self.lock:
            # Check if there is a failed dictation awaiting retry (within 90s)
            if self._pending_retry and os.path.isfile(self._backup_wav_path):
                if now - self._last_fail_time < 90.0:
                    if self._is_retrying:
                        # User tapped shortcut while already retrying -> CANCEL SPEECH!
                        self._is_retrying = False
                        self._pending_retry = False
                        self._last_toggle_time = now
                        if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
                            play_sound("error")
                        notify("Speech cancelled.")
                        return
                    else:
                        # User pressed shortcut to RESEND:
                        self._is_retrying = True
                        self._last_toggle_time = now
                        if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
                            play_sound("transcribing")
                        notify("Resending audio...")
                        threading.Thread(
                            target=self._process_transcription,
                            args=(self._backup_wav_path,),
                            daemon=True
                        ).start()
                        return
                else:
                    self._pending_retry = False
                    self._is_retrying = False

            # Normal dictation toggle:
            if not self.recognizer.is_recording:
                self._last_toggle_time = now
                self.start_dictation()
            else:
                self._last_toggle_time = now
                self.stop_dictation()

    @scriptHandler.script(
        description="Opens Wispr Flow settings dialog in NVDA.",
        category="Wispr Flow",
    )
    def script_settings(self, gesture):
        def _open():
            try:
                gui.mainFrame.onSettingsCommand(None)
            except Exception:
                pass
        core.callLater(0, _open)

    def start_dictation(self):
        session = self.store.get_session()
        if not session or not session.get("access_token"):
            play_sound("error")
            notify("Wispr Flow is not signed in. Open NVDA Settings -> Wispr Flow to sign in.")
            return

        try:
            self._pending_retry = False
            self._is_retrying = False
            self.recognizer.start()
            if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
                play_sound("start")
            notify("Listening...")
        except Exception as e:
            if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
                play_sound("error")
            notify(f"Microphone error: {e}")

    def stop_dictation(self):
        if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
            play_sound("transcribing")
        notify("Transcribing...")

        wav_path = self.recognizer.stop()
        if wav_path and os.path.isfile(wav_path):
            try:
                shutil.copy2(wav_path, self._backup_wav_path)
            except Exception:
                pass

        threading.Thread(
            target=self._process_transcription,
            args=(self._backup_wav_path if os.path.isfile(self._backup_wav_path) else wav_path,),
            daemon=True
        ).start()

    def _process_transcription(self, wav_path: str):
        if not wav_path or not os.path.isfile(wav_path):
            if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
                play_sound("error")
            notify("No audio captured.")
            return

        lang = config.conf.get("wisprFlow", {}).get("language", "en")
        input_method = config.conf.get("wisprFlow", {}).get("inputMethod", "paste")

        try:
            text = self.client.transcribe(wav_path, language=lang)
            if text:
                # SUCCESS! Clear retry state
                self._pending_retry = False
                self._is_retrying = False

                # Record usage statistics
                try:
                    import wave
                    duration_sec = 0.0
                    with wave.open(wav_path, "rb") as wf:
                        duration_sec = wf.getnframes() / float(wf.getframerate())
                    words = len(text.strip().split())
                    self.store.record_usage(word_count=words, audio_seconds=duration_sec)
                except Exception:
                    pass

                # 1. Paste text into the focused control first
                if input_method == "paste":
                    paste_text(text)
                else:
                    type_text(text)

                # 2. Short pause for synthetic keystrokes to complete in Windows queue
                # so NVDA's keypress speech-cancellation hook does NOT interrupt speech!
                time.sleep(0.08)

                # 3. Audio confirmation chime
                if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
                    play_sound("done")

                # 4. Speak the dictated text directly through NVDA speech and braille
                core.callLater(0, ui.message, text)
            else:
                # Actual empty speech (server succeeded but no words found)
                self._pending_retry = False
                self._is_retrying = False
                if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
                    play_sound("error")
                notify("No speech detected.")
        except Exception as e:
            # FAILURE! Keep audio intact so user never loses their speech!
            import traceback
            traceback.print_exc()
            self._pending_retry = True
            self._is_retrying = False
            self._last_fail_time = time.time()
            if config.conf.get("wisprFlow", {}).get("soundFeedback", True):
                play_sound("error")
            notify("Sorry, your request failed. Press shortcut again to resend.")
