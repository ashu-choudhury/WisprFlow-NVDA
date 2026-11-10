"""
Build & Package Script for Wispr Flow NVDA Add-on.
Creates wisprFlow-1.0.0.nvda-addon and optionally installs it directly into NVDA.
"""

import argparse
import os
import shutil
import zipfile

ADDON_NAME = "wisprFlow"
VERSION = "1.0.0"
OUTPUT_FILENAME = f"{ADDON_NAME}-{VERSION}.nvda-addon"


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
    parser.add_argument("--install", action="store_true", help="Install directly into NVDA addons folder")
    args = parser.parse_args()

    pkg_path = build_addon()

    if args.install:
        install_to_nvda()


if __name__ == "__main__":
    main()
