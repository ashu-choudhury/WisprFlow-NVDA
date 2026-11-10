"""
Automatic Updater for Wispr Flow NVDA Add-on.
Follows the non-blocking NVDA updater model (modeled after NVDA's own UpdateDownloader).
- Non-modal update dialog (UpdateDialog.Show) ensures NVDA main loop stays free.
- Asynchronous downloading in a dedicated background thread prevents socket I/O freezes.
- wx.CallAfter throttled progress updates keep the UI responsive without event queue lag.
- Native NVDA installation hand-off via os.startfile().
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
_active_download_task = None


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


class DownloadTask:
    """
    Handles asynchronous background downloading of the add-on update package.
    Keeps the NVDA main event loop completely free.
    Updates the progress dialog smoothly via wx.CallAfter.
    """

    def __init__(self, download_url: str, new_version: str):
        self.download_url = download_url
        self.new_version = new_version
        self.target_path = os.path.join(
            tempfile.gettempdir(),
            f"wisprFlow-{new_version}.nvda-addon"
        )
        self._should_cancel = False
        self._progress_dialog = None

    def start(self):
        gui.mainFrame.prePopup()
        self._progress_dialog = wx.ProgressDialog(
            "Wispr Flow Update",
            f"Downloading Wispr Flow {self.new_version}... Please wait.",
            maximum=100,
            parent=gui.mainFrame,
            style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE
        )
        self._progress_dialog.CentreOnScreen()
        self._progress_dialog.Raise()

        # Start download in background worker thread
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "WisprFlow-NVDA-Updater"}
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                content_length = resp.headers.get("Content-Length")
                total_size = int(content_length) if content_length else 0
                downloaded = 0
                block_size = 65536  # 64 KB
                last_percent = -1

                with open(self.target_path, "wb") as out_f:
                    while not self._should_cancel:
                        chunk = resp.read(block_size)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = min(99, int((downloaded / total_size) * 100))
                            if percent != last_percent:
                                last_percent = percent
                                mb_down = downloaded / (1024 * 1024)
                                mb_total = total_size / (1024 * 1024)
                                msg = f"Downloaded {mb_down:.1f} MB of {mb_total:.1f} MB ({percent}%)"
                                wx.CallAfter(self._update_progress, percent, msg)
                        else:
                            wx.CallAfter(self._pulse_progress, downloaded)

            if self._should_cancel:
                self._cleanup_temp()
                wx.CallAfter(self._on_cancel)
                return

            wx.CallAfter(self._on_success)

        except Exception as e:
            self._cleanup_temp()
            wx.CallAfter(self._on_error, str(e))

    def _cleanup_temp(self):
        if os.path.isfile(self.target_path):
            try:
                os.remove(self.target_path)
            except Exception:
                pass

    def _update_progress(self, percent: int, msg: str):
        if self._progress_dialog:
            try:
                res = self._progress_dialog.Update(percent, msg)
                cont = res[0] if isinstance(res, (tuple, list)) else bool(res)
                if not cont:
                    self._should_cancel = True
            except Exception:
                pass

    def _pulse_progress(self, downloaded_bytes: int):
        if self._progress_dialog:
            try:
                mb_down = downloaded_bytes / (1024 * 1024)
                res = self._progress_dialog.Pulse(f"Downloaded {mb_down:.1f} MB")
                cont = res[0] if isinstance(res, (tuple, list)) else bool(res)
                if not cont:
                    self._should_cancel = True
            except Exception:
                pass

    def _close_dialog(self):
        global _active_download_task
        _active_download_task = None
        if self._progress_dialog:
            try:
                self._progress_dialog.Hide()
                self._progress_dialog.Destroy()
            except Exception:
                pass
            self._progress_dialog = None
        try:
            gui.mainFrame.postPopup()
        except Exception:
            pass

    def _on_cancel(self):
        self._close_dialog()
        ui.message("Wispr Flow download cancelled.")

    def _on_error(self, err_msg: str):
        self._close_dialog()
        gui.messageBox(
            f"Failed to download update:\n{err_msg}",
            "Update Error",
            wx.OK | wx.ICON_ERROR,
            gui.mainFrame
        )

    def _on_success(self):
        self._close_dialog()
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
        # Launch official NVDA installation via file association
        try:
            os.startfile(self.target_path)
        except Exception as e:
            gui.messageBox(
                f"Update downloaded to:\n{self.target_path}\n\nPlease open this file to install.",
                "Wispr Flow Update",
                wx.OK | wx.ICON_INFORMATION,
                gui.mainFrame
            )


class UpdateDialog(wx.Dialog):
    """
    Accessible non-modal update prompt dialog.
    Mimics the Weather_Plus architecture:
    - Never calls ShowModal() so NVDA main event loop and speech pump remain completely free.
    - Displays changelog, Install, and Not Needed buttons.
    - Hands download off to asynchronous DownloadTask.
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
        global _active_update_dialog, _active_download_task
        _active_update_dialog = None
        download_url = self.download_url
        new_version = self.new_version
        self.Destroy()

        # Start asynchronous download task
        _active_download_task = DownloadTask(download_url, new_version)
        _active_download_task.start()


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
