"""
Authentication & Sign-In Manager for Accessible Wispr Flow.
Implements the exact official Wispr Flow Desktop Device Authentication Protocol.
No developer API keys required.
"""

import glob
import json
import os
import re
import time
import urllib.parse
import uuid
import webbrowser
from typing import Optional, Dict, Any

import requests

from session_store import SessionStore

LOGIN_PAGE_URL = "https://wisprflow.ai/login"
API_BASE_URL = "https://api.wisprflow.ai"
DEVICE_POLL_URL = f"{API_BASE_URL}/device/poll"
SUPABASE_TOKEN_URL = "https://dodjkfqhwrzqjwkfnthl.supabase.co/auth/v1/token"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRvZGprZnFod3J6cWp3a2ZudGhsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MTk4ODQzMDcsImV4cCI6MjAzNTQ2MDMwN30.h6EeQ_6kqFeznH25icVUX0Szn9__kc8HoSXAsxxBWG8"


class AuthManager:
    def __init__(self, session_store: Optional[SessionStore] = None):
        self.store = session_store or SessionStore()

    def start_browser_login(self, timeout_seconds: int = 300) -> bool:
        """
        Launches the official Wispr Flow device authentication flow.
        1. Generates a unique device UUID.
        2. Opens default browser to https://wisprflow.ai/login?device_code=<UUID>.
        3. Polls https://api.wisprflow.ai/device/poll?device_code=<UUID> until completion.
        4. Saves received tokens into local SQLite database.
        """
        device_code = str(uuid.uuid4())
        login_url = f"{LOGIN_PAGE_URL}?device_code={device_code}"

        print("\n" + "=" * 65)
        print("  WISPR FLOW OFFICIAL DESKTOP LOGIN")
        print("  Authenticating normally via browser (Google, Apple, Email, etc.)")
        print("=" * 65)
        print(f"\n[Auth] Generated Device Code: {device_code}")
        print(f"[Auth] Opening browser: {login_url}")
        print("[Auth] Please complete sign-in in your browser...")

        webbrowser.open(login_url)

        start_time = time.time()
        poll_interval = 2.0

        while time.time() - start_time < timeout_seconds:
            try:
                resp = requests.get(
                    f"{DEVICE_POLL_URL}?device_code={device_code}",
                    headers={"Accept": "application/json"},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status")

                    if status == "pending":
                        # Still waiting for user to complete login in browser
                        time.sleep(poll_interval)
                        continue

                    access_token = data.get("access_token")
                    refresh_token = data.get("refresh_token")

                    if access_token:
                        name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "User"
                        print(f"\n[Auth] Sign-in successful! Welcome, {name}.")
                        
                        self.store.save_session(
                            access_token=access_token,
                            refresh_token=refresh_token,
                            expires_in=3600,
                            email=name
                        )
                        print("[Auth] Tokens saved to local SQLite database (session.db).")
                        return True
                    else:
                        print(f"\n[Auth] Unexpected response: {data}")
                        time.sleep(poll_interval)
                else:
                    print(f"[Auth] Poll error (HTTP {resp.status_code}): {resp.text}")
                    time.sleep(poll_interval)

            except requests.RequestException as e:
                print(f"[Auth] Network error during poll: {e}")
                time.sleep(poll_interval)

        print("\n[Auth] Sign-in timed out. Please try running again.")
        return False

    def auto_discover_desktop_session(self) -> bool:
        """
        Check if an active Wispr Flow desktop session exists in standard Windows app paths:
        - %APPDATA%/wisprflow-re/config.json
        - %APPDATA%/Wispr Flow/Local Storage/leveldb
        """
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return False

        # 1. Check wisprflow-re config.json
        re_config_path = os.path.join(appdata, "wisprflow-re", "config.json")
        if os.path.isfile(re_config_path):
            try:
                with open(re_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("access_token")
                    refresh = data.get("refresh_token")
                    if token:
                        self.store.save_session(token, refresh, expires_in=7200)
                        print("[Auth] Imported session from wisprflow-re config.json!")
                        return True
            except Exception:
                pass

        # 2. Check LevelDB stores for Supabase session strings
        leveldb_paths = [
            os.path.join(appdata, "Wispr Flow", "Local Storage", "leveldb"),
            os.path.join(appdata, "WisprFlow", "Local Storage", "leveldb"),
        ]
        token_regex = re.compile(rb'eyJhbGciOi[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')

        for ldb_dir in leveldb_paths:
            if os.path.isdir(ldb_dir):
                for filepath in glob.glob(os.path.join(ldb_dir, "*.ldb")) + glob.glob(os.path.join(ldb_dir, "*.log")):
                    try:
                        with open(filepath, "rb") as f:
                            content = f.read()
                            matches = token_regex.findall(content)
                            if matches:
                                jwt_token = matches[-1].decode("ascii")
                                self.store.save_session(jwt_token, expires_in=3600)
                                print(f"[Auth] Discovered session token from desktop storage ({os.path.basename(filepath)})!")
                                return True
                    except Exception:
                        continue

        return False

    def refresh_access_token_if_needed(self) -> bool:
        """
        Checks if token is expired, and if so, uses refresh_token to renew it via Supabase.
        """
        if not self.store.is_token_expired(leeway_seconds=120):
            return True

        session = self.store.get_session()
        if not session:
            return False

        refresh_token = session.get("refresh_token")
        if not refresh_token:
            return False

        try:
            url = f"{SUPABASE_TOKEN_URL}?grant_type=refresh_token"
            resp = requests.post(
                url,
                json={"refresh_token": refresh_token},
                headers={
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_ANON_KEY
                },
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                new_access = data.get("access_token")
                new_refresh = data.get("refresh_token", refresh_token)
                expires_in = float(data.get("expires_in", 3600))
                self.store.update_tokens(new_access, new_refresh, expires_in)
                print("[Auth] Access token refreshed automatically via SQLite!")
                return True
            else:
                print(f"[Auth] Token refresh failed (HTTP {resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            print(f"[Auth] Token refresh error: {e}")
            return False
