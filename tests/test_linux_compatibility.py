"""Regression checks for importing and packaging the add-on on Linux.

These tests deliberately run without NVDA, a display server, or a microphone.
They protect the startup boundary: Linux must not evaluate a Win32 DLL binding
just because the add-on is installed.
"""

import configparser
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "globalPlugins" / "wisprFlow"


def load_as_linux(module_name: str, path: Path):
	old_platform = sys.platform
	try:
		sys.platform = "linux"
		spec = importlib.util.spec_from_file_location(module_name, path)
		module = importlib.util.module_from_spec(spec)
		assert spec.loader is not None
		spec.loader.exec_module(module)
		return module
	finally:
		sys.platform = old_platform


class TestLinuxCompatibility(unittest.TestCase):
	def test_manifest_declares_linux(self):
		manifest = configparser.ConfigParser()
		manifest.read_string("[addon]\n" + (ROOT / "manifest.ini").read_text(encoding="utf-8"))
		platforms = manifest["addon"]["platforms"].replace(" ", "").split(",")
		self.assertIn("linux", platforms)

	def test_linux_keyboard_module_does_not_load_win32_dlls(self):
		module = load_as_linux("wisprflow_linux_keyboard", PLUGIN / "keyboard.py")
		self.assertTrue(callable(module.set_clipboard_text))
		self.assertTrue(callable(module.paste_text))

	def test_linux_recorder_import_and_construction_do_not_load_winmm(self):
		old_platform = sys.platform
		try:
			sys.platform = "linux"
			module = load_as_linux("wisprflow_linux_recorder", PLUGIN / "recognizer.py")
			self.assertIsNone(module.AudioRecorder()._winmm)
		finally:
			sys.platform = old_platform

	def test_linux_grpc_bundles_are_selected_separately(self):
		flow_client = (PLUGIN / "flow_client.py").read_text(encoding="utf-8")
		self.assertIn('"linux"', flow_client)
		self.assertIn("_platform_tag", flow_client)


if __name__ == "__main__":
	unittest.main()
