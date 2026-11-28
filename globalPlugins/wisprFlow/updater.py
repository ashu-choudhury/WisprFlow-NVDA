"""
Automatic Updater for Wispr Flow NVDA Add-on.
Follows the non-blocking NVDA updater model (modeled after NVDA's own UpdateDownloader).
- Non-modal update dialog (UpdateDialog.Show) ensures NVDA main loop stays free.
- Asynchronous downloading in a dedicated background thread prevents socket I/O freezes.
- wx.CallAfter throttled progress updates keep the UI responsive without event queue lag.
- Native NVDA installation hand-off via wx.LaunchDefaultApplication().
- Strict asset selection: only accepts the asset whose filename matches the expected version.
- Downloaded package validation: confirms valid zip archive and matching internal manifest version.
- No HTML fallback: a clear error is raised when no matching asset exists.
"""

import configparser
import io
import json
import os
import re
import tempfile
import threading
import urllib.request
import urllib.error
import zipfile
import wx

import core
import gui
from gui import guiHelper
import ui
from .sound import play_sound

GITHUB_RELEASES_URL = "https://api.github.com/repos/ashu-choudhury/WisprFlow-NVDA/releases/latest"
ADDON_NAME = "wisprFlow"

# Expected filename pattern: wisprFlow-<version>.nvda-addon
# The version part must match the release tag version exactly.
_ASSET_RE = re.compile(r"^wisprFlow-([^/]+)\.nvda-addon$", re.IGNORECASE)

_active_update_dialog = None
_active_download_task = None


def get_current_version() -> str:
    """Reads current add-on version from the nearest manifest.ini."""
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
                            return line.split("=", 1)[1].strip()
            except Exception:
                pass
    return "0.0.0"


def parse_version(v_str: str) -> tuple:
    """
    Parses a semantic version string into a tuple of integers for comparison.

    Handles versions like '1.0.5', 'v1.0.10', '2.0' correctly.
    Each component is parsed as a plain integer so that 1.0.10 > 1.0.9.
    Non-numeric suffixes (e.g. '-rc1') are stripped from each part.

    >>> parse_version('1.0.5') == (1, 0, 5)
    True
    >>> parse_version('v1.0.10') > parse_version('1.0.9')
    True
    >>> parse_version('1.0.10') > parse_version('1.0.5')
    True
    >>> parse_version('1.5') > parse_version('1.0.5')
    False
    """
    cleaned = v_str.strip().lstrip("vV")
    if not cleaned:
        return ()
    parts = []
    for part in cleaned.split("."):
        # Strip any non-numeric suffix (e.g. '-rc1', 'b2')
        digits = re.match(r"(\d+)", part)
        parts.append(int(digits.group(1)) if digits else 0)
    return tuple(parts)


def is_newer_version(remote_ver: str, current_ver: str) -> bool:
    """Returns True iff remote_ver is strictly newer than current_ver."""
    return parse_version(remote_ver) > parse_version(current_ver)


def select_asset(assets: list, expected_version: str) -> str | None:
    """
    Selects the download URL for the asset whose filename matches
    'wisprFlow-<expected_version>.nvda-addon' exactly.

    Returns the browser_download_url string, or None if no match is found.
    Never falls back to the first asset or to any HTML page.
    """
    target_name = f"{ADDON_NAME}-{expected_version}.nvda-addon"
    for asset in assets:
        name = asset.get("name", "")
        if name.lower() == target_name.lower():
            url = asset.get("browser_download_url", "")
            if url:
                return url
    return None


def validate_addon_package(path: str, expected_version: str) -> None:
    """
    Validates a downloaded .nvda-addon file before installation.

    Checks:
    1. The file is a valid ZIP archive (NVDA add-ons are ZIP files).
    2. The archive contains a 'manifest.ini' at its root.
    3. The 'version' field in the internal manifest matches expected_version exactly.

    Raises ValueError with a descriptive message on any failure.
    """
    # 1. Valid ZIP?
    if not zipfile.is_zipfile(path):
        raise ValueError(
            f"Downloaded file is not a valid NVDA add-on archive (not a ZIP): {path}"
        )

    with zipfile.ZipFile(path, "r") as z:
        # 2. Has manifest.ini?
        names = z.namelist()
        if "manifest.ini" not in names:
            raise ValueError(
                "Downloaded archive does not contain 'manifest.ini'. "
                "This may not be a valid NVDA add-on."
            )

        # 3. Internal version matches?
        with z.open("manifest.ini") as mf:
            raw = mf.read().decode("utf-8", errors="replace")

        cfg = configparser.RawConfigParser()
        cfg.read_string("[addon]\n" + raw)
        try:
            internal_version = cfg.get("addon", "version").strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            raise ValueError(
                "Could not read 'version' from the internal manifest.ini "
                "of the downloaded archive."
            )

        if internal_version != expected_version:
            raise ValueError(
                f"Version mismatch in downloaded package: "
                f"expected '{expected_version}', "
                f"but internal manifest reports '{internal_version}'. "
                "Refusing to install a mismatched package."
            )


class DownloadTask:
    """
    Handles asynchronous background downloading of the add-on update package.
    Keeps the NVDA main event loop completely free.
    Updates the progress dialog smoothly via wx.CallAfter.
    Validates the downloaded archive before handing off to NVDA.
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

            # Validate the downloaded package before installation
            try:
                validate_addon_package(self.target_path, self.new_version)
            except ValueError as ve:
                self._cleanup_temp()
                wx.CallAfter(self._on_error, str(ve))
                return

            wx.CallAfter(self._on_success)

        except urllib.error.URLError as e:
            self._cleanup_temp()
            wx.CallAfter(self._on_error, f"Network error: {e.reason}")
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
            play_sound("done")
        except Exception:
            pass
        # Launch official NVDA installation via file association
        try:
            wx.LaunchDefaultApplication(self.target_path)
        except Exception:
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
            play_sound("error")
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

    Asset selection is strict:
    - Only the asset named 'wisprFlow-<remote_version>.nvda-addon' is accepted.
    - If no such asset exists, a clear error is reported; there is no HTML fallback.
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

        except urllib.error.URLError as e:
            if manual:
                def _notify_network_error():
                    gui.messageBox(
                        f"Unable to reach GitHub to check for updates.\n"
                        f"Please check your internet connection and try again.\n\n"
                        f"Details: {e.reason}",
                        "Update Error",
                        wx.OK | wx.ICON_WARNING,
                        gui.mainFrame
                    )
                core.callLater(0, _notify_network_error)
            return
        except Exception as e:
            if manual:
                def _notify_error():
                    gui.messageBox(
                        f"Unable to check for updates.\n"
                        f"Please check your internet connection and try again.\n\n"
                        f"Details: {e}",
                        "Update Error",
                        wx.OK | wx.ICON_WARNING,
                        gui.mainFrame
                    )
                core.callLater(0, _notify_error)
            return

        # Parse and validate the remote version from the tag_name field
        raw_tag = data.get("tag_name", "")
        if not raw_tag:
            if manual:
                def _notify_bad_release():
                    gui.messageBox(
                        "The latest GitHub release has no version tag. "
                        "Cannot determine whether an update is available.",
                        "Update Error",
                        wx.OK | wx.ICON_WARNING,
                        gui.mainFrame
                    )
                core.callLater(0, _notify_bad_release)
            return

        remote_ver = raw_tag.lstrip("v").strip()

        # Validate the remote version string looks sane (digits + dots only)
        if not re.match(r"^\d+(\.\d+)*$", remote_ver):
            if manual:
                def _notify_malformed():
                    gui.messageBox(
                        f"The latest GitHub release tag '{raw_tag}' is not a valid "
                        f"semantic version. Cannot check for updates.",
                        "Update Error",
                        wx.OK | wx.ICON_WARNING,
                        gui.mainFrame
                    )
                core.callLater(0, _notify_malformed)
            return

        changelog = data.get("body", "")
        assets = data.get("assets", [])

        # Strict asset selection — must match 'wisprFlow-<remote_ver>.nvda-addon'
        download_url = select_asset(assets, remote_ver)

        if not download_url:
            if manual:
                expected_name = f"wisprFlow-{remote_ver}.nvda-addon"
                available = [a.get("name", "") for a in assets]
                def _notify_no_asset():
                    gui.messageBox(
                        f"No matching add-on package found for version {remote_ver}.\n\n"
                        f"Expected asset name: {expected_name}\n"
                        f"Available assets: {', '.join(available) if available else '(none)'}\n\n"
                        f"Please check the GitHub release page manually.",
                        "Update Error",
                        wx.OK | wx.ICON_WARNING,
                        gui.mainFrame
                    )
                core.callLater(0, _notify_no_asset)
            return

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

    threading.Thread(target=_worker, daemon=True).start()
