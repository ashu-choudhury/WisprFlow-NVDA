"""
Audio Feedback & Sound Effects for NVDA Wispr Flow Add-on.
Uses NVDA's built-in tones API or winsound for distinct status beeps.
"""

try:
    import winsound
except ImportError:
    winsound = None

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
        elif winsound:
            winsound.Beep(880, 80)
    elif cue == "transcribing":
        # Neutral tone
        if tones:
            tones.beep(1100, 60)
        elif winsound:
            winsound.Beep(1100, 60)
    elif cue == "done":
        # Cheerful confirmation double beep
        if tones:
            tones.beep(1320, 90)
        elif winsound:
            winsound.Beep(1320, 90)
    elif cue == "error":
        # Low warning
        if tones:
            tones.beep(350, 150)
        elif winsound:
            winsound.Beep(350, 150)
