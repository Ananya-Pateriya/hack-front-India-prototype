"""Sarvam AI voice assistant for FrostMind (Bulbul v3 TTS + Saaras v3 STT)."""
from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from sarvamai import SarvamAI

CACHE_DIR = Path(tempfile.gettempdir()) / "frostmind_tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _client() -> SarvamAI | None:
    key = os.getenv("SARVAM_API_KEY", "").strip()
    return SarvamAI(api_subscription_key=key) if key else None


def _offline_tts_wav(text: str) -> bytes | None:
    """Zero-dependency local Windows SAPI fallback if API quota/network is unavailable."""
    try:
        out_wav = CACHE_DIR / "offline_fallback.wav"
        safe_text = text.replace('"', "'").replace("\n", " ")
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f'$s.SetOutputToWaveFile("{out_wav}");'
            f'$s.Speak("{safe_text}");'
            "$s.Dispose()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=8)
        return out_wav.read_bytes() if out_wav.exists() else None
    except Exception:
        return None


def build_spoken_prompt(card: dict, lang: str = "hi-IN") -> str:
    is_flatmate = card.get("flatmate_mode", False)
    due = [] if is_flatmate else [m["med_name"] for m in card["due"]]
    missed = [] if is_flatmate else [m["med_name"] for m in card["missed"]]
    urgent = [e["name"] for e in card["urgent"]]
    expired = [e["name"] for e in card["expired"]]

    if lang == "hi-IN":
        parts = ["नमस्ते।"]
        if missed:
            parts.append(f"आपकी {', '.join(missed)} की दवा पहले छूट गई थी।")
        if due:
            parts.append(f"अभी {card['meal']} के साथ {', '.join(due)} ले लीजिए।")
        if expired:
            parts.append(f"फ्रिज में {', '.join(expired)} खराब हो चुका है, उसे निकाल दें।")
        if urgent:
            parts.append(f"आज {', '.join(urgent)} पहले इस्तेमाल कर लें।")
        if len(parts) == 1:
            parts.append("फ्रिज में सब कुछ ताज़ा है।")
        return " ".join(parts)

    parts = []
    if missed:
        parts.append(f"Reminder: you missed {', '.join(missed)} earlier.")
    if due:
        parts.append(f"Please take {', '.join(due)} with your {card['meal'].lower()}.")
    if expired:
        parts.append(f"Discard expired {', '.join(expired)}.")
    if urgent:
        parts.append(f"Use {', '.join(urgent)} first before it spoils.")
    return " ".join(parts) or "Everything in your fridge is fresh."


def speak_card(card: dict, lang: str = "hi-IN", speaker: str = "priya") -> tuple[bytes | None, str | None]:
    """Returns (wav_bytes, error_message). Uses Sarvam Bulbul v3, cached locally,
    with automatic offline Windows speech fallback."""
    text = build_spoken_prompt(card, lang=lang)
    digest = hashlib.sha256(f"{lang}:{speaker}:{text}".encode()).hexdigest()[:16]
    cached_file = CACHE_DIR / f"{digest}.wav"

    if cached_file.exists():
        return cached_file.read_bytes(), None

    client = _client()
    if client:
        try:
            resp = client.text_to_speech.convert(
                text=text,
                target_language_code=lang,
                model="bulbul:v3",
                speaker=speaker,
            )
            audio_b64 = resp.audios[0] if getattr(resp, "audios", None) else None
            if audio_b64:
                wav_bytes = base64.b64decode(audio_b64)
                cached_file.write_bytes(wav_bytes)
                return wav_bytes, None
        except Exception as exc:
            fallback = _offline_tts_wav(build_spoken_prompt(card, lang="en-IN"))
            if fallback:
                return fallback, None
            return None, f"Sarvam TTS error: {exc}"

    fallback = _offline_tts_wav(build_spoken_prompt(card, lang="en-IN"))
    if fallback:
        return fallback, None
    return None, "SARVAM_API_KEY is not set."


def transcribe_voice(audio_bytes: bytes) -> tuple[str | None, str | None]:
    """Returns (transcript, error_message)."""
    client = _client()
    if not client:
        return None, "SARVAM_API_KEY is not set."
    if not audio_bytes:
        return None, "No audio recorded."

    try:
        resp = client.speech_to_text.transcribe(
            file=("voice.wav", audio_bytes, "audio/wav"),
            model="saaras:v3",
            mode="codemix",
        )
        text = getattr(resp, "transcript", None)
        if not text:
            return None, "Sarvam returned an empty transcript—try speaking louder."
        return text, None
    except Exception as exc:
        return None, f"Sarvam STT error: {exc}"