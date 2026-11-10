"""
Text Injection Engine for NVDA Wispr Flow Add-on.
Supports Instant Clipboard Paste (Ctrl+V) and Direct Unicode Typing.
"""

import ctypes
from ctypes import wintypes
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Win32 Constants
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
VK_CONTROL = 0x11
VK_V = 0x56

# 64-bit safe prototypes
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


def set_clipboard_text(text: str) -> bool:
    """Sets Unicode text onto the Windows clipboard cleanly without screen reader announcement."""
    if not text:
        return False

    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return False

    try:
        user32.EmptyClipboard()
        encoded = (text + "\0").encode("utf-16le")
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        ctypes.memmove(ptr, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            kernel32.GlobalFree(h_mem)
            return False
        return True
    finally:
        user32.CloseClipboard()


def paste_text(text: str):
    """
    Pastes text instantly into the focused control using Windows Clipboard and Ctrl+V.
    Does not steal focus or type character by character.
    """
    if not text:
        return

    # Set text to clipboard
    if not set_clipboard_text(text):
        # Fallback to direct typing if clipboard is locked
        type_text(text)
        return

    # Ensure any stuck modifier keys (like Win or Shift) are released before Ctrl+V
    for vk in (0x5B, 0x5C, 0x10, 0xA0, 0xA1):  # LWin, RWin, Shift
        if user32.GetAsyncKeyState(vk) & 0x8000:
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.u.ki.wVk = vk
            inp.u.ki.dwFlags = KEYEVENTF_KEYUP
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    # Allow key state and clipboard to settle
    time.sleep(0.02)

    # Synthesize Ctrl+V
    inputs = (INPUT * 4)()

    # 1. Ctrl down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].u.ki.wVk = VK_CONTROL

    # 2. V down
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].u.ki.wVk = VK_V

    # 3. V up
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].u.ki.wVk = VK_V
    inputs[2].u.ki.dwFlags = KEYEVENTF_KEYUP

    # 4. Ctrl up
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].u.ki.wVk = VK_CONTROL
    inputs[3].u.ki.dwFlags = KEYEVENTF_KEYUP

    user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))


def type_text(text: str):
    """Fallback: Injects text directly into active controls using Unicode SendInput."""
    if not text:
        return

    utf16_bytes = text.encode("utf-16-le")
    code_units = []
    for i in range(0, len(utf16_bytes), 2):
        code_units.append(utf16_bytes[i] | (utf16_bytes[i + 1] << 8))

    n_inputs = len(code_units) * 2
    input_array_cls = INPUT * n_inputs
    inputs = input_array_cls()

    idx = 0
    for code_unit in code_units:
        # Key down
        inputs[idx].type = INPUT_KEYBOARD
        inputs[idx].u.ki.wVk = 0
        inputs[idx].u.ki.wScan = code_unit
        inputs[idx].u.ki.dwFlags = KEYEVENTF_UNICODE
        idx += 1

        # Key up
        inputs[idx].type = INPUT_KEYBOARD
        inputs[idx].u.ki.wVk = 0
        inputs[idx].u.ki.wScan = code_unit
        inputs[idx].u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        idx += 1

    user32.SendInput(n_inputs, ctypes.byref(inputs), ctypes.sizeof(INPUT))
