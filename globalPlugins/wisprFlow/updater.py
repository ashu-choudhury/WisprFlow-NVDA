"""
Automatic Updater for Wispr Flow NVDA Add-on.
Checks GitHub Releases for new versions, displays release changelog,
and provides seamless 1-click update installation.
"""

import json
import os
import tempfile
import threading
import urllib.request
import urllib.error
import wx

import core
import gui
import ui

GITHUB_RELEASES_URL = "https://api.github.com/repos/ashu-choudhury/WisprFlow-NVDA/releases/latest"
ADDON_NAME = "wisprFlow"


def get_current_version() -> str:
    """Reads current add-on version from manifest.ini."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Check parent directory (addon root) or installed manifest
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
    Accessible dialog prompting the user to install a new version.
    Includes changelog view, 'Install', and 'Not Needed' buttons.
    """

    def __init__(self, parent, current_version: str, new_version: str, changelog: str, download_url: str):
        super().__init__(
            parent,
            title="Wispr Flow Update Available",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.download_url = download_url
        self.new_version = new_version

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. Prompt Text
        prompt_text = (
            f"A new version ({new_version}) is available.\n"
            f"Do you like to install?\n\n"
            f"Current version: {current_version}"
        )
        label_prompt = wx.StaticText(self, label=prompt_text)
        main_sizer.Add(label_prompt, flag=wx.ALL | wx.EXPAND, border=10)

        # 2. Changelog Label
        label_changelog = wx.StaticText(self, label="Change log:")
        main_sizer.Add(label_changelog, flag=wx.LEFT | wx.RIGHT, border=10)

        # 3. Multiline Read-Only Changelog Text Box
        self.changelog_ctrl = wx.TextCtrl(
            self,
            value=changelog or "No changelog provided.",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(480, 160)
        )
        main_sizer.Add(self.changelog_ctrl, proportion=1, flag=wx.ALL | wx.EXPAND, border=10)

        # 4. Buttons Row: Install, Not Needed
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        self.btn_install = wx.Button(self, label="&Install")
        self.btn_install.SetDefault()
        self.btn_install.Bind(wx.EVT_BUTTON, self.on_install)
        btn_sizer.Add(self.btn_install, flag=wx.RIGHT, border=10)

        self.btn_not_needed = wx.Button(self, label="&Not Needed")
        self.btn_not_needed.Bind(wx.EVT_BUTTON, self.on_not_needed)
        btn_sizer.Add(self.btn_not_needed)

        main_sizer.Add(btn_sizer, flag=wx.ALL | wx.EXPAND, border=10)

        self.SetSizer(main_sizer)
        self.Fit()
        self.CentreOnScreen()

    def on_install(self, event):
        self.EndModal(wx.ID_YES)

    def on_not_needed(self, event):
        self.EndModal(wx.ID_NO)


def _perform_download_and_install(download_url: str, new_version: str):
    """Downloads the .nvda-addon package and triggers installation."""
    progress_dialog = wx.ProgressDialog(
        "Downloading Wispr Flow Update",
        f"Downloading version {new_version}... Please wait.",
        maximum=100,
        parent=gui.mainFrame,
        style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE
    )
    progress_dialog.CentreOnScreen()

    tmp_file = None
    try:
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "WisprFlow-NVDA-Updater"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 65536

            tmp = tempfile.NamedTemporaryFile(suffix=".nvda-addon", delete=False)
            tmp_file = tmp.name

            while True:
                chunk = resp.read(block_size)
                if not chunk:
                    break
                tmp.write(chunk)
                downloaded += len(chunk)

                if total_size > 0:
                    percent = min(100, int((downloaded / total_size) * 100))
                    progress_dialog.Update(percent)
                else:
                    progress_dialog.Pulse()

            tmp.close()

        progress_dialog.Destroy()

        # Install via NVDA addonHandler
        try:
            import addonHandler
            bundle = addonHandler.AddonBundle(tmp_file)
            for a in addonHandler.getAvailableAddons():
                if a.name == bundle.manifest.get("name"):
                    a.requestRemove()
                    break
            addonHandler.installAddonBundle(bundle)

            # Prompt to restart NVDA
            res = gui.messageBox(
                f"Wispr Flow has been successfully updated to version {new_version}.\n\n"
                "Would you like to restart NVDA now to activate the new version?",
                "Wispr Flow Update",
                wx.YES_NO | wx.ICON_QUESTION,
                gui.mainFrame
            )
            if res == wx.YES:
                core.restart()

        except Exception as e:
            # Fallback to shell open if addonHandler direct call encounters an issue
            os.startfile(tmp_file)

    except Exception as e:
        if progress_dialog:
            try:
                progress_dialog.Destroy()
            except Exception:
                pass
        gui.messageBox(
            f"Failed to download update:\n{e}",
            "Update Error",
            wx.OK | wx.ICON_ERROR,
            gui.mainFrame
        )


def check_for_updates(manual: bool = False):
    """
    Checks GitHub Releases API in a separate thread.
    If an update is found, presents the UpdateDialog.
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
                    dlg = UpdateDialog(
                        gui.mainFrame,
                        current_version=current_ver,
                        new_version=remote_ver,
                        changelog=changelog,
                        download_url=download_url
                    )
                    res = dlg.ShowModal()
                    dlg.Destroy()
                    if res == wx.ID_YES:
                        threading.Thread(
                            target=_perform_download_and_install,
                            args=(download_url, remote_ver),
                            daemon=True
                        ).start()

                core.callLater(0, _show_dialog)
            elif manual:
                def _show_uptodate():
                    gui.messageBox(
                        f"You are running the latest version of Wispr Flow (v{current_ver}).",
                        "Wispr Flow Update",
                        wx.OK | wx.ICON_INFORMATION,
                        gui.mainFrame
                    )
                core.callLater(0, _show_uptodate)

        except Exception as e:
            if manual:
                def _show_err():
                    gui.messageBox(
                        f"Unable to check for updates.\nPlease verify your internet connection.\n\nDetails: {e}",
                        "Wispr Flow Update",
                        wx.OK | wx.ICON_ERROR,
                        gui.mainFrame
                    )
                core.callLater(0, _show_err)

    threading.Thread(target=_worker, daemon=True).start()
