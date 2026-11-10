"""
Authentication Manager for NVDA Wispr Flow Add-on.
Implements the official Device Code Browser Login without API keys.
"""

import threading
import time
import urllib.request
import urllib.parse
import json
import uuid
import webbrowser
from typing import Optional

from .session_store import SessionStore

LOGIN_PAGE_URL = "https://wisprflow.ai/login"
DEVICE_POLL_URL = "https://api.wisprflow.ai/device/poll"
SUPABASE_TOKEN_URL = "https://dodjkfqhwrzqjwkfnthl.supabase.co/auth/v1/token"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRvZGprZnFod3J6cWp3a2ZudGhsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MTk4ODQzMDcsImV4cCI6MjAzNTQ2MDMwN30.h6EeQ_6kqFeznH25icVUX0Szn9__kc8HoSXAsxxBWG8"


class AuthManager:
    def __init__(self, session_store: Optional[SessionStore] = None):
        self.store = session_store or SessionStore()
        self.is_logging_in = False

    def start_browser_login(self, on_success=None, on_error=None):
        """Start async device authentication loop."""
        if self.is_logging_in:
            return
        threading.Thread(
            target=self._login_worker,
            args=(on_success, on_error),
            daemon=True
        ).start()

    def _login_worker(self, on_success, on_error):
        self.is_logging_in = True
        device_code = str(uuid.uuid4())
        login_url = f"{LOGIN_PAGE_URL}?device_code={device_code}"

        try:
            webbrowser.open(login_url)
        except Exception as e:
            self.is_logging_in = False
            if on_error:
                on_error(f"Failed to open browser: {e}")
            return

        start_time = time.time()
        timeout_seconds = 300

        while time.time() - start_time < timeout_seconds:
            try:
                req = urllib.request.Request(
                    f"{DEVICE_POLL_URL}?device_code={device_code}",
                    headers={"Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        status = data.get("status")

                        if status == "pending":
                            time.sleep(2.0)
                            continue

                        access_token = data.get("access_token")
                        refresh_token = data.get("refresh_token")

                        if access_token:
                            name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "User"
                            self.store.save_session(
                                access_token=access_token,
                                refresh_token=refresh_token,
                                expires_in=3600,
                                email=name
                            )
                            self.is_logging_in = False
                            if on_success:
                                on_success(name)
                            return
            except Exception:
                pass
            time.sleep(2.0)

        self.is_logging_in = False
        if on_error:
            on_error("Sign-in timed out. Please try again.")

    def refresh_access_token_if_needed(self) -> bool:
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
            payload = json.dumps({"refresh_token": refresh_token}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_ANON_KEY
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    new_access = data.get("access_token")
                    new_refresh = data.get("refresh_token", refresh_token)
                    expires_in = float(data.get("expires_in", 3600))
                    self.store.update_tokens(new_access, new_refresh, expires_in)
                    return True
        except Exception:
            pass
        return False

    def get_account_profile(self) -> dict:
        """Fetches full authenticated user profile from the backend API or returns cached profile."""
        session = self.store.get_session()
        if not session or not session.get("access_token"):
            return {}

        self.refresh_access_token_if_needed()
        session = self.store.get_session()
        token = session.get("access_token")

        try:
            req = urllib.request.Request(
                "https://dodjkfqhwrzqjwkfnthl.supabase.co/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_ANON_KEY,
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cur_data = self.store._read_data()
                cur_data["user_profile"] = data
                self.store._write_data(cur_data)
                return data
        except Exception:
            return self.store._read_data().get("user_profile", {})

