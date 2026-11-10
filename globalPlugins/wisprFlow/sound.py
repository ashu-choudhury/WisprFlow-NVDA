"""
Audio Feedback & Sound Effects for NVDA Wispr Flow Add-on.
Uses NVDA's built-in tones API or winsound for distinct status beeps.
"""

import winsound

try:
    import tones
except ImportError:
    tones = None


def play_sound(cue: str):
    """Play distinct acoustic tones for state transitions."""
    if cue == "start":
        # Upward high pip
        if tones:
            tones.beep(880, 80)
        else:
            winsound.Beep(880, 80)
    elif cue == "transcribing":
        # Neutral tone
        if tones:
            tones.beep(1100, 60)
        else:
            winsound.Beep(1100, 60)
    elif cue == "done":
        # Cheerful confirmation double beep
        if tones:
            tones.beep(1320, 90)
        else:
            winsound.Beep(1320, 90)
    elif cue == "error":
        # Low warning
        if tones:
            tones.beep(350, 150)
        else:
            winsound.Beep(350, 150)
