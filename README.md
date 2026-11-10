# Wispr Flow for NVDA

**Accessible, High-Accuracy AI Voice Dictation for the NVDA Screen Reader**

Wispr Flow for NVDA brings the power of **Wispr Flow AI** (`wisprflow.ai`) directly into Windows for blind and visually impaired users. It provides lightning-fast, context-aware speech-to-text with zero audio ducking, direct speech confirmation, clean HTML-to-text formatting, and instantaneous clipboard pasting.

---

## Key Features

- **Zero Audio Ducking (100% Volume Always)**: Windows Communications Audio Ducking is completely bypassed. Your screen reader (NVDA, JAWS, or SAPI) will never be silenced, lowered, or muted while dictating.
- **Reliable Toggle Mode**: Press once to start listening, speak naturally for as long as you want, and press once again to stop. Includes hardware debounce to prevent accidental toggles from keyboard repeat.
- **Direct Speech Confirmation**: The moment transcription completes, NVDA immediately speaks what was recognized through your synthesizer and displays it on Braille displays so you always know what was typed.
- **Instant Clipboard Pasting**: Text is placed on the Windows clipboard and inserted instantly via <kbd>Ctrl + V</kbd>. No character-by-character typing lag or cursor jitter.
- **Clean Text Formatting (Zero HTML Clutter)**: Automatically detects and transforms HTML structures (such as `<ol><li>...</li></ol>` into clean numbered lists `1. ...\n2. ...` and `<ul>` into clean bullet points), unescaping entities (`&amp;`, `&quot;`) so your documents and code remain clean.
- **No Developer API Keys Needed**: Log in normally using your standard web browser (Google, Apple, or Email). Tokens are saved locally in `%APPDATA%\nvda\wisprFlow_session.json` using pure JSON (fully compatible with NVDA's Python runtime without `sqlite3` dependency).
- **Fully Customizable Shortcuts**: Easily change or add shortcuts through NVDA's built-in Input Gestures dialog.

---

## Default Shortcuts

| Shortcut | Action |
|---|---|
| <kbd>Windows + Space</kbd> | Toggle Dictation (Start / Stop & Paste) |
| <kbd>Ctrl + Windows</kbd> | Alternate Toggle Dictation |

> **Tip**: You can customize these shortcuts anytime by going to **NVDA Menu (<kbd>NVDA + N</kbd>) &rarr; Preferences &rarr; Input Gestures &rarr; Wispr Flow**.

---

## Installation

### Option 1: Install from Add-on Package
1. Download or locate `wisprFlow-1.0.0.nvda-addon`.
2. Press <kbd>Enter</kbd> on the file or open it with NVDA.
3. Confirm the installation prompt and restart NVDA when prompted.

### Option 2: Install from Source
Run the included build script with the `--install` flag:
```powershell
python build_addon.py --install
```
Then restart NVDA (<kbd>Ctrl + Alt + N</kbd>).

---

## How to Use

1. **Sign In**:
   - Open **NVDA Menu (<kbd>NVDA + N</kbd>) &rarr; Preferences &rarr; Settings &rarr; Wispr Flow**.
   - Click **Sign In via Browser...**.
   - Complete your sign-in in your default web browser. Once finished, NVDA will announce that sign-in succeeded.
2. **Dictate Anywhere**:
   - Move your focus into any text box, edit field, terminal, or document (Notepad, Word, Chrome, Discord, Slack, etc.).
   - Press <kbd>Windows + Space</kbd> (or <kbd>Ctrl + Windows</kbd>). You will hear a start chime and NVDA will say *"Listening..."*.
   - Speak your sentence naturally.
   - Press <kbd>Windows + Space</kbd> again. You will hear the chime, NVDA will announce the transcribed text, and it will be pasted directly into the field!

---

## Settings & Preferences

Open **NVDA Settings (<kbd>NVDA + Ctrl + G</kbd>) &rarr; Wispr Flow**:

- **Account Status**: View your logged-in email and Sign In / Sign Out buttons.
- **Text Insertion Method**:
  - *Paste via Clipboard (Instant, Recommended)*: Pastes all text at once with focus intact.
  - *Type character-by-character (Legacy)*: Types characters one by one using synthetic input.
- **Spoken Language**: Choose between English, Hindi, Hinglish (Hindi + English), Spanish, French, German, or Auto-detect.
- **Play Sound Effects**: Toggle audio cue beeps on/off.
- **Speak Status Notifications**: Toggle spoken status announcements ("Listening...", "Transcribing...") on/off.

---

## Architecture & Technical Overview

```
wisprFlow/
├── manifest.ini                       # NVDA Add-on Metadata
├── build_addon.py                     # Automatic packager and installer
└── globalPlugins/
    └── wisprFlow/
        ├── __init__.py                # GlobalPlugin lifecycle & gesture engine
        ├── settings.py                # wxPython settings panel under NVDA Preferences
        ├── auth.py                    # Official device-code OAuth flow (api.wisprflow.ai)
        ├── session_store.py           # Pure JSON token storage (%APPDATA%\nvda\wisprFlow_session.json)
        ├── recognizer.py              # Pure winmm.dll 16kHz 16-bit Mono WAV capture (zero ducking)
        ├── keyboard.py                # 64-bit safe Win32 clipboard paste & SendInput engine
        ├── sound.py                   # NVDA tones.beep / winsound audio cues
        ├── flow_client.py             # Runtime gRPC client loader & session manager
        ├── wisprflow/
        │   ├── protocol.py            # Protobuf request encoders & clean HTML-to-text parser
        │   ├── client.py              # Robust route & auth facade
        │   └── models.py              # Strong typing for routes, languages, and options
        └── lib/
            ├── py311/                 # Bundled grpcio wheels for Python 3.11
            ├── py312/                 # Bundled grpcio wheels for Python 3.12
            └── py313/                 # Bundled grpcio wheels for Python 3.13 (modern NVDA)
```

- **Backend Route**: Communicates directly with Wispr Flow's official edge inference servers at `inference.wisprflow.com:443` via gRPC streaming (`/flow_api.v1.TranscriptionService/TranscribeStream`).
- **Audio Capture**: Utilizes Windows Multimedia (`winmm.dll`) MCI waveaudio directly into 16kHz mono linear PCM WAV bytes, ensuring zero ducking and zero dependency on PyAudio or PortAudio.

---

## Standalone Python Client

In addition to the NVDA add-on, a standalone cross-platform Python CLI client is available in `standalone_client/`:
```powershell
cd standalone_client
python main.py
```

---

## License

MIT License. Designed with accessibility at the core for blind and visually impaired pilots and developers.
