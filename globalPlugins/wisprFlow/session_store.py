"""
JSON Session Store for NVDA Wispr Flow Add-on.
Stores credentials in %APPDATA%/nvda/wisprFlow_session.json
Pure Python with zero external C-dependencies (no sqlite3 required).
"""

import json
import os
import time
from typing import Optional, Dict, Any

DEFAULT_SESSION_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "nvda",
    "wisprFlow_session.json"
)


class SessionStore:
    def __init__(self, file_path: str = DEFAULT_SESSION_FILE):
        self.file_path = file_path

    def _read_data(self) -> Dict[str, Any]:
        if not os.path.isfile(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_data(self, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
        temp_path = self.file_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.file_path)
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    def save_session(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: float = 3600,
        email: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        now = time.time()
        expires_at = now + expires_in if expires_in else None
        data = self._read_data()
        data.update({
            "access_token": access_token,
            "refresh_token": refresh_token or data.get("refresh_token"),
            "expires_at": expires_at,
            "email": email or data.get("email"),
            "user_id": user_id or data.get("user_id"),
            "updated_at": now,
        })
        if "created_at" not in data:
            data["created_at"] = now
        self._write_data(data)

    def get_session(self) -> Optional[Dict[str, Any]]:
        data = self._read_data()
        if data and data.get("access_token"):
            return data
        return None

    def is_token_expired(self, leeway_seconds: float = 60.0) -> bool:
        session = self.get_session()
        if not session or not session.get("access_token"):
            return True
        expires_at = session.get("expires_at")
        if not expires_at:
            return False
        return time.time() >= (expires_at - leeway_seconds)

    def update_tokens(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: float = 3600,
    ) -> None:
        now = time.time()
        expires_at = now + expires_in if expires_in else None
        data = self._read_data()
        data["access_token"] = access_token
        if refresh_token:
            data["refresh_token"] = refresh_token
        data["expires_at"] = expires_at
        data["updated_at"] = now
        self._write_data(data)

    def record_usage(self, word_count: int, audio_seconds: float) -> dict:
        data = self._read_data()
        usage = data.get("usage", {"total_dictations": 0, "total_words": 0, "total_audio_seconds": 0.0})
        usage["total_dictations"] = usage.get("total_dictations", 0) + 1
        usage["total_words"] = usage.get("total_words", 0) + word_count
        usage["total_audio_seconds"] = round(usage.get("total_audio_seconds", 0.0) + audio_seconds, 1)
        data["usage"] = usage
        self._write_data(data)
        return usage

    def get_usage(self) -> dict:
        data = self._read_data()
        return data.get("usage", {"total_dictations": 0, "total_words": 0, "total_audio_seconds": 0.0})

    def clear_session(self) -> None:
        try:
            if os.path.isfile(self.file_path):
                os.remove(self.file_path)
        except Exception:
            self._write_data({})
