"""Optional Sarvam Saaras v4 STT and Bulbul v4 Flash TTS integration.
The application remains usable when credentials, network access, or credits are unavailable.
"""
from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

import requests

CACHE_DIR = Path(tempfile.gettempdir()) / "frostmind_tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _api_key() -> str:
    return os.getenv("SARVAM_API_KEY", "").strip()


def _offline_tts_wav(text: str) -> bytes | None:
    """Windows local speech fallback; returns None on unsupported systems."""
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
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       check=True, timeout=10, capture_output=True)
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
            parts.append(f"अभी {card['meal']} के साथ {', '.join(due)} की याद दिलाई जा रही है।")
        if expired:
            parts.append(f"इन खाद्य वस्तुओं की तारीख निकल गई है: {', '.join(expired)}। पैकेज निर्देश जाँचें।")
        if urgent:
            parts.append(f"आज पहले इस्तेमाल करने की योजना बनाएँ: {', '.join(urgent)}।")
        if len(parts) == 1:
            parts.append("अभी कोई जरूरी रसोई रिमाइंडर नहीं है।")
        return " ".join(parts)
    parts = []
    if missed:
        parts.append(f"Earlier reminder pending: {', '.join(missed)}.")
    if due:
        parts.append(f"Reminder associated with {card['meal'].lower()}: {', '.join(due)}.")
    if expired:
        parts.append(f"Please check the storage guidance for: {', '.join(expired)}.")
    if urgent:
        parts.append(f"Plan to use these items first: {', '.join(urgent)}.")
    return " ".join(parts) or "There are no urgent kitchen reminders right now."


def speak_card(card: dict, lang: str = "hi-IN", speaker: str | None = None) -> tuple[bytes | None, str | None]:
    text = build_spoken_prompt(card, lang=lang)
    digest = hashlib.sha256(f"{lang}:{speaker}:{text}".encode()).hexdigest()[:16]
    cached_file = CACHE_DIR / f"{digest}.wav"
    if cached_file.exists():
        return cached_file.read_bytes(), None

    key = _api_key()
    if key:
        try:
            payload = {
                "text": text[:500],
                "target_language_code": lang,
                "model": "bulbul:v4-flash",
                "pace": 1.0,
            }
            if speaker:
                payload["speaker"] = speaker
            response = requests.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"api-subscription-key": key, "Content-Type": "application/json"},
                json=payload,
                timeout=25,
            )
            response.raise_for_status()
            audios = response.json().get("audios", [])
            if audios:
                audio = base64.b64decode("".join(audios))
                cached_file.write_bytes(audio)
                return audio, None
            raise RuntimeError("Sarvam returned an empty audio response.")
        except Exception as exc:
            fallback = _offline_tts_wav(text if lang == "en-IN" else build_spoken_prompt(card, "en-IN"))
            if fallback:
                return fallback, None
            return None, f"Sarvam speech unavailable: {exc}"

    fallback = _offline_tts_wav(text if lang == "en-IN" else build_spoken_prompt(card, "en-IN"))
    if fallback:
        return fallback, None
    return None, "SARVAM_API_KEY is not configured, or local speech is unavailable."


def transcribe_voice(audio_bytes: bytes) -> tuple[str | None, str | None]:
    if not audio_bytes:
        return None, "No audio was recorded."
    key = _api_key()
    if not key:
        return None, "SARVAM_API_KEY is not configured. Paste receipt text instead."
    try:
        response = requests.post(
            "https://api.sarvam.ai/speech-to-text",
            headers={"api-subscription-key": key},
            files={"file": ("voice_drop.wav", audio_bytes, "audio/wav")},
            data={"model": "saaras:v4", "mode": "translit"},
            timeout=30,
        )
        response.raise_for_status()
        transcript = response.json().get("transcript", "").strip()
        return (transcript, None) if transcript else (None, "Sarvam returned an empty transcript.")
    except Exception as exc:
        return None, f"Sarvam speech recognition unavailable: {exc}"
