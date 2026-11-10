"""
SQLite Session & Settings Store for Accessible Wispr Flow Client.
Stores user authentication tokens, expiry, and configuration locally.
"""

import contextlib
import os
import sqlite3
import time
from typing import Optional, Dict, Any

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session.db")


class SessionStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize SQLite database tables."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Session table (singleton row id=1)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at REAL,
                    email TEXT,
                    user_id TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)

            # Settings table (key-value)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Seed default settings if empty
            default_settings = {
                "hotkey": "f8",
                "hotkey_mode": "push_to_talk",  # 'push_to_talk' or 'toggle'
                "language": "en",
                "speech_feedback": "true",
                "sound_cues": "true",
                "writing_style": "default",
            }
            for k, v in default_settings.items():
                cursor.execute("""
                    INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)
                """, (k, v))
            conn.commit()

    def save_session(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: float = 3600,
        email: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Save or replace the active user session."""
        now = time.time()
        expires_at = now + expires_in if expires_in else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (id, access_token, refresh_token, expires_at, email, user_id, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = COALESCE(excluded.refresh_token, sessions.refresh_token),
                    expires_at = excluded.expires_at,
                    email = COALESCE(excluded.email, sessions.email),
                    user_id = COALESCE(excluded.user_id, sessions.user_id),
                    updated_at = excluded.updated_at
            """, (access_token, refresh_token, expires_at, email, user_id, now, now))
            conn.commit()

    def get_session(self) -> Optional[Dict[str, Any]]:
        """Retrieve current session if it exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def is_token_expired(self, leeway_seconds: float = 60.0) -> bool:
        """Check if access token is expired or within leeway window."""
        session = self.get_session()
        if not session or not session.get("access_token"):
            return True
        expires_at = session.get("expires_at")
        if not expires_at:
            return False  # If no expiry recorded, assume valid
        return time.time() >= (expires_at - leeway_seconds)

    def update_tokens(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: float = 3600,
    ) -> None:
        """Update tokens following a refresh call."""
        now = time.time()
        expires_at = now + expires_in if expires_in else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if refresh_token:
                cursor.execute("""
                    UPDATE sessions
                    SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = ?
                    WHERE id = 1
                """, (access_token, refresh_token, expires_at, now))
            else:
                cursor.execute("""
                    UPDATE sessions
                    SET access_token = ?, expires_at = ?, updated_at = ?
                    WHERE id = 1
                """, (access_token, expires_at, now))
            conn.commit()

    def clear_session(self) -> None:
        """Log out by clearing session table."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE id = 1")
            conn.commit()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a configuration setting."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row["value"]
            return default

    def set_setting(self, key: str, value: str) -> None:
        """Update a configuration setting."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, str(value)))
            conn.commit()
