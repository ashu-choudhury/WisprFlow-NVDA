"""
Accessibility & Speech Engine for Accessible Wispr Flow.
Provides direct screen reader speech (NVDA), audio cues (chimes),
and seamless, focus-preserving text injection into active edit controls.
"""

import ctypes
import os
import time
import winsound
from typing import Optional

import pyperclip
from pynput.keyboard import Controller, Key


class AccessibilityManager:
    def __init__(self, enable_speech: bool = True, enable_sounds: bool = True):
        self.enable_speech = enable_speech
        self.enable_sounds = enable_sounds
        self.nvda_dll = self._load_nvda_dll()
        self.keyboard_controller = Controller()

    def _load_nvda_dll(self) -> Optional[ctypes.WinDLL]:
        """Attempt to locate and load nvdaControllerClient DLL."""
        candidate_paths = [
            r"C:\Program Files\Bookworm\_internal\accessible_output2\lib\nvdaControllerClient64.dll",
            r"C:\Program Files\NVDA\nvdaControllerClient64.dll",
            r"C:\Program Files (x86)\NVDA\nvdaControllerClient32.dll",
            r"C:\Program Files (x86)\BGT\redist\screen_readers\nvda\nvdaControllerClient32.dll",
            os.path.join(os.path.dirname(__file__), "nvdaControllerClient64.dll"),
            os.path.join(os.path.dirname(__file__), "nvdaControllerClient32.dll"),
        ]
        for path in candidate_paths:
            if os.path.isfile(path):
                try:
                    dll = ctypes.windll.LoadLibrary(path)
                    return dll
                except Exception:
                    continue
        return None

    def speak(self, text: str):
        """Announce text directly through NVDA or screen reader."""
        if not self.enable_speech or not text:
            return

        if self.nvda_dll:
            try:
                # nvdaController_speakText accepts LPCWSTR
                self.nvda_dll.nvdaController_speakText(str(text))
                return
            except Exception:
                pass

        # Fallback: Print to console
        print(f"[Speech] {text}")

    def play_sound(self, sound_type: str):
        """Play short, distinct audio cues for state transitions."""
        if not self.enable_sounds:
            return

        try:
            if sound_type == "start":
                # Upward short beep
                winsound.Beep(850, 70)
            elif sound_type == "transcribing":
                # Neutral tick
                winsound.Beep(1050, 50)
            elif sound_type == "done":
                # High pleasant confirmation
                winsound.Beep(1300, 90)
            elif sound_type == "error":
                # Low warning buzz
                winsound.Beep(400, 150)
        except Exception:
            pass

    def inject_text(self, text: str):
        """
        Inserts text directly into the focused edit box.
        Preserves existing clipboard, pastes cleanly via Ctrl+V,
        and restores the user's prior clipboard without stealing window focus.
        """
        if not text:
            return

        try:
            # Backup current clipboard
            try:
                old_clipboard = pyperclip.paste()
            except Exception:
                old_clipboard = ""

            # Copy transcribed text to clipboard
            pyperclip.copy(text)

            # Fire synthetic Ctrl+V without opening any overlay window
            time.sleep(0.02)
            with self.keyboard_controller.pressed(Key.ctrl):
                self.keyboard_controller.press("v")
                self.keyboard_controller.release("v")

            # Restore original clipboard after short delay
            time.sleep(0.06)
            try:
                pyperclip.copy(old_clipboard)
            except Exception:
                pass

        except Exception as e:
            print(f"[Accessibility] Error injecting text: {e}")
