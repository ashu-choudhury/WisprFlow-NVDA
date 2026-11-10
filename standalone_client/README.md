# Accessible Wispr Flow Client for Windows

A native, screen-reader-first desktop client for **Wispr Flow**. Built specifically for blind and visually impaired users navigating with NVDA, JAWS, or Windows Narrator.

---

## Why this client exists

The official Wispr Flow Windows application suffers from severe accessibility bugs:
1. **Audio Muting**: Opening the microphone triggers Windows Communications Ducking, reducing screen reader volume by 80% or muting it entirely.
2. **`Ctrl` Key Conflict**: The default shortcut (`Ctrl + Win`) instantly silences NVDA and JAWS speech every time it is pressed.
3. **Caret Freezing**: Floating Electron overlays disrupt the Windows UI Automation tree, freezing text edit boxes and throwing screen reader focus off.

**This client solves all three:**
* **Zero Audio Ducking**: Captures microphone audio using shared WASAPI (Normal multimedia stream). Screen readers stay at 100% volume.
* **Safe Hotkey**: Push-to-talk on <kbd>F8</kbd> (or <kbd>CapsLock</kbd>), completely eliminating <kbd>Ctrl</kbd> conflicts.
* **100% Headless**: No floating overlays. Your caret and focus stay locked in the active edit box.
* **NVDA Integration**: Speaks status announcements ("Recording...", "Transcribing...", "Done") directly into NVDA.
* **Standard User Login**: Uses standard browser sign-in. **No developer API keys required.**

---

## Quick Start

### 1. Launch the Application
Run from PowerShell or Command Prompt:
```powershell
python tools/accessible_flow/main.py
```

### 2. Sign In (First Run Only)
If you are not yet signed in:
1. The app generates a unique desktop device code and opens your browser to:
   `https://wisprflow.ai/login?device_code=<UUID>`
2. Sign in with your normal account (Google, Apple, Microsoft, or Email).
3. The browser tells Wispr Flow's server that device authentication is complete.
4. The client automatically receives your `access_token` and `refresh_token`, saves them into SQLite (`session.db`), and NVDA speaks:
   *"Wispr Flow ready. Hold F8 to dictate."*

*(If you already have a session in the official desktop app or `whisprflow-re`, the app auto-imports it without requiring browser login).*

### 3. Dictate into Any Application
1. Place your cursor into any text field (Notepad, Word, Discord, Chrome, VS Code, Outlook).
2. **Hold <kbd>F8</kbd>** and speak naturally:
   - NVDA announces *"Recording"* and plays an audio cue.
3. **Release <kbd>F8</kbd>**:
   - NVDA announces *"Transcribing"*.
   - Within seconds, your polished text is inserted directly at your cursor, and an audio chime plays.

---

## Configuration & Commands

You can inspect and customize settings via the command line:

```powershell
# Check current login and hotkey status
python tools/accessible_flow/main.py --status

# Change the dictation hotkey (e.g. F9, CapsLock, F7)
python tools/accessible_flow/main.py --set-hotkey f9
python tools/accessible_flow/main.py --set-hotkey caps_lock

# Change hotkey mode (push_to_talk or toggle)
python tools/accessible_flow/main.py --set-mode toggle
python tools/accessible_flow/main.py --set-mode push_to_talk

# Force browser re-authentication
python tools/accessible_flow/main.py --login

# Log out (clear saved SQLite tokens)
python tools/accessible_flow/main.py --logout
```

---

## Running Automated Tests

```powershell
python tools/accessible_flow/test_session_store.py
python tools/accessible_flow/test_audio.py
```
