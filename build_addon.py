"""
Build & Package Script for Wispr Flow NVDA Add-on.
Creates wisprFlow-1.0.0.nvda-addon and optionally installs it directly into NVDA.
Supports automatic dependency fetching for Python 3.11, 3.12, and 3.13 (win_amd64).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ADDON_NAME = "wisprFlow"
VERSION = "1.0.4"
OUTPUT_FILENAME = f"{ADDON_NAME}-{VERSION}.nvda-addon"
PYTHON_VERSIONS = ["311", "312", "313"]


def fetch_dependencies():
    """Fetches and extracts gRPC wheels for Windows x64 across supported Python runtimes."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    lib_dir = os.path.join(current_dir, "globalPlugins", ADDON_NAME, "lib")
    os.makedirs(lib_dir, exist_ok=True)

    print("[Deps] Fetching pre-compiled dependencies for NVDA Python runtimes...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        for py_ver in PYTHON_VERSIONS:
            target_py_dir = os.path.join(lib_dir, f"py{py_ver}")
            if os.path.isdir(target_py_dir) and os.path.isdir(os.path.join(target_py_dir, "grpc")):
                print(f"[Deps] py{py_ver} already present, skipping.")
                continue

            print(f"[Deps] Downloading grpcio for Python {py_ver} (win_amd64)...")
            ver_tmp = os.path.join(tmp_dir, f"py{py_ver}")
            os.makedirs(ver_tmp, exist_ok=True)

            cmd = [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--platform",
                "win_amd64",
                "--python-version",
                py_ver,
                "grpcio>=1.68.0",
                "typing_extensions>=4.10.0",
                "--dest",
                ver_tmp,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[Deps] Warning: pip download failed for {py_ver}: {res.stderr}")
                continue

            os.makedirs(target_py_dir, exist_ok=True)
            for f in os.listdir(ver_tmp):
                if f.endswith(".whl"):
                    whl_path = os.path.join(ver_tmp, f)
                    with zipfile.ZipFile(whl_path, "r") as z:
                        z.extractall(target_py_dir)

            print(f"[Deps] Extracted dependencies for Python {py_ver} into lib/py{py_ver}.")


def build_addon(output_path: str = OUTPUT_FILENAME) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_abs_path = os.path.join(current_dir, output_path)

    print(f"[Build] Packaging {OUTPUT_FILENAME}...")

    if os.path.exists(output_abs_path):
        os.remove(output_abs_path)

    # Exclude unwanted extensions/cache
    exclude_exts = {".pyc", ".pyo", ".git", ".whl"}
    exclude_dirs = {"__pycache__", ".git"}

    with zipfile.ZipFile(output_abs_path, "w", zipfile.ZIP_DEFLATED) as z:
        # Add manifest.ini
        manifest_path = os.path.join(current_dir, "manifest.ini")
        if os.path.exists(manifest_path):
            z.write(manifest_path, "manifest.ini")

        # Add globalPlugins
        plugins_dir = os.path.join(current_dir, "globalPlugins")
        for root, dirs, files in os.walk(plugins_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in exclude_exts or f.endswith(".tmp"):
                    continue
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, current_dir)
                z.write(full_path, rel_path)

    size_mb = os.path.getsize(output_abs_path) / (1024 * 1024)
    print(f"[Build] Successfully created {OUTPUT_FILENAME} ({size_mb:.2f} MB)")
    return output_abs_path


def install_to_nvda():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        print("[Install] APPDATA environment variable not found.")
        return

    nvda_addons_dir = os.path.join(appdata, "nvda", "addons", ADDON_NAME)
    source_dir = os.path.join(current_dir, "globalPlugins", ADDON_NAME)
    manifest_source = os.path.join(current_dir, "manifest.ini")

    print(f"[Install] Installing directly to: {nvda_addons_dir}")
    os.makedirs(os.path.join(nvda_addons_dir, "globalPlugins", ADDON_NAME), exist_ok=True)

    # Copy manifest.ini
    shutil.copy2(manifest_source, os.path.join(nvda_addons_dir, "manifest.ini"))

    # Copy files
    dest_plugin_dir = os.path.join(nvda_addons_dir, "globalPlugins", ADDON_NAME)
    for root, dirs, files in os.walk(source_dir):
        rel = os.path.relpath(root, source_dir)
        target_dir = os.path.join(dest_plugin_dir, rel) if rel != "." else dest_plugin_dir
        os.makedirs(target_dir, exist_ok=True)
        for f in files:
            src_file = os.path.join(root, f)
            dst_file = os.path.join(target_dir, f)
            try:
                shutil.copy2(src_file, dst_file)
            except PermissionError:
                # If a dll/pyd is locked by a running NVDA process, skip it
                pass

    print(f"[Install] Add-on installed successfully! Please restart NVDA (Ctrl+Alt+N).")


def main():
    parser = argparse.ArgumentParser(description="Build and install Wispr Flow NVDA add-on")
    parser.add_argument("--fetch-deps", action="store_true", help="Download and extract gRPC runtime wheels")
    parser.add_argument("--install", action="store_true", help="Install directly into NVDA addons folder")
    args = parser.parse_args()

    if args.fetch_deps:
        fetch_dependencies()

    pkg_path = build_addon()

    if args.install:
        install_to_nvda()


if __name__ == "__main__":
    main()
