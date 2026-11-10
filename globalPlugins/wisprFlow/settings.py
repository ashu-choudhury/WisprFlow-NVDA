"""
Settings Panel for NVDA Wispr Flow Add-on.
Accessible wxPython interface registered into NVDA Preferences -> Settings.
Provides conditional Sign In / Sign Out controls and live API account statistics.
"""

import os
import threading
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
from .updater import check_for_updates

LANGUAGES = [
    ("en", "English"),
    ("hi", "Hindi"),
    ("hi_en", "Hinglish (Hindi + English)"),
    ("bn", "Bengali"),
    ("ur", "Urdu"),
    ("auto", "Auto-detect"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("ar", "Arabic"),
    ("ta", "Tamil"),
    ("te", "Telugu"),
    ("mr", "Marathi"),
    ("gu", "Gujarati"),
    ("ja", "Japanese"),
    ("zh", "Chinese"),
    ("pt", "Portuguese"),
    ("ru", "Russian"),
    ("it", "Italian"),
]

INPUT_METHODS = [
    ("paste", "Paste via Clipboard (Instant, Recommended)"),
    ("clipboard_only", "Copy to Clipboard only (Do not paste)"),
    ("type", "Type character-by-character (Legacy)"),
]

confspec = {
    "language": "string(default=\"en\")",
    "inputMethod": "string(default=\"paste\")",
    "customVocabulary": "string(default=\"\")",
    "soundFeedback": "boolean(default=True)",
    "voiceFeedback": "boolean(default=True)",
    "autoCheckUpdates": "boolean(default=True)",
}


class WisprFlowSettingsPanel(SettingsPanel):
    title = "Wispr Flow"

    def makeSettings(self, settingsSizer):
        sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        self.store = SessionStore()
        self.auth = AuthManager(self.store)

        session = self.store.get_session()
        is_logged_in = bool(session and session.get("access_token"))

        # 1. Account Action Buttons (Conditional Visibility)
        self.buttonSizer = wx.BoxSizer(wx.HORIZONTAL)

        self.loginButton = wx.Button(self, label="&Sign In via Browser...")
        self.loginButton.Bind(wx.EVT_BUTTON, self.onLoginClicked)
        self.buttonSizer.Add(self.loginButton, flag=wx.RIGHT, border=5)

        self.logoutButton = wx.Button(self, label="&Sign Out")
        self.logoutButton.Bind(wx.EVT_BUTTON, self.onLogoutClicked)
        self.buttonSizer.Add(self.logoutButton, flag=wx.RIGHT, border=5)

        self.refreshButton = wx.Button(self, label="&Refresh Account Info")
        self.refreshButton.Bind(wx.EVT_BUTTON, self.onRefreshClicked)
        self.buttonSizer.Add(self.refreshButton)

        # Apply initial conditional visibility
        self.loginButton.Show(not is_logged_in)
        self.logoutButton.Show(is_logged_in)
        self.refreshButton.Show(is_logged_in)

        sHelper.addItem(self.buttonSizer)

        # 2. Account Profile & Voice Statistics Box
        sHelper.addItem(wx.StaticText(self, label="Account Profile & Dictation Statistics:"))
        self.accountDetailsText = sHelper.addItem(
            wx.TextCtrl(
                self,
                value=self._get_account_display_text(),
                style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
                size=(-1, 140)
            )
        )
        self.accountDetailsText.SetName("Account Profile and Dictation Statistics")

        # 3. Text Insertion Method (Paste vs Type)
        inputLabels = [label for _, label in INPUT_METHODS]
        self.inputChoice = sHelper.addLabeledControl(
            "Text Insertion Method:",
            wx.Choice,
            choices=inputLabels
        )
        cur_input = config.conf.get("wisprFlow", {}).get("inputMethod", "paste")
        input_idx = next((i for i, (k, _) in enumerate(INPUT_METHODS) if k == cur_input), 0)
        self.inputChoice.SetSelection(input_idx)

        # 4. Spoken Language
        langLabels = [label for _, label in LANGUAGES]
        self.langChoice = sHelper.addLabeledControl(
            "Spoken Language:",
            wx.Choice,
            choices=langLabels
        )
        cur_lang = config.conf.get("wisprFlow", {}).get("language", "en")
        lang_idx = next((i for i, (k, _) in enumerate(LANGUAGES) if k == cur_lang), 0)
        self.langChoice.SetSelection(lang_idx)

        # 5. Custom Vocabulary (Specialized words, names, jargon)
        self.vocabCtrl = sHelper.addLabeledControl(
            "Custom Vocabulary (comma-separated words or names):",
            wx.TextCtrl
        )
        self.vocabCtrl.SetValue(config.conf.get("wisprFlow", {}).get("customVocabulary", ""))

        # 6. Sound & Voice Feedback
        self.soundCheckbox = sHelper.addItem(
            wx.CheckBox(self, label="Play sound effects (audio cues)")
        )
        self.soundCheckbox.SetValue(config.conf.get("wisprFlow", {}).get("soundFeedback", True))

        self.voiceCheckbox = sHelper.addItem(
            wx.CheckBox(self, label="Speak status notifications (voice feedback)")
        )
        self.voiceCheckbox.SetValue(config.conf.get("wisprFlow", {}).get("voiceFeedback", True))

        # 7. Fail-safe Retranscribe button
        self.retranscribeButton = sHelper.addItem(
            wx.Button(self, label="&Re-transcribe Last Audio Recording...")
        )
        self.retranscribeButton.Bind(wx.EVT_BUTTON, self.onRetranscribeClicked)

        # 8. Automatic Updates
        self.updateCheckbox = sHelper.addItem(
            wx.CheckBox(self, label="Automatically check for updates on startup")
        )
        self.updateCheckbox.SetValue(config.conf.get("wisprFlow", {}).get("autoCheckUpdates", True))

        self.checkUpdatesButton = sHelper.addItem(
            wx.Button(self, label="Check for Updates Now...")
        )
        self.checkUpdatesButton.Bind(wx.EVT_BUTTON, lambda evt: check_for_updates(manual=True))

        # 9. Helpful Shortcut note
        sHelper.addItem(
            wx.StaticText(
                self,
                label="Tip: To customize the dictation shortcut, go to NVDA Menu -> Preferences -> Input Gestures -> Wispr Flow."
            )
        )

    def _get_account_display_text(self) -> str:
        session = self.store.get_session()
        if not session or not session.get("access_token"):
            return (
                "Status: Not Signed In\n\n"
                "Please click 'Sign In via Browser...' above to connect your Wispr Flow account."
            )

        # Fetch verified account profile from API / cached store
        profile = self.auth.get_account_profile()
        email = profile.get("email") or session.get("email") or "Unknown"
        user_meta = profile.get("user_metadata", {})
        name = user_meta.get("full_name") or user_meta.get("name") or session.get("email") or "User"
        user_id = profile.get("id") or session.get("user_id") or "N/A"
        app_meta = profile.get("app_metadata", {})
        provider = app_meta.get("provider", "google").capitalize()
        created_at = profile.get("created_at", "")[:10] if profile.get("created_at") else "N/A"
        last_sign_in = profile.get("last_sign_in_at", "")[:10] if profile.get("last_sign_in_at") else "N/A"
        email_confirmed = "Yes (Verified)" if profile.get("email_confirmed_at") else "Pending"

        usage = self.store.get_usage()
        total_dictations = usage.get("total_dictations", 0)
        total_words = usage.get("total_words", 0)
        audio_sec = usage.get("total_audio_seconds", 0.0)
        audio_min = audio_sec / 60.0

        details = [
            f"Account: {email}",
            f"Display Name: {name}",
            f"Status: Signed In",
            f"Login Provider: {provider}",
            f"User ID: {user_id}",
            f"Email Verified: {email_confirmed}",
            f"Member Since: {created_at}",
            f"Last Sign-In: {last_sign_in}",
            "",
            "--- Dictation & Voice Statistics ---",
            f"Total Dictations: {total_dictations}",
            f"Total Words Dictated: {total_words}",
            f"Total Audio Detected: {audio_sec:.1f} seconds ({audio_min:.1f} minutes)",
        ]
        return "\n".join(details)

    def _update_auth_state(self, is_logged_in: bool):
        self.loginButton.Show(not is_logged_in)
        self.logoutButton.Show(is_logged_in)
        self.refreshButton.Show(is_logged_in)
        self.loginButton.Enable()
        self.logoutButton.Enable()
        self.accountDetailsText.SetValue(self._get_account_display_text())
        self.buttonSizer.Layout()
        self.Layout()

    def onLoginClicked(self, event):
        self.loginButton.Disable()
        self.accountDetailsText.SetValue("Opening browser for Wispr Flow sign in. Please complete sign-in in your browser...")
        ui.message("Opening browser for Wispr Flow sign in. Please complete login in your browser.")

        def on_success(name):
            core.callLater(0, self._update_auth_state, True)
            core.callLater(0, ui.message, f"Wispr Flow sign in successful! Welcome {name}. You can now close your browser tab.")

        def on_error(err):
            core.callLater(0, self._update_auth_state, False)
            core.callLater(0, ui.message, str(err))

        self.auth.start_browser_login(on_success=on_success, on_error=on_error)

    def onLogoutClicked(self, event):
        self.store.clear_session()
        self._update_auth_state(False)
        ui.message("Signed out of Wispr Flow.")

    def onRefreshClicked(self, event):
        self.accountDetailsText.SetValue("Refreshing account profile and statistics from API...")
        def _refresh():
            self.auth.get_account_profile()
            core.callLater(0, self.accountDetailsText.SetValue, self._get_account_display_text())
            core.callLater(0, ui.message, "Account profile and statistics refreshed.")
        threading.Thread(target=_refresh, daemon=True).start()

    def onRetranscribeClicked(self, event):
        wav_path = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "nvda",
            "last_dictation.wav"
        )
        if not os.path.isfile(wav_path):
            gui.messageBox(
                "No previous audio recording found.",
                "Wispr Flow",
                wx.OK | wx.ICON_INFORMATION,
                self
            )
            return

        ui.message("Re-transcribing last audio recording...")
        def _retranscribe():
            from .flow_client import FlowClient
            from .keyboard import paste_text, type_text, set_clipboard_text
            import time

            client = FlowClient(self.store, self.auth)
            lang = config.conf.get("wisprFlow", {}).get("language", "en")
            input_method = config.conf.get("wisprFlow", {}).get("inputMethod", "paste")
            vocab_str = config.conf.get("wisprFlow", {}).get("customVocabulary", "")
            custom_vocab = [w.strip() for w in vocab_str.split(",") if w.strip()] if vocab_str else None

            try:
                text = client.transcribe(wav_path, language=lang, custom_vocabulary=custom_vocab)
                if text:
                    if input_method == "clipboard_only":
                        set_clipboard_text(text)
                        time.sleep(0.08)
                        core.callLater(0, ui.message, f"Copied to clipboard: {text}")
                    elif input_method == "paste":
                        paste_text(text)
                        time.sleep(0.08)
                        core.callLater(0, ui.message, text)
                    else:
                        type_text(text)
                        time.sleep(0.08)
                        core.callLater(0, ui.message, text)
                else:
                    core.callLater(0, ui.message, "No speech detected in last recording.")
            except Exception as e:
                core.callLater(0, ui.message, f"Re-transcription failed: {e}")

        threading.Thread(target=_retranscribe, daemon=True).start()

    def onSave(self):
        sel_input = INPUT_METHODS[self.inputChoice.GetSelection()][0]
        sel_lang = LANGUAGES[self.langChoice.GetSelection()][0]

        config.conf["wisprFlow"]["inputMethod"] = sel_input
        config.conf["wisprFlow"]["language"] = sel_lang
        config.conf["wisprFlow"]["customVocabulary"] = self.vocabCtrl.GetValue().strip()
        config.conf["wisprFlow"]["soundFeedback"] = self.soundCheckbox.GetValue()
        config.conf["wisprFlow"]["voiceFeedback"] = self.voiceCheckbox.GetValue()
        config.conf["wisprFlow"]["autoCheckUpdates"] = self.updateCheckbox.GetValue()
