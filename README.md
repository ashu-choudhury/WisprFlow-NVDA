# Wispr Flow for NVDA

**Ultra-lightweight, 100% accessible AI voice dictation add-on for the NVDA screen reader.**  
Powered by [Wispr Flow AI](https://wisprflow.ai).

Developed by **Ashutosh Chaudhary** ([@ashu-choudhury](https://github.com/ashu-choudhury)).

---

## Why This Add-on Exists (The Problem with Official Wispr Flow)

[Wispr Flow](https://wisprflow.ai) provides exceptional speech recognition and AI context-aware text formatting. However, the official Windows desktop app is fundamentally inaccessible and problematic for blind and visually impaired users:

1. **Destructive Audio Ducking (Silences Screen Readers)**:  
   The official Wispr Flow desktop app triggers Windows Communication Audio Ducking, attenuating or completely muting system audio whenever the microphone is active. For screen reader users (NVDA, JAWS), this silences the speech synthesizer, making it impossible to hear what you are doing, verify cursor position, or receive audio feedback while dictating.
2. **Resource-Heavy Electron Bloat**:  
   The official application is packaged with Chromium/Electron, consuming hundreds of megabytes (and often gigabytes) of RAM, running multiple persistent background helper processes, and causing CPU spikes even when idle.
3. **Focus Loss & Field Glitches**:  
   Its floating HUD window often intercepts or steals keyboard focus, breaks input focus in terminal emulators (PowerShell, WSL), and causes missed keystrokes when typing into code editors or rich web controls.
4. **Daemon Dependency**:  
   Requires a continuous background daemon and system tray application to be running at all times.

---

## The Solution: Wispr Flow for NVDA

This add-on connects NVDA directly to Wispr Flow's neural transcription servers via low-level gRPC streaming, offering a native, lightning-fast, and completely accessible experience:

- **Zero Audio Ducking (100% Screen Reader Volume)**:  
  Uses native low-level shared WASAPI capture (`winmm.dll`). Screen reader audio is never lowered, muted, or ducked. You can speak and listen to NVDA at the exact same time.
- **Ultra-Lightweight (< 10 MB RAM, 0% CPU Idle)**:  
  Runs natively inside NVDA's existing Python engine. No Electron, no browser windows, no extra background processes.
- **Uses Your Existing Wispr Flow Account**:  
  Sign in once via your default web browser using Wispr's official OAuth device code flow. Works with your regular account (free or paid) — **no developer API keys, credit cards, or credit limits required**.
- **Long Speech Handling (5+ Minute Dictations)**:  
  Wispr Flow's gRPC servers reject audio payloads larger than 4 MB. This add-on features an intelligent audio segmenter that splits long speeches into safe, valid RIFF WAV chunks (~60s each) and stitches the transcribed text seamlessly.
- **Fail-Safe Audio Protection (Never Lose Your Speech)**:  
  Audio is always saved locally to `%APPDATA%\nvda\last_dictation.wav` before uploading. If your internet disconnects or the request fails, NVDA announces:  
  > *"Sorry, your request failed. Press shortcut again to resend."*  
  Pressing the shortcut immediately resends the saved audio without making you speak again!
- **Clean Text & List Formatting (Zero HTML Clutter)**:  
  Wispr's AI often formats structured thoughts into HTML tags (`<ol><li>...</li></ol>`, `<ul>`, `<p>`). This add-on automatically detects and transforms HTML into clean, human-readable plain text:
  ```
  1. First item
  2. Second item
  - Bullet item
  ```
- **Instant Clipboard Insertion (<kbd>Ctrl + V</kbd>)**:  
  Inserts transcribed text instantly using high-speed clipboard pasting. Preserves control focus, works across all text areas, and prevents typing lag.
- **Direct Speech Feedback & Braille Output**:  
  Speaks the transcribed text aloud immediately after insertion so you know exactly what was written, with full Braille display mirroring.
- **Toggle Dictation Mode**:  
  Simple, reliable toggle mode: press once to start recording, speak naturally, and press again to transcribe and insert. Includes a 500ms hardware debounce to prevent accidental double-toggles.

---

## Default Shortcuts

| Shortcut | Description |
|---|---|
| <kbd>Windows + Space</kbd> | Toggle Dictation (Start recording / Stop, transcribe & paste) |
| <kbd>Ctrl + Windows</kbd> | Alternate Toggle Dictation |

> **Customization**: You can customize these shortcuts anytime via **NVDA Menu (<kbd>NVDA + N</kbd>) &rarr; Preferences &rarr; Input Gestures &rarr; Wispr Flow**.

---

## Compatibility

- **Minimum NVDA Version**: 2024.1 (Python 3.11+)
- **Tested & Verified Versions**: NVDA 2024.x, NVDA 2025.x, NVDA 2026.2 (Python 3.13 64-bit)
- **Supported Operating Systems**: Windows 10, Windows 11 (AMD64)

---

## Quick Start Guide

### 1. Installation

1. Download the latest `wisprFlow-1.0.0.nvda-addon` from [Releases](https://github.com/ashu-choudhury/WisprFlow-NVDA/releases).
2. Open the file in Windows or press <kbd>Enter</kbd> to install it into NVDA.
3. Restart NVDA when prompted.

*(Or build and install from source using `python build_addon.py --install`)*.

### 2. Sign In to Your Wispr Flow Account

1. Press <kbd>NVDA + N</kbd> &rarr; **Preferences** &rarr; **Settings** &rarr; **Wispr Flow**.
2. Tab to the **"Sign In via Browser..."** button and press <kbd>Enter</kbd> or <kbd>Space</kbd>.
3. Your default web browser will open to Wispr Flow's authorization page.
4. Log in with Google, Apple, or Email and click **Approve**.
5. Return to NVDA — NVDA will announce: *"Successfully signed in to Wispr Flow as [Your Name]"*.

### 3. Start Dictating

1. Focus on any text field (Notepad, Word, Discord, browser, terminal, Visual Studio Code, etc.).
2. Press <kbd>Windows + Space</kbd>. You will hear an activation chime and NVDA will say *"Listening..."*.
3. Speak your thoughts naturally.
4. Press <kbd>Windows + Space</kbd> again. You will hear a processing chime, NVDA will announce the transcribed text, and the text will be pasted instantly into the active field!

---

## Configuration & Settings

Access preferences via **NVDA Settings (<kbd>NVDA + Ctrl + G</kbd>) &rarr; Wispr Flow**:

- **Account Status**: Displays the connected email and provides *Sign In* / *Sign Out* buttons.
- **Text Insertion Method**:
  - **Paste via Clipboard (Instant, Recommended)**: Pastes the entire text block simultaneously.
  - **Type character-by-character**: Sends individual keystrokes (legacy mode).
- **Spoken Language**: Choose between Auto-detect, English, Hindi, Hinglish (Hindi + English), Spanish, French, or German.
- **Play Sound Effects**: Toggle audio beeps/chimes for start, stop, and errors.
- **Voice Feedback**: Toggle NVDA spoken messages ("Listening...", "Transcribing...").

---

## Architecture & Codebase Overview

```
WisprFlow-NVDA/
├── manifest.ini                   # NVDA Add-on manifest & compatibility range
├── build_addon.py                 # Automated build & installation script
├── .github/
│   └── workflows/
│       └── release.yml            # Automated CI/CD release packager
└── globalPlugins/
    └── wisprFlow/
        ├── __init__.py            # Main GlobalPlugin lifecycle, state machine & retry logic
        ├── auth.py                # Device code OAuth flow & token refresh (api.wisprflow.ai)
        ├── flow_client.py         # gRPC client facade, dynamic lib loader & 60s WAV segmenter
        ├── recognizer.py          # Shared WASAPI audio recorder (16kHz 16-bit Mono, zero ducking)
        ├── keyboard.py            # Win32 clipboard paste & synthetic input
        ├── session_store.py       # Pure JSON token storage (%APPDATA%\nvda\wisprFlow_session.json)
        ├── settings.py            # wxPython settings panel inside NVDA Preferences
        ├── sound.py               # Sound cues via NVDA tones & Windows sound APIs
        └── wisprflow/
            ├── client.py          # Wispr gRPC endpoint coordinator
            ├── protocol.py        # Protobuf binary encoders & clean HTML-to-text parser
            └── models.py          # Route definitions, languages, and transcription options
```

---

## Building from Source & Release Packaging

To build the standalone `.nvda-addon` file locally:

```powershell
python build_addon.py
```

To build and immediately install into your active NVDA user profile:

```powershell
python build_addon.py --install
```

---

## License

Released under the [MIT License](LICENSE).  
Copyright (c) 2026 Ashutosh Chaudhary ([ashuchoudhury22@gmail.com](mailto:ashuchoudhury22@gmail.com)).
