"""
Settings Panel for NVDA Wispr Flow Add-on.
Accessible wxPython interface registered into NVDA Preferences -> Settings.
"""

import wx
import gui
import config
import core
import ui

try:
    from gui.settingsDialogs import SettingsPanel
except (ImportError, AttributeError):
    SettingsPanel = gui.SettingsPanel

from .session_store import SessionStore
from .auth import AuthManager

LANGUAGES = [
    ("en", "English"),
    ("hi", "Hindi"),
    ("hi_en", "Hinglish (Hindi + English)"),
    ("auto", "Auto-detect"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
]

INPUT_METHODS = [
    ("paste", "Paste via Clipboard (Instant, Recommended)"),
    ("type", "Type character-by-character (Legacy)"),
]

confspec = {
    "language": "string(default=\"en\")",
    "inputMethod": "string(default=\"paste\")",
    "soundFeedback": "boolean(default=True)",
    "voiceFeedback": "boolean(default=True)",
}


class WisprFlowSettingsPanel(SettingsPanel):
    title = "Wispr Flow"

    def makeSettings(self, settingsSizer):
        sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        self.store = SessionStore()
        self.auth = AuthManager(self.store)

        # 1. Account Section
        session = self.store.get_session()
        account_name = session.get("email") if session else "Not Logged In"

        self.accountLabel = sHelper.addItem(
            wx.StaticText(self, label=f"Account: {account_name}")
        )

        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.loginButton = wx.Button(self, label="Sign In via Browser...")
        self.loginButton.Bind(wx.EVT_BUTTON, self.onLoginClicked)
        buttonSizer.Add(self.loginButton, flag=wx.RIGHT, border=5)

        self.logoutButton = wx.Button(self, label="Sign Out")
        self.logoutButton.Bind(wx.EVT_BUTTON, self.onLogoutClicked)
        buttonSizer.Add(self.logoutButton)

        sHelper.addItem(buttonSizer)

        # 2. Text Insertion Method (Paste vs Type)
        inputLabels = [label for _, label in INPUT_METHODS]
        self.inputChoice = sHelper.addLabeledControl(
            "Text Insertion Method:",
            wx.Choice,
            choices=inputLabels
        )
        cur_input = config.conf.get("wisprFlow", {}).get("inputMethod", "paste")
        input_idx = next((i for i, (k, _) in enumerate(INPUT_METHODS) if k == cur_input), 0)
        self.inputChoice.SetSelection(input_idx)

        # 3. Spoken Language
        langLabels = [label for _, label in LANGUAGES]
        self.langChoice = sHelper.addLabeledControl(
            "Spoken Language:",
            wx.Choice,
            choices=langLabels
        )
        cur_lang = config.conf.get("wisprFlow", {}).get("language", "en")
        lang_idx = next((i for i, (k, _) in enumerate(LANGUAGES) if k == cur_lang), 0)
        self.langChoice.SetSelection(lang_idx)

        # 4. Sound & Voice Feedback
        self.soundCheckbox = sHelper.addItem(
            wx.CheckBox(self, label="Play sound effects (audio cues)")
        )
        self.soundCheckbox.SetValue(config.conf.get("wisprFlow", {}).get("soundFeedback", True))

        self.voiceCheckbox = sHelper.addItem(
            wx.CheckBox(self, label="Speak status notifications (voice feedback)")
        )
        self.voiceCheckbox.SetValue(config.conf.get("wisprFlow", {}).get("voiceFeedback", True))

        # 5. Helpful Shortcut note
        sHelper.addItem(
            wx.StaticText(
                self,
                label="Tip: To customize the dictation shortcut, go to NVDA Menu -> Preferences -> Input Gestures -> Wispr Flow."
            )
        )

    def onLoginClicked(self, event):
        self.loginButton.Disable()
        self.accountLabel.SetLabel("Account: Opening browser for sign-in...")
        ui.message("Opening browser for Wispr Flow sign in. Please complete login in your browser.")

        def on_success(name):
            core.callLater(0, self._update_account_ui, f"Account: Logged in as {name}")
            core.callLater(0, ui.message, f"Wispr Flow sign in successful! Welcome {name}.")

        def on_error(err):
            core.callLater(0, self._update_account_ui, "Account: Sign-in failed")
            core.callLater(0, ui.message, str(err))

        self.auth.start_browser_login(on_success=on_success, on_error=on_error)

    def _update_account_ui(self, label_text):
        self.accountLabel.SetLabel(label_text)
        self.loginButton.Enable()

    def onLogoutClicked(self, event):
        self.store.clear_session()
        self.accountLabel.SetLabel("Account: Not Logged In")
        ui.message("Signed out of Wispr Flow.")

    def onSave(self):
        sel_input = INPUT_METHODS[self.inputChoice.GetSelection()][0]
        sel_lang = LANGUAGES[self.langChoice.GetSelection()][0]

        config.conf["wisprFlow"]["inputMethod"] = sel_input
        config.conf["wisprFlow"]["language"] = sel_lang
        config.conf["wisprFlow"]["soundFeedback"] = self.soundCheckbox.GetValue()
        config.conf["wisprFlow"]["voiceFeedback"] = self.voiceCheckbox.GetValue()
