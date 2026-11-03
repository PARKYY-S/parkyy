"""
PARKYY's ears for "tap the mic / show your palm, then talk".

transcribe(pcm16) takes 16 kHz mono 16-bit audio and returns the words:
  1. Groq Whisper (free key GROQ_API_KEY) - very accurate, understands accents well
  2. otherwise the free offline Vosk model PARKYY already uses for "Hey PARKYY"
"""

import io
import json
import os
import array
import math
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
RATE = 16000
_vosk = None


def _wav(pcm: bytes) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return b.getvalue()


def _groq(pcm: bytes) -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no groq key")
    boundary = uuid.uuid4().hex
    parts = []
    lang = os.environ.get("PARKYY_LANGUAGE", "en").strip().lower()      # "auto" = detect Hindi/Urdu/Arabic/English...
    fields = [("model", os.environ.get("PARKYY_WHISPER_MODEL", "whisper-large-v3-turbo")), ("response_format", "json")]
    if lang and lang != "auto":
        fields.append(("language", lang))
    for name, val in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{val}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="talk.wav"\r\n'
                 f'Content-Type: audio/wav\r\n\r\n'.encode() + _wav(pcm) + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=b"".join(parts),
                                 headers={"Authorization": "Bearer " + key, "User-Agent": "PARKYY/1.0 (+desktop)",
                                          "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return (json.loads(r.read()).get("text") or "").strip()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Groq {e.code}: {e.read().decode('utf-8', 'replace')[:160]}")


def _vosk_model():
    global _vosk
    if _vosk is None:
        from vosk import Model
        custom = os.environ.get("PARKYY_VOSK_MODEL", "").strip()
        base = Path(custom) if custom else HERE / "voice-model"
        cands = [base] + ([d for d in base.iterdir() if d.is_dir()] if base.exists() else [])
        path = next((p for p in cands if (p / "am" / "final.mdl").exists()), None)
        if not path:
            raise RuntimeError("no offline voice model yet (run VOICE.bat once)")
        _vosk = Model(str(path))
    return _vosk


def _offline(pcm: bytes) -> str:
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(_vosk_model(), RATE)
    rec.AcceptWaveform(pcm)
    return (json.loads(rec.FinalResult()).get("text") or "").strip()


def _log(res: dict, pcm: bytes):
    """Keep the last recording + a short log, so problems can be checked (data/last-talk.wav, data/ears.log)."""
    try:
        d = HERE / "data"
        d.mkdir(exist_ok=True)
        (d / "last-talk.wav").write_bytes(_wav(pcm))
        a = array.array("h", pcm[: len(pcm) // 2 * 2])
        rms = int(math.sqrt(sum(x * x for x in a[::8]) / max(1, len(a[::8])))) if a else 0
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} secs={len(pcm) / (RATE * 2):.1f} loudness={rms} "
                f"mic={res.get('mic', 'window')!r} engine={res.get('engine')} text={res.get('text', '')[:80]!r} error={res.get('error', '')[:200]!r}\n")
        with open(d / "ears.log", "a", encoding="utf-8") as f:
            f.write(line)
        res["loudness"] = rms
    except Exception:
        pass
    return res



# ============================================================ finding a mic that actually works
MIC_FILE = HERE / "data" / "mic.json"


def _peak(sd, dev, secs=0.35) -> float:
    """Loudest sample a mic gives in a short moment (-1 = can't open it)."""
    try:
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", device=dev) as st:
            data, _ = st.read(int(RATE * secs))
        a = array.array("h", bytes(data))
        return float(max((abs(x) for x in a[800:]), default=0))     # skip the click at the start
    except Exception:
        return -1.0


def _inputs(sd):
    """Every microphone Windows knows about (one entry per mic name)."""
    seen, out = set(), []
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) < 1:
            continue
        key = d["name"][:28].lower()
        if key in seen or "stereo mix" in key or "loopback" in key:
            continue
        seen.add(key)
        out.append((i, d["name"]))
    return out


def _pick_mic(sd):
    """Use the saved/env/default mic - but if it's dead silent (muted or blocked), try every other
    mic on the laptop (webcam, headset, USB...) and switch to one that really hears sound."""
    env = os.environ.get("PARKYY_MIC_INDEX", "").strip()
    saved = None
    try:
        saved = json.loads(MIC_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    cands = []
    if env.isdigit():
        cands.append(int(env))
    if saved and isinstance(saved.get("index"), int):
        cands.append(saved["index"])
    try:
        cands.append(sd.default.device[0] if sd.default.device[0] is not None and sd.default.device[0] >= 0 else None)
    except Exception:
        cands.append(None)

    def nm(d):
        try:
            return sd.query_devices(d if d is not None else sd.default.device[0])["name"]
        except Exception:
            return "default mic"
    first = cands[0]
    if _peak(sd, first) >= 60:
        return first, nm(first)
    tried = {}
    for i, n in _inputs(sd):
        p = _peak(sd, i)
        tried[n] = int(p)
        if p >= 60:
            MIC_FILE.parent.mkdir(exist_ok=True)
            MIC_FILE.write_text(json.dumps({"index": i, "name": n}), encoding="utf-8")
            _note(f"default mic silent -> switched to {n!r} (index {i}); levels {tried}")
            return i, n
    _note(f"every mic is silent: {tried}")
    return first, nm(first)


def _note(msg: str):
    try:
        (HERE / "data").mkdir(exist_ok=True)
        with open(HERE / "data" / "ears.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def mics() -> list:
    import sounddevice as sd
    return [{"index": i, "name": n, "level": int(_peak(sd, i))} for i, n in _inputs(sd)]

# ============================================================ recording from the laptop mic (Python side)
_stop = False


def stop_listening():
    global _stop
    _stop = True


def listen(max_secs: float = 12.0) -> dict:
    """Record from the laptop microphone until you stop talking, then turn it into words.
    Uses Windows directly (sounddevice), so it doesn't depend on the PARKYY window's mic access."""
    global _stop
    try:
        import sounddevice as sd
    except ImportError:                                      # first time: install it by itself
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "pip", "install", "sounddevice", "-q", "--disable-pip-version-check"],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=180)
        import sounddevice as sd
    _stop = False
    dev, name = _pick_mic(sd)
    block = int(RATE * 0.1)                                  # 100 ms
    frames, levels = [], []
    started, silent, voice, quiet = False, 0.0, 0.0, []
    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=block, device=dev) as st:
        n = 0
        while True:
            data, _ = st.read(block)
            n += 1
            if n <= 2:                                       # skip the "click" when the mic opens
                continue
            b = bytes(data)
            frames.append(b)
            a = array.array("h", b)
            rms = math.sqrt(sum(x * x for x in a) / max(1, len(a)))
            levels.append(rms)
            el = len(frames) * 0.1                           # seconds of audio so far
            if el <= 0.3:
                quiet.append(rms)
                continue
            noise = sorted(quiet)[len(quiet) // 2] if quiet else 5.0
            # works for loud AND very quiet mics (earphones): compare to the room's own noise
            thr = max(6.0, noise * 2.5, voice * 0.25)
            if rms > thr:
                started, silent, voice = True, 0.0, max(voice * 0.995, rms)
            else:
                if not started:
                    quiet.append(rms)
                    quiet = quiet[-20:]
                elif started:
                    silent += 0.1
            if _stop or (started and silent > 1.5) or el > max_secs or (not started and el > 8):
                break
    pcm = b"".join(frames)
    peak = max(levels) if levels else 0
    raw_peak = max((abs(x) for x in array.array("h", pcm)), default=0)
    # quiet mic? turn it up (up to 40x) so Whisper hears clear words
    gain = min(40.0, 20000.0 / max(1.0, raw_peak))
    if gain > 1.2:
        a = array.array("h", pcm)
        pcm = array.array("h", (max(-32767, min(32767, int(x * gain))) for x in a)).tobytes()
    if not started or raw_peak < 40:
        return _log({"text": "", "engine": "none", "mic": name, "heard": False,
                     "error": f"silent mic ({name}, level {int(peak)})"}, pcm)
    res = transcribe(pcm, log=False)
    res.update(mic=name, heard=True)
    return _log(res, pcm)


def transcribe(pcm: bytes, log: bool = True) -> dict:
    _L = _log if log else (lambda r, p: r)
    if len(pcm) < RATE * 2 * 0.3:                 # under 0.3 s
        return _L({"text": "", "engine": "none", "error": "too short"}, pcm)
    errors = []
    try:
        t = _groq(pcm)
        if t:
            return _L({"text": t, "engine": "groq-whisper"}, pcm)
        errors.append("Groq heard nothing")
    except Exception as e:
        errors.append(str(e))
    try:
        t = _offline(pcm)
        return _L({"text": t, "engine": "vosk", "error": " / ".join(errors)}, pcm)
    except Exception as e:
        errors.append(str(e))
        return _L({"text": "", "engine": "none", "error": " / ".join(errors)}, pcm)
