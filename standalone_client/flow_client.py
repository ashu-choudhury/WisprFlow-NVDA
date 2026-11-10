"""
Wispr Flow Backend gRPC Client.
Uses Wispr Flow's official high-performance gRPC transcription protocol
(inference.wisprflow.com:443) with your active user session.
"""

import base64
import json
from typing import Optional, List, Dict, Any

from auth_manager import AuthManager
from session_store import SessionStore
from wisprflow.client import WisprClient
from wisprflow.models import Language, RuntimeRoute, TranscriptionOptions, WritingStyle


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
        """Extract user_id (sub claim) from JWT in SQLite session."""
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
        """Return valid access token, auto-refreshing if expired."""
        self.auth.refresh_access_token_if_needed()
        session = self.store.get_session()
        if session and session.get("access_token"):
            return session["access_token"]
        return ""

    def _init_client(self):
        """Initialize WisprClient with SQLite token callback."""
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
        wav_bytes: bytes,
        language: str = "en",
        style: str = "default",
        custom_vocabulary: Optional[List[str]] = None,
        app_context: Optional[str] = None,
    ) -> Optional[str]:
        """
        Sends 16kHz WAV audio bytes over gRPC to Wispr Flow inference server.
        Returns the formatted, punctuation-corrected final transcription.
        """
        if not wav_bytes:
            return None

        if self._wispr_client is None:
            self._init_client()

        # Map language string to Wispr Language enum
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
                wav_bytes,
                options=options
            )
            final_text = result.final.strip() if result and result.final else None
            return final_text
        except Exception as e:
            print(f"[FlowClient] gRPC Transcription error: {e}")
            return None
