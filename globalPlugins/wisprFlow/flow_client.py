"""
gRPC Transcription Client for NVDA Wispr Flow Add-on.
Dynamically loads bundled gRPC libraries matching the active Python runtime version.
"""

import base64
import json
import os
import sys
from typing import Optional, List

# Ensure bundled gRPC matching current Python version is on sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_py_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
_lib_path = os.path.join(_current_dir, "lib", _py_tag)
if os.path.isdir(_lib_path) and _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

# Also ensure wisprflow package directory is discoverable
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from .auth import AuthManager
from .session_store import SessionStore
from .wisprflow.client import WisprClient
from .wisprflow.models import Language, RuntimeRoute, TranscriptionOptions


class FlowClient:
    def __init__(
        self,
        session_store: Optional[SessionStore] = None,
        auth_manager: Optional[AuthManager] = None,
    ):
        self.store = session_store or SessionStore()
        self.auth = auth_manager or AuthManager(self.store)
        self._wispr_client: Optional[WisprClient] = None

    def _get_user_id(self) -> str:
        session = self.store.get_session()
        if session and session.get("access_token"):
            tok = session["access_token"]
            try:
                parts = tok.split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1] + "=="
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    return payload.get("sub", "")
            except Exception:
                pass
        return ""

    def _get_access_token(self) -> str:
        self.auth.refresh_access_token_if_needed()
        session = self.store.get_session()
        if session and session.get("access_token"):
            return session["access_token"]
        return ""

    def _init_client(self):
        user_id = self._get_user_id()
        self._wispr_client = WisprClient(
            auth=self._get_access_token,
            user_id=user_id,
            route=RuntimeRoute(
                host="inference.wisprflow.com",
                port=443,
                method="/flow_api.v1.TranscriptionService/TranscribeStream"
            ),
            timeout=30.0,
        )

    def transcribe(
        self,
        wav_path_or_bytes,
        language: str = "en",
        custom_vocabulary: Optional[List[str]] = None,
    ) -> Optional[str]:
        if not wav_path_or_bytes:
            return None

        if self._wispr_client is None:
            self._init_client()

        lang_map = {
            "en": Language.EN,
            "auto": Language.UNSPECIFIED,
            "es": Language.ES,
            "fr": Language.FR,
            "de": Language.DE,
            "hi": Language.HI,
            "hi_en": Language.HI_EN,
        }
        target_lang = lang_map.get(language.lower(), Language.EN)

        options = TranscriptionOptions(
            languages=[target_lang],
            dictionary=custom_vocabulary or [],
        )

        try:
            result = self._wispr_client.transcribe(
                wav_path_or_bytes,
                options=options
            )
            if result and result.final:
                return result.final.strip()
            return None
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[WisprFlow] Transcription error: {e}")
            return None
