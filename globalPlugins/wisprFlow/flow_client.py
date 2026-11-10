"""
gRPC Transcription Client for NVDA Wispr Flow Add-on.
Dynamically loads bundled gRPC libraries matching the active Python runtime version.
Supports multi-chunk long speech segmentation and resilient exception handling.
"""

import base64
import io
import json
import os
import sys
import wave
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
            timeout=180.0,  # 3-minute timeout for long speech
        )

    def _segment_audio(self, wav_path_or_bytes, max_segment_sec: int = 60) -> List[bytes]:
        """Splits long WAV audio into safe segments (default 60s each, ~1.9MB) using standard library wave."""
        if isinstance(wav_path_or_bytes, bytes):
            stream = io.BytesIO(wav_path_or_bytes)
        elif os.path.isfile(str(wav_path_or_bytes)):
            with open(str(wav_path_or_bytes), "rb") as f:
                stream = io.BytesIO(f.read())
        else:
            return []

        try:
            with wave.open(stream, "rb") as wf:
                framerate = wf.getframerate()
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                nframes = wf.getnframes()
                frames = wf.readframes(nframes)
        except Exception:
            # If not a standard WAV header, return raw bytes as single payload
            stream.seek(0)
            return [stream.read()]

        bytes_per_sec = framerate * sampwidth * nchannels
        max_bytes = max_segment_sec * bytes_per_sec

        if len(frames) <= max_bytes:
            # Short audio: return single WAV
            stream.seek(0)
            return [stream.read()]

        # Long audio: slice into max_segment_sec chunks
        segments = []
        offset = 0
        total_len = len(frames)
        while offset < total_len:
            end = min(offset + max_bytes, total_len)
            chunk_frames = frames[offset:end]
            out = io.BytesIO()
            with wave.open(out, "wb") as wf:
                wf.setnchannels(nchannels)
                wf.setsampwidth(sampwidth)
                wf.setframerate(framerate)
                wf.writeframes(chunk_frames)
            segments.append(out.getvalue())
            offset = end

        return segments

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

        segments = self._segment_audio(wav_path_or_bytes)
        if not segments:
            return None

        results = []
        for segment_bytes in segments:
            # Let exceptions propagate to caller so retry logic can protect the audio!
            result = self._wispr_client.transcribe(
                segment_bytes,
                options=options
            )
            if result and result.final and result.final.strip():
                results.append(result.final.strip())

        if results:
            return "\n\n".join(results)
        return None
