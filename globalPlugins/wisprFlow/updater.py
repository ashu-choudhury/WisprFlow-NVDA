"""
Automatic Updater for Wispr Flow NVDA Add-on.
Follows the proven, non-blocking NVDA updater model (as used in Weather_Plus).
Checks GitHub Releases for new versions, presents an accessible non-modal prompt
with changelog, and performs smooth downloading and standard NVDA installation.
"""

import json
import os
import tempfile
import threading
import urllib.request
import urllib.error
import winsound
import wx

import core
import gui
from gui import guiHelper
import ui

GITHUB_RELEASES_URL = "https://api.github.com/repos/ashu-choudhury/WisprFlow-NVDA/releases/latest"
ADDON_NAME = "wisprFlow"

_active_update_dialog = None


def get_current_version() -> str:
    """Reads current add-on version from manifest.ini."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(current_dir, "..", "..", "manifest.ini"),
        os.path.join(current_dir, "..", "manifest.ini"),
        os.path.join(current_dir, "manifest.ini"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("version"):
                            return line.split("=")[1].strip()
            except Exception:
                pass
    return "1.0.0"


def parse_version(v_str: str) -> tuple:
    """Parses semantic version string into integer tuple for comparison."""
    cleaned = v_str.lstrip("v").strip()
    parts = []
    for p in cleaned.split("."):
        digits = "".join(filter(str.isdigit, p))
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer_version(remote_ver: str, current_ver: str) -> bool:
    return parse_version(remote_ver) > parse_version(current_ver)


class UpdateDialog(wx.Dialog):
    """
    Accessible non-modal update prompt dialog.
    Mimics the Weather_Plus architecture:
    - Never calls ShowModal() so the NVDA main event loop and speech pump remain completely free.
    - Displays changelog, Install, and Not Needed buttons.
    - Downloads package with responsive progress feedback.
    - Hands package to NVDA's official installer via os.startfile().
    """

    def __init__(self, parent, current_version: str, new_version: str, changelog: str, download_url: str):
        super().__init__(
            parent,
            title="Wispr Flow Update Available",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.download_url = download_url
        self.new_version = new_version
        self.current_version = current_version

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

        # Auditory cue when dialog appears
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        # 1. Prompt Text
        prompt_text = (
            f"A new version ({new_version}) of Wispr Flow is available.\n"
            f"Installed version: {current_version}.\n\n"
            f"Do you want to download and install it?"
        )
        sizer_helper.addItem(wx.StaticText(self, label=prompt_text))

        # 2. Changelog Label
        sizer_helper.addItem(wx.StaticText(self, label="Change log:"))

        # 3. Multiline Read-Only Changelog
        self.changelog_ctrl = wx.TextCtrl(
            self,
            value=changelog or "No changelog provided.",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(520, 180)
        )
        sizer_helper.addItem(self.changelog_ctrl)

        # 4. Buttons (Install & Not Needed)
        btn_helper = sizer_helper.addDialogDismissButtons(guiHelper.ButtonHelper(wx.HORIZONTAL))
        self.btn_install = btn_helper.addButton(self, id=wx.ID_YES, label="&Install")
        self.btn_not_needed = btn_helper.addButton(self, id=wx.ID_NO, label="&Not Needed")

        self.btn_install.SetDefault()
        self.btn_install.Bind(wx.EVT_BUTTON, self.on_install)
        self.btn_not_needed.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.Bind(wx.EVT_CLOSE, self.on_cancel)

        main_sizer.Add(sizer_helper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
        main_sizer.Fit(self)
        self.SetSizer(main_sizer)
        self.Center(wx.BOTH | wx.CENTER)

    def on_cancel(self, event=None):
        global _active_update_dialog
        _active_update_dialog = None
        self.Destroy()

    def on_install(self, event=None):
        global _active_update_dialog
        _active_update_dialog = None
        self.Hide()

        filename = f"wisprFlow-{self.new_version}.nvda-addon"
        target_path = os.path.join(tempfile.gettempdir(), filename)

        success = self._download_file(self.download_url, target_path)
        if success:
            try:
                # Trigger native NVDA add-on installation via registered file association
                os.startfile(target_path)
            except Exception as e:
                gui.messageBox(
                    f"Update package downloaded to:\n{target_path}\n\nPlease open this file to complete the installation.",
                    "Wispr Flow Update",
                    wx.OK | wx.ICON_INFORMATION,
                    gui.mainFrame
                )
        self.Destroy()

    def _download_file(self, url: str, target_path: str) -> bool:
        """Downloads the update package using GenericProgressDialog and GetApp().Yield()."""
        max_steps = 100
        title = "Wispr Flow Update"
        message = f"Downloading Wispr Flow {self.new_version}... Please wait."

        progress_dialog = wx.GenericProgressDialog(
            title,
            message,
            maximum=max_steps,
            parent=None,
            style=wx.PD_CAN_ABORT | wx.PD_APP_MODAL | wx.PD_ELAPSED_TIME | wx.PD_ESTIMATED_TIME
        )
        progress_dialog.CentreOnScreen()
        progress_dialog.Update(0, message)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "WisprFlow-NVDA-Updater"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                content_length = resp.headers.get("Content-Length")
                total_size = int(content_length) if content_length else None
                keep_going = True
                downloaded = 0
                chunk_size = max(1024, (total_size // max_steps) if total_size else 65536)

                with open(target_path, "wb") as out_f:
                    count = 0
                    while keep_going:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        downloaded += len(chunk)
                        count += 1
                        if count >= max_steps:
                            count = 99

                        wx.GetApp().Yield()

                        if total_size and total_size > 0:
                            mb_down = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            status_txt = f"Downloaded {mb_down:.1f} MB of {mb_total:.1f} MB"
                            keep_going, _ = progress_dialog.Update(count, status_txt)
                        else:
                            keep_going, _ = progress_dialog.UpdatePulse(f"Downloaded {downloaded // 1024} KB")

            progress_dialog.Update(99, "Download complete.")
            progress_dialog.Hide()
            progress_dialog.Destroy()

            if not keep_going:
                if os.path.isfile(target_path):
                    try:
                        os.remove(target_path)
                    except Exception:
                        pass
                ui.message("Wispr Flow download cancelled.")
                return False

            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
            return True

        except Exception as e:
            try:
                progress_dialog.Hide()
                progress_dialog.Destroy()
            except Exception:
                pass
            if os.path.isfile(target_path):
                try:
                    os.remove(target_path)
                except Exception:
                    pass
            gui.messageBox(
                f"Failed to download update:\n{e}",
                "Update Error",
                wx.OK | wx.ICON_ERROR,
                gui.mainFrame
            )
            return False


def check_for_updates(manual: bool = False):
    """
    Checks GitHub Releases API in a separate background thread.
    Presents UpdateDialog non-modally without interrupting NVDA.
    """
    def _worker():
        current_ver = get_current_version()
        try:
            req = urllib.request.Request(
                GITHUB_RELEASES_URL,
                headers={"User-Agent": "WisprFlow-NVDA-Updater"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            remote_ver = data.get("tag_name", "").lstrip("v")
            changelog = data.get("body", "")

            # Locate .nvda-addon asset
            download_url = None
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".nvda-addon"):
                    download_url = asset.get("browser_download_url")
                    break

            if not download_url:
                download_url = data.get("html_url")

            if is_newer_version(remote_ver, current_ver):
                def _show_dialog():
                    global _active_update_dialog
                    if _active_update_dialog:
                        try:
                            _active_update_dialog.Raise()
                            _active_update_dialog.SetFocus()
                            return
                        except Exception:
                            _active_update_dialog = None

                    gui.mainFrame.prePopup()
                    _active_update_dialog = UpdateDialog(
                        gui.mainFrame,
                        current_version=current_ver,
                        new_version=remote_ver,
                        changelog=changelog,
                        download_url=download_url
                    )
                    _active_update_dialog.Show()
                    gui.mainFrame.postPopup()

                core.callLater(0, _show_dialog)
            elif manual:
                def _notify_up_to_date():
                    gui.messageBox(
                        f"Wispr Flow is up to date.\nInstalled version: {current_ver}",
                        "Wispr Flow Update",
                        wx.OK | wx.ICON_INFORMATION,
                        gui.mainFrame
                    )
                core.callLater(0, _notify_up_to_date)

        except Exception as e:
            if manual:
                def _notify_error():
                    gui.messageBox(
                        f"Unable to check for updates.\nPlease check your internet connection and try again.\n\nDetails: {e}",
                        "Update Error",
                        wx.OK | wx.ICON_WARNING,
                        gui.mainFrame
                    )
                core.callLater(0, _notify_error)

    threading.Thread(target=_worker, daemon=True).start()
