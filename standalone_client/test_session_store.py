"""
Unit tests for SessionStore (SQLite persistence).
"""

import os
import tempfile
import time
import unittest
from session_store import SessionStore


class TestSessionStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_session.db")
        self.store = SessionStore(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_get_session(self):
        self.assertIsNone(self.store.get_session())
        self.store.save_session(
            access_token="test_access_123",
            refresh_token="test_refresh_456",
            expires_in=3600,
            email="pilot@eurofly.org",
            user_id="user_789"
        )
        session = self.store.get_session()
        self.assertIsNotNone(session)
        self.assertEqual(session["access_token"], "test_access_123")
        self.assertEqual(session["refresh_token"], "test_refresh_456")
        self.assertEqual(session["email"], "pilot@eurofly.org")
        self.assertEqual(session["user_id"], "user_789")

    def test_is_token_expired(self):
        # Fresh token
        self.store.save_session("tok", expires_in=3600)
        self.assertFalse(self.store.is_token_expired())

        # Expired token
        self.store.save_session("tok_expired", expires_in=-10)
        self.assertTrue(self.store.is_token_expired())

    def test_update_tokens(self):
        self.store.save_session("old_access", "old_refresh", expires_in=100)
        self.store.update_tokens("new_access", "new_refresh", expires_in=7200)
        session = self.store.get_session()
        self.assertEqual(session["access_token"], "new_access")
        self.assertEqual(session["refresh_token"], "new_refresh")

    def test_clear_session(self):
        self.store.save_session("token_to_clear")
        self.assertIsNotNone(self.store.get_session())
        self.store.clear_session()
        self.assertIsNone(self.store.get_session())

    def test_settings(self):
        self.assertEqual(self.store.get_setting("hotkey"), "f8")
        self.store.set_setting("hotkey", "caps_lock")
        self.assertEqual(self.store.get_setting("hotkey"), "caps_lock")


if __name__ == "__main__":
    unittest.main()
