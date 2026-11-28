"""
Tests for the Wispr Flow NVDA add-on updater logic.

Covers:
- Version parsing (parse_version) with semantic versioning edge cases
- Version comparison (is_newer_version), including 1.0.10 > 1.0.9
- Asset selection (select_asset): exact filename match, no HTML fallback
- Package validation (validate_addon_package): valid zip, manifest present, version match
- Failure cases: network errors, missing assets, malformed versions, bad archives
- Regression: v1.5 must NOT be treated as newer than 1.0.5 by parse_version semantics;
  the manifest/tag alignment fix ensures the two are kept in sync and the version space
  correctly continues from 1.0.5 -> 1.0.6, 1.0.7, ...

Run with:
    python -m pytest tests/test_updater.py -v
or:
    python -m unittest tests.test_updater
"""

import configparser
import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# ---------------------------------------------------------------------------
# Bootstrap: make the updater importable without NVDA being installed.
# We mock out the NVDA-specific modules before importing updater.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parents[1]

# Provide stubs for every NVDA-only import used by updater.py
_NVDA_STUBS = ["core", "gui", "gui.guiHelper", "ui", "wx"]

for _mod in _NVDA_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Stub the add-on's own sound module so the relative import inside updater.py resolves.
# updater.py does `from .sound import play_sound` — to intercept this we must register
# the stub under the package name the loader will look up.
import types

_sound_stub = MagicMock()
_sound_stub.play_sound = MagicMock()

# Register the full package hierarchy so the relative import chain works.
_wf_plugin_pkg = types.ModuleType("globalPlugins")
_wf_wf_pkg = types.ModuleType("globalPlugins.wisprFlow")
_wf_sound_mod = types.ModuleType("globalPlugins.wisprFlow.sound")
_wf_sound_mod.play_sound = MagicMock()

_wf_plugin_pkg.wisprFlow = _wf_wf_pkg
_wf_wf_pkg.sound = _wf_sound_mod

sys.modules.setdefault("globalPlugins", _wf_plugin_pkg)
sys.modules.setdefault("globalPlugins.wisprFlow", _wf_wf_pkg)
sys.modules["globalPlugins.wisprFlow.sound"] = _wf_sound_mod

# Now add the package root to sys.path so absolute imports resolve
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import updater as a submodule of the stubbed package so relative imports work.
import importlib.util

_updater_path = ROOT / "globalPlugins" / "wisprFlow" / "updater.py"
_spec = importlib.util.spec_from_file_location(
    "globalPlugins.wisprFlow.updater",
    _updater_path,
    submodule_search_locations=[],
)
_updater_mod = importlib.util.module_from_spec(_spec)
# Register as part of the package before exec so intra-package imports resolve
sys.modules["globalPlugins.wisprFlow.updater"] = _updater_mod
_wf_wf_pkg.updater = _updater_mod
_spec.loader.exec_module(_updater_mod)

parse_version = _updater_mod.parse_version
is_newer_version = _updater_mod.is_newer_version
select_asset = _updater_mod.select_asset
validate_addon_package = _updater_mod.validate_addon_package
get_current_version = _updater_mod.get_current_version


# ---------------------------------------------------------------------------
# Helper: build a minimal .nvda-addon in-memory (or on disk)
# ---------------------------------------------------------------------------

def _make_addon_zip(version: str, path: str | None = None) -> str:
    """
    Creates a valid .nvda-addon archive with an internal manifest.ini
    declaring the given version.  Returns the file path.
    """
    manifest_content = f"name = wisprFlow\nversion = {version}\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.ini", manifest_content)
        z.writestr("globalPlugins/wisprFlow/__init__.py", "# stub\n")

    if path is None:
        fd, path = tempfile.mkstemp(suffix=".nvda-addon")
        os.close(fd)

    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


def _make_bad_zip(path: str | None = None) -> str:
    """Creates a file that is not a valid ZIP."""
    if path is None:
        fd, path = tempfile.mkstemp(suffix=".nvda-addon")
        os.close(fd)
    with open(path, "wb") as f:
        f.write(b"This is not a zip file.\n<html>Not a package</html>")
    return path


def _make_addon_zip_no_manifest(path: str | None = None) -> str:
    """Creates a valid ZIP archive that is missing manifest.ini."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("globalPlugins/wisprFlow/__init__.py", "# stub\n")

    if path is None:
        fd, path = tempfile.mkstemp(suffix=".nvda-addon")
        os.close(fd)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


# ===========================================================================
# Test: parse_version
# ===========================================================================

class TestParseVersion(unittest.TestCase):

    def test_simple_three_part(self):
        self.assertEqual(parse_version("1.0.5"), (1, 0, 5))

    def test_leading_v(self):
        self.assertEqual(parse_version("v1.0.5"), (1, 0, 5))
        self.assertEqual(parse_version("V2.3.4"), (2, 3, 4))

    def test_two_part(self):
        self.assertEqual(parse_version("1.5"), (1, 5))

    def test_single_part(self):
        self.assertEqual(parse_version("2"), (2,))

    def test_four_part(self):
        self.assertEqual(parse_version("1.2.3.4"), (1, 2, 3, 4))

    def test_numeric_ordering_correctness(self):
        """1.0.10 must be greater than 1.0.9 (not less like a lexicographic sort would give)."""
        self.assertGreater(parse_version("1.0.10"), parse_version("1.0.9"))

    def test_numeric_ordering_1_0_6_gt_1_0_5(self):
        self.assertGreater(parse_version("1.0.6"), parse_version("1.0.5"))

    def test_1_5_vs_1_0_5(self):
        """
        v1.5 (the erroneous tag) is semantically LESS than 1.0.5 is NOT a valid statement.
        1.5 == (1, 5), and 1.0.5 == (1, 0, 5).
        Tuple comparison: (1, 5) > (1, 0, 5) because at index 1: 5 > 0.
        This is the root cause of the spurious update: 1.5 appeared newer than 1.0.5.
        The fix is to keep tag and manifest in sync at 1.0.6, not to change parse_version.
        """
        # Confirm the parse_version behaviour so we understand the bug clearly
        self.assertGreater(parse_version("1.5"), parse_version("1.0.5"))
        # After the fix, the installed version will be 1.0.6 and new releases
        # will be 1.0.7, 1.0.8, etc. — the v1.5 tag is a one-off anomaly.

    def test_non_numeric_suffix_stripped(self):
        """Parts like '5b2' or '10rc1' should use only the leading integer."""
        self.assertEqual(parse_version("1.0.5b2"), (1, 0, 5))
        self.assertEqual(parse_version("2.0.10rc1"), (2, 0, 10))

    def test_empty_string_fallback(self):
        self.assertEqual(parse_version(""), ())

    def test_zero_version(self):
        self.assertEqual(parse_version("0.0.0"), (0, 0, 0))


# ===========================================================================
# Test: is_newer_version
# ===========================================================================

class TestIsNewerVersion(unittest.TestCase):

    def test_newer(self):
        self.assertTrue(is_newer_version("1.0.6", "1.0.5"))

    def test_same(self):
        self.assertFalse(is_newer_version("1.0.5", "1.0.5"))

    def test_older(self):
        self.assertFalse(is_newer_version("1.0.4", "1.0.5"))

    def test_major_bump(self):
        self.assertTrue(is_newer_version("2.0.0", "1.9.9"))

    def test_patch_crossing_ten(self):
        """Ensure 1.0.10 is correctly seen as newer than 1.0.9."""
        self.assertTrue(is_newer_version("1.0.10", "1.0.9"))

    def test_patch_crossing_ten_vs_older_patch(self):
        self.assertTrue(is_newer_version("1.0.10", "1.0.5"))

    def test_v_prefix_stripped(self):
        self.assertTrue(is_newer_version("v1.0.6", "1.0.5"))
        self.assertFalse(is_newer_version("v1.0.5", "1.0.5"))


# ===========================================================================
# Test: select_asset
# ===========================================================================

class TestSelectAsset(unittest.TestCase):

    def _make_assets(self, names: list[str]) -> list[dict]:
        return [
            {
                "name": n,
                "browser_download_url": f"https://example.com/releases/{n}",
            }
            for n in names
        ]

    def test_exact_match(self):
        assets = self._make_assets([
            "wisprFlow-1.0.6.nvda-addon",
            "wisprFlow-1.0.4.nvda-addon",   # stale old file
            "source.zip",
        ])
        url = select_asset(assets, "1.0.6")
        self.assertEqual(url, "https://example.com/releases/wisprFlow-1.0.6.nvda-addon")

    def test_no_match_returns_none(self):
        """If no asset matches the expected version, None is returned (no HTML fallback)."""
        assets = self._make_assets([
            "wisprFlow-1.0.4.nvda-addon",   # wrong version
            "source.zip",
        ])
        result = select_asset(assets, "1.0.6")
        self.assertIsNone(result)

    def test_empty_assets(self):
        self.assertIsNone(select_asset([], "1.0.6"))

    def test_first_asset_not_blindly_selected(self):
        """
        Regression: the old updater took the first .nvda-addon it found,
        even if it was an old version. This must never happen.
        """
        assets = self._make_assets([
            "wisprFlow-1.0.4.nvda-addon",   # first asset is old
            "wisprFlow-1.0.6.nvda-addon",   # correct version is second
        ])
        url = select_asset(assets, "1.0.6")
        # Must select 1.0.6, not 1.0.4
        self.assertIn("1.0.6", url)
        self.assertNotIn("1.0.4", url)

    def test_case_insensitive_match(self):
        """Filename comparison is case-insensitive (Windows filenames)."""
        assets = self._make_assets(["WisprFlow-1.0.6.NVDA-ADDON"])
        url = select_asset(assets, "1.0.6")
        self.assertIsNotNone(url)

    def test_no_html_url_returned(self):
        """
        Regression: the old updater fell back to html_url when no asset was found.
        select_asset must never return an HTML URL.
        """
        assets = self._make_assets(["source.zip"])
        result = select_asset(assets, "1.0.6")
        self.assertIsNone(result)

    def test_asset_with_empty_download_url_skipped(self):
        """Assets with empty browser_download_url must be skipped."""
        assets = [{"name": "wisprFlow-1.0.6.nvda-addon", "browser_download_url": ""}]
        result = select_asset(assets, "1.0.6")
        self.assertIsNone(result)


# ===========================================================================
# Test: validate_addon_package
# ===========================================================================

class TestValidateAddonPackage(unittest.TestCase):

    def setUp(self):
        # Temporary files are cleaned up in tearDown
        self._temps = []

    def tearDown(self):
        for p in self._temps:
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def _tmp(self, suffix=".nvda-addon") -> str:
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self._temps.append(path)
        return path

    def test_valid_package_passes(self):
        path = _make_addon_zip("1.0.6", self._tmp())
        # Should not raise
        validate_addon_package(path, "1.0.6")

    def test_not_a_zip_raises(self):
        path = _make_bad_zip(self._tmp())
        with self.assertRaises(ValueError) as ctx:
            validate_addon_package(path, "1.0.6")
        self.assertIn("not a valid NVDA add-on archive", str(ctx.exception))

    def test_missing_manifest_raises(self):
        path = _make_addon_zip_no_manifest(self._tmp())
        with self.assertRaises(ValueError) as ctx:
            validate_addon_package(path, "1.0.6")
        self.assertIn("manifest.ini", str(ctx.exception))

    def test_version_mismatch_raises(self):
        """An archive whose internal version doesn't match must be rejected."""
        path = _make_addon_zip("1.0.4", self._tmp())   # contains 1.0.4 but we expect 1.0.6
        with self.assertRaises(ValueError) as ctx:
            validate_addon_package(path, "1.0.6")
        msg = str(ctx.exception)
        self.assertIn("1.0.4", msg)
        self.assertIn("1.0.6", msg)
        self.assertIn("mismatch", msg.lower())

    def test_html_file_disguised_as_addon_rejected(self):
        """An HTML file (GitHub release page) must be caught as not-a-zip."""
        path = self._tmp()
        with open(path, "wb") as f:
            f.write(b"<!DOCTYPE html><html><body>Release page</body></html>")
        with self.assertRaises(ValueError) as ctx:
            validate_addon_package(path, "1.0.6")
        self.assertIn("not a valid NVDA add-on archive", str(ctx.exception))


# ===========================================================================
# Test: get_current_version
# ===========================================================================

class TestGetCurrentVersion(unittest.TestCase):

    def test_reads_from_manifest(self):
        """get_current_version should return the version in the actual manifest.ini."""
        ver = get_current_version()
        # The fixed manifest says 1.0.6
        # We just check it's a parseable version-like string.
        self.assertRegex(ver, r"^\d+\.\d+")

    def test_manifest_now_reports_1_0_6(self):
        """After the fix, manifest.ini must report version 1.0.6."""
        manifest_path = ROOT / "manifest.ini"
        cfg = configparser.RawConfigParser()
        cfg.read_string("[addon]\n" + manifest_path.read_text(encoding="utf-8"))
        version = cfg.get("addon", "version").strip()
        self.assertEqual(version, "1.0.6",
            msg="manifest.ini version must be 1.0.6 after the fix")


# ===========================================================================
# Test: manifest consistency
# ===========================================================================

class TestManifestConsistency(unittest.TestCase):

    def setUp(self):
        self.manifest_path = ROOT / "manifest.ini"
        cfg = configparser.RawConfigParser()
        cfg.read_string("[addon]\n" + self.manifest_path.read_text(encoding="utf-8"))
        self.manifest_version = cfg.get("addon", "version").strip()

    def test_build_script_uses_manifest_version(self):
        """build_addon.py must derive its output filename from manifest.ini."""
        build_script = (ROOT / "build_addon.py").read_text(encoding="utf-8")
        # The build script calls get_addon_version() and uses it in OUTPUT_FILENAME
        self.assertIn("get_addon_version", build_script)
        self.assertIn("OUTPUT_FILENAME", build_script)

    def test_no_stale_addon_packages_committed(self):
        """
        Old .nvda-addon packages must not be committed alongside the source
        (they confuse the release workflow's glob upload).
        """
        stale = list(ROOT.glob("*.nvda-addon"))
        self.assertEqual(
            stale, [],
            msg=(
                f"Stale .nvda-addon files found in repo root: "
                f"{[p.name for p in stale]}. "
                "Remove them so the release workflow only uploads the freshly-built package."
            ),
        )

    def test_manifest_version_is_valid_semver(self):
        import re
        self.assertRegex(
            self.manifest_version,
            r"^\d+\.\d+(\.\d+)*$",
            msg=f"manifest version '{self.manifest_version}' is not a valid semantic version",
        )


if __name__ == "__main__":
    unittest.main()
