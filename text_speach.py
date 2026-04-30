import asyncio
import io
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pyttsx3


_SLOVAK_LANG_CODES = {"sk", "sk-sk", "sk_sk"}
_SLOVAK_NAME_MARKERS = ("slovak", "slovenčina", "slovensky", "slovensk")


def _normalize_language(lang: object) -> str:
    if isinstance(lang, bytes):
        try:
            lang = lang.decode("utf-8", errors="ignore")
        except Exception:
            lang = str(lang)
    text = str(lang).strip().lower()
    text = text.replace("_", "-")
    text = re.sub(r"[^a-z-]", "", text)
    return text


def _voice_language_codes(voice: object) -> set[str]:
    languages = getattr(voice, "languages", []) or []
    codes = {_normalize_language(lang) for lang in languages if lang is not None}
    return {code for code in codes if code}


def _score_voice(voice: object) -> int:
    voice_id = str(getattr(voice, "id", "")).lower()
    name = str(getattr(voice, "name", "")).lower()
    codes = _voice_language_codes(voice)

    if codes & _SLOVAK_LANG_CODES:
        return 3
    if any(marker in name for marker in _SLOVAK_NAME_MARKERS):
        return 2
    if any(marker in voice_id for marker in _SLOVAK_NAME_MARKERS):
        return 2

    if re.search(r"(^|[^a-z])sk([-_]?sk)?([^a-z]|$)", name):
        return 1
    if re.search(r"(^|[^a-z])sk([-_]?sk)?([^a-z]|$)", voice_id):
        return 1
    return 0


def _pick_slovak_voice(engine: pyttsx3.Engine) -> str | None:
    voices = engine.getProperty("voices") or []
    best_score = 0
    best_id: str | None = None
    for voice in voices:
        score = _score_voice(voice)
        if score > best_score:
            best_score = score
            best_id = getattr(voice, "id", None)
    return best_id if best_score > 0 else None


def slovak_voice_available() -> bool:
    engine = pyttsx3.init()
    return _pick_slovak_voice(engine) is not None


def _ensure_online_tts() -> bool:
    """Auto-install gtts on first use (user-level, no admin)."""
    try:
        import gtts  # noqa: F401
        return True
    except ImportError:
        pass

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--user",
                "--quiet",
                "gtts==2.4.0",
            ],
            check=False,
            capture_output=True,
            timeout=60,
        )
        import gtts  # noqa: F401
        return True
    except Exception as exc:
        print(f"[TTS] Nepodarilo sa nainštalovať online TTS: {exc}")
        return False


def synthesize_mp3_bytes(text: str) -> bytes:
    """Create Slovak MP3 audio for browser playback using gTTS."""
    if not text:
        return b""
    if not _ensure_online_tts():
        raise RuntimeError("Online TTS nie je dostupné.")
    import gtts

    buffer = io.BytesIO()
    tts = gtts.gTTS(text, lang="sk", slow=False)
    tts.write_to_fp(buffer)
    return buffer.getvalue()


async def _speak_online(text: str) -> None:
    """Speak text using Google TTS (sk language) - gtts has built-in playback."""
    try:
        import gtts

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp_path = Path(tmp.name)

        tts = gtts.gTTS(text, lang="sk", slow=False)
        tts.save(str(tmp_path))
        
        # gtts can play directly or use native player
        import subprocess as sp
        try:
            sp.run(["start", str(tmp_path)], check=False, shell=True, capture_output=True)
        except Exception:
            print(f"[TTS] Zvuk uložený v {tmp_path} (nie je možné prehrať)")

        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
    except Exception as exc:
        print(f"[TTS] Online chyba: {exc}")


def prehovor(text: str) -> None:
    """Čítaj text po slovensky: lokálny hlas → online TTS → log."""
    if not text:
        return

    # Skúsi lokálny hlas
    try:
        engine = pyttsx3.init()
        slovak_voice = _pick_slovak_voice(engine)
        if slovak_voice:
            engine.setProperty("voice", slovak_voice)
            engine.say(text)
            engine.runAndWait()
            return
    except Exception as exc:
        print(f"[TTS] Lokálny hlas chyba: {exc}")

    # Skúsi online TTS
    if _ensure_online_tts():
        try:
            asyncio.run(_speak_online(text))
            return
        except Exception as exc:
            print(f"[TTS] Online nepodarilo: {exc}")

    # Fallback: len log
    print(f"[TTS] Offline režim. Text: {text[:80]}...")