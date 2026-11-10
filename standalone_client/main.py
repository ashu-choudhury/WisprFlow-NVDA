"""
Accessible Wispr Flow Client for Windows.
Main orchestrator: Global hotkey listener, zero-ducking audio capture,
direct NVDA/JAWS feedback, and clean focus-preserving text injection.
"""

import argparse
import sys
import threading
import time

from pynput import keyboard

from accessibility import AccessibilityManager
from audio_recorder import AudioRecorder
from auth_manager import AuthManager
from flow_client import FlowClient
from session_store import SessionStore


def parse_hotkey(key_str: str) -> keyboard.Key | keyboard.KeyCode:
    """Convert string key name to pynput Key."""
    key_lower = key_str.lower().strip()
    key_map = {
        "f1": keyboard.Key.f1,
        "f2": keyboard.Key.f2,
        "f3": keyboard.Key.f3,
        "f4": keyboard.Key.f4,
        "f5": keyboard.Key.f5,
        "f6": keyboard.Key.f6,
        "f7": keyboard.Key.f7,
        "f8": keyboard.Key.f8,
        "f9": keyboard.Key.f9,
        "f10": keyboard.Key.f10,
        "f11": keyboard.Key.f11,
        "f12": keyboard.Key.f12,
        "caps_lock": keyboard.Key.caps_lock,
        "scroll_lock": keyboard.Key.scroll_lock,
        "pause": keyboard.Key.pause,
    }
    return key_map.get(key_lower, keyboard.Key.f8)


class AccessibleFlowApp:
    def __init__(self):
        self.store = SessionStore()
        self.auth = AuthManager(self.store)
        self.accessibility = AccessibilityManager(
            enable_speech=(self.store.get_setting("speech_feedback", "true") == "true"),
            enable_sounds=(self.store.get_setting("sound_cues", "true") == "true"),
        )
        self.recorder = AudioRecorder()
        self.client = FlowClient(self.store, self.auth)

        self.hotkey_name = self.store.get_setting("hotkey", "f8")
        self.target_key = parse_hotkey(self.hotkey_name)
        self.mode = self.store.get_setting("hotkey_mode", "push_to_talk")
        self.language = self.store.get_setting("language", "en")
        self.style = self.store.get_setting("writing_style", "default")

        self.is_recording = False
        self.key_pressed = False
        self.lock = threading.Lock()

    def ensure_authenticated(self) -> bool:
        """Check login status, auto-discover or launch browser sign-in."""
        session = self.store.get_session()
        if session and session.get("access_token"):
            email = session.get("email") or "Active User"
            print(f"[Auth] Logged in as: {email}")
            return True

        print("\n[Auth] No active session found in SQLite.")
        print("[Auth] Checking for existing desktop login...")
        if self.auth.auto_discover_desktop_session():
            return True

        print("\n" + "=" * 60)
        print("  WISPR FLOW STANDARD BROWSER SIGN-IN")
        print("  Zero API keys required. Authenticate normally in your browser.")
        print("=" * 60)

        success = self.auth.start_browser_login()
        if success:
            self.accessibility.speak("Sign in successful")
            return True
        else:
            self.accessibility.speak("Sign in failed")
            return False

    def on_press(self, key):
        if key == self.target_key:
            with self.lock:
                if self.mode == "push_to_talk":
                    if not self.is_recording:
                        self.is_recording = True
                        self.key_pressed = True
                        self._start_capture()
                elif self.mode == "toggle":
                    if not self.is_recording:
                        self.is_recording = True
                        self._start_capture()
                    else:
                        self.is_recording = False
                        self._stop_and_transcribe()

    def on_release(self, key):
        if key == self.target_key:
            with self.lock:
                if self.mode == "push_to_talk":
                    if self.is_recording:
                        self.is_recording = False
                        self.key_pressed = False
                        self._stop_and_transcribe()

    def _start_capture(self):
        """Begin audio capture with speech and sound cues."""
        self.accessibility.play_sound("start")
        self.accessibility.speak("Recording")
        self.recorder.start()
        print("\n[Flow] >> Recording voice... Speak naturally.")

    def _stop_and_transcribe(self):
        """Stop audio capture and dispatch transcription in background."""
        self.accessibility.play_sound("transcribing")
        self.accessibility.speak("Transcribing")
        wav_bytes = self.recorder.stop()
        print("[Flow] >> Processing audio with Wispr AI...")

        # Process in separate worker thread to avoid blocking keyboard hook
        threading.Thread(target=self._transcribe_worker, args=(wav_bytes,), daemon=True).start()

    def _transcribe_worker(self, wav_bytes: bytes):
        if not wav_bytes:
            self.accessibility.play_sound("error")
            self.accessibility.speak("No audio captured")
            return

        text = self.client.transcribe(
            wav_bytes,
            language=self.language,
            style=self.style
        )

        if text:
            print(f"[Flow] Dictated text: \"{text}\"")
            self.accessibility.inject_text(text)
            self.accessibility.play_sound("done")
        else:
            print("[Flow] No transcription returned.")
            self.accessibility.play_sound("error")
            self.accessibility.speak("Transcription failed")

    def run(self):
        """Start global hotkey listener and background runner."""
        if not self.ensure_authenticated():
            print("[App] Cannot run without authentication. Exiting.")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("  ACCESSIBLE WISPR FLOW IS ACTIVE")
        print(f"  Hotkey : {self.hotkey_name.upper()} ({self.mode.replace('_', ' ')})")
        print(f"  Audio  : Shared WASAPI 16kHz (Zero Ducking / Full Screen Reader Volume)")
        print(f"  Speech : Connected to NVDA / Screen Reader")
        print("  Press Ctrl+C to exit.")
        print("=" * 60 + "\n")

        self.accessibility.speak(f"Wispr Flow ready. Hold {self.hotkey_name.upper()} to dictate.")

        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print("\n[App] Shutting down Accessible Wispr Flow...")
                self.recorder.close()
                self.accessibility.speak("Wispr Flow stopped")


def main():
    parser = argparse.ArgumentParser(description="Accessible Wispr Flow Desktop Client")
    parser.add_argument("--login", action="store_true", help="Force interactive browser login")
    parser.add_argument("--logout", action="store_true", help="Clear saved SQLite session tokens")
    parser.add_argument("--status", action="store_true", help="Show current login and configuration status")
    parser.add_argument("--set-hotkey", type=str, help="Set dictation hotkey (e.g. f8, f9, caps_lock)")
    parser.add_argument("--set-mode", type=str, choices=["push_to_talk", "toggle"], help="Set hotkey mode")
    parser.add_argument("--set-language", type=str, help="Set spoken language (e.g. en, hi, hi_en, auto)")
    args = parser.parse_args()

    store = SessionStore()

    if args.logout:
        store.clear_session()
        print("[App] Successfully logged out and cleared session from SQLite.")
        return

    if args.set_hotkey:
        store.set_setting("hotkey", args.set_hotkey.lower())
        print(f"[App] Dictation hotkey updated to: {args.set_hotkey.upper()}")
        return

    if args.set_mode:
        store.set_setting("hotkey_mode", args.set_mode)
        print(f"[App] Hotkey mode updated to: {args.set_mode}")
        return

    if args.set_language:
        store.set_setting("language", args.set_language.lower())
        print(f"[App] Spoken language updated to: {args.set_language.upper()}")
        return

    if args.status:
        session = store.get_session()
        print("\n--- Accessible Wispr Flow Status ---")
        if session:
            email = session.get("email") or "Logged in"
            exp = store.is_token_expired()
            print(f"Account: {email}")
            print(f"Token status: {'Expired (will auto-refresh)' if exp else 'Valid'}")
        else:
            print("Account: Not logged in")
        print(f"Hotkey: {store.get_setting('hotkey', 'f8').upper()}")
        print(f"Mode: {store.get_setting('hotkey_mode', 'push_to_talk')}")
        print(f"Language: {store.get_setting('language', 'en')}")
        return

    app = AccessibleFlowApp()
    if args.login:
        app.auth.start_browser_login()
        return

    app.run()


if __name__ == "__main__":
    main()
