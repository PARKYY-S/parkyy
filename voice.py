"""
PARKYY's voice.

1) ElevenLabs  - best quality, needs internet + ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env
2) Piper       - free and offline backup (voices/models/*.onnx), always works
PARKYY's Piper voice gets a little deeper as it grows up (Baby -> Kid -> Teen -> Adult).

.env settings (all optional):
  ELEVENLABS_API_KEY=...        your key (keep it only in .env)
  ELEVENLABS_VOICE_ID=...       the voice you design/choose on elevenlabs.io
  ELEVENLABS_MODEL=eleven_flash_v2_5
  PIPER_VOICE=en_GB-cori-high   which offline voice to use
  PIPER_SPEED=0.95              lower = faster
  PIPER_PITCH=1.0               extra pitch on top of the growing-up pitch
"""
import io
import json
import os
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = HERE / "voices" / "models"

# ElevenLabs key + voice id live in voice.env (kept separate from .env)
try:
    from dotenv import load_dotenv
    load_dotenv(HERE / "voice.env", override=True)
except ImportError:
    pass

STAGE_PITCH = {"baby": 1.32, "kid": 1.20, "teen": 1.08, "adult": 1.00}

_piper_cache = {}


def _elevenlabs(text: str):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    vid = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if not key or not vid:
        return None
    body = json.dumps({
        "text": text,
        "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
    }).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
        data=body, method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except Exception:
        return None  # offline, out of credits, bad key... fall back to Piper


def _piper_model():
    want = os.environ.get("PIPER_VOICE", "en_GB-cori-high")
    path = MODELS / f"{want}.onnx"
    if path.exists():
        return path
    found = sorted(MODELS.glob("*.onnx")) if MODELS.exists() else []
    return found[0] if found else None


def _piper(text: str, stage: str):
    try:
        import numpy as np
        from piper import PiperVoice, SynthesisConfig
    except ImportError:
        return None
    model = _piper_model()
    if model is None:
        return None
    if model not in _piper_cache:
        _piper_cache[model] = PiperVoice.load(str(model))
    voice = _piper_cache[model]
    pitch = STAGE_PITCH.get((stage or "baby").lower(), 1.0) * float(os.environ.get("PIPER_PITCH", "1.0"))
    speed = float(os.environ.get("PIPER_SPEED", "0.95"))

    raw = io.BytesIO()
    with wave.open(raw, "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=speed * pitch))
    raw.seek(0)
    with wave.open(raw, "rb") as wf:
        rate, ch, sw = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
    if abs(pitch - 1.0) > 1e-3:
        n = int(len(audio) / pitch)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(ch); wf.setsampwidth(sw); wf.setframerate(rate)
        wf.writeframes(np.clip(audio, -32768, 32767).astype(np.int16).tobytes())
    return out.getvalue()


def speak(text: str, stage: str = "baby", prefer: str = "auto"):
    """Returns (audio_bytes, mime_type, engine) or (None, None, None)."""
    text = (text or "").strip()[:1500]
    if not text:
        return None, None, None
    if prefer in ("auto", "elevenlabs"):
        mp3 = _elevenlabs(text)
        if mp3:
            return mp3, "audio/mpeg", "elevenlabs"
    wav = _piper(text, stage)
    if wav:
        return wav, "audio/wav", "piper"
    return None, None, None
