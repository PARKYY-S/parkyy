"""
PARKYY's ears (step 8): voice input + "Hey PARKYY" wake word + voice unlock.

This runs on the laptop and listens through the microphone using Vosk -
a FREE, OFFLINE speech recogniser (no internet, no accounts, nothing paid).

How it works:
  - It's always quietly listening for the wake word ("parkyy" / "hey parkyy").
  - When it hears it, it tells PARKYY's window to wake up / unlock, then
    listens for what you say next and sends it to PARKYY as if you typed it.
    PARKYY thinks and speaks back in its own voice (through the window).
  - So this file is just the EARS; PARKYY's window is the brain + mouth.
    That means only one thing ever talks, and it works while the screen is
    locked (wake word unlocks it - that's the "voice unlock").

First run downloads a small (~40 MB) English model once, then it's fully
offline forever.

Settings (.env, all optional):
  PARKYY_WAKE_WORDS=parkyy,hey parkyy,okay parkyy,ok parkyy
  PARKYY_UNLOCK_PHRASE=            # if set, ONLY this phrase unlocks (extra security)
  PARKYY_VOICE_INPUT=0             # set to 0 to turn the mic off completely
  PARKYY_VOSK_MODEL=               # path to a bigger Vosk model if you want better accuracy
  PARKYY_MIC_INDEX=                # sound device number, if the wrong mic is picked
"""

import json
import re
import os
import queue
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:                                   # same settings + password (PARKYY_AUTH_TOKEN) as the backend
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except Exception:
    pass
LOG = HERE / "desktop" / "voice-input.log"
API = os.environ.get("PARKYY_API", "http://127.0.0.1:8000")
TOKEN = os.environ.get("PARKYY_AUTH_TOKEN", "parkyy-local")
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_DIR = HERE / "voice-model"
SAMPLE_RATE = 16000

import voiceconf
COMMAND_WINDOW = 6  # seconds to wait for a command right after just the wake word


def log(*a):
    msg = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(msg, flush=True)
    try:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def post(path, data):
    try:
        req = urllib.request.Request(API + path, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:
        log("post failed", path, e)
        return False


_busy_cache = {"t": 0.0, "v": False}


def parkyy_busy() -> bool:
    """True while PARKYY is talking (or the mic button is recording) - then we ignore what we hear."""
    now = time.time()
    if now - _busy_cache["t"] < 0.25:
        return _busy_cache["v"]
    v = False
    try:
        req = urllib.request.Request(API + "/mic/busy", headers={"Authorization": "Bearer " + TOKEN})
        v = bool(json.loads(urllib.request.urlopen(req, timeout=2).read()).get("busy"))
    except Exception:
        v = False
    _busy_cache.update(t=now, v=v)
    return v


def pick_mic(sd):
    """Same mic choice as the mic button: skip silent/muted mics (e.g. a dead laptop mic -> earphones)."""
    mic = os.environ.get("PARKYY_MIC_INDEX")
    if mic and mic.isdigit():
        return int(mic), "mic " + mic
    try:
        import ears
        return ears._pick_mic(sd)
    except Exception as e:
        log("mic check failed:", e)
        return None, "default mic"


_JUNK = {"i am sorry.", "i'm sorry.", "thank you.", "thanks for watching!", "you", "bye.", ".", "okay.", "yeah.", "oh.", "uh", "um"}


def better_text(pcm: bytes, rough: str) -> str:
    """The offline model is great at spotting 'Hey PARKYY' but sloppy at sentences, so re-hear the
    same audio with Groq Whisper (much more accurate). Falls back to the offline words."""
    try:
        import ears
        r = ears.transcribe(pcm, log=False)
        t = (r.get("text") or "").strip()
        if t and t.lower() not in _JUNK and r.get("engine") == "groq-whisper":
            return t
    except Exception as e:
        log("whisper re-hear failed:", e)
    return rough


def ensure_model() -> Path | None:
    custom = os.environ.get("PARKYY_VOSK_MODEL", "").strip()
    if custom and Path(custom).exists():
        return Path(custom)
    if MODEL_DIR.exists() and any(MODEL_DIR.glob("**/am/final.mdl")):
        # find the folder that actually contains the model
        for p in [MODEL_DIR] + [d for d in MODEL_DIR.iterdir() if d.is_dir()]:
            if (p / "am" / "final.mdl").exists():
                return p
    log("downloading the free voice model (~40 MB, one time)...")
    try:
        MODEL_DIR.mkdir(exist_ok=True)
        zpath = MODEL_DIR / "model.zip"
        urllib.request.urlretrieve(MODEL_URL, zpath)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(MODEL_DIR)
        zpath.unlink(missing_ok=True)
        for d in MODEL_DIR.iterdir():
            if d.is_dir() and (d / "am" / "final.mdl").exists():
                log("voice model ready")
                return d
    except Exception as e:
        log("couldn't download the voice model:", e)
    return None


def main():
    if os.environ.get("PARKYY_VOICE_INPUT", "1") == "0":
        log("voice input is turned off (PARKYY_VOICE_INPUT=0)")
        return
    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model, SetLogLevel
    except ImportError:
        log("Voice input needs 'vosk' and 'sounddevice'. Run SETUP-PARKYY.bat once to install them.")
        return
    SetLogLevel(-1)
    model_path = ensure_model()
    if not model_path:
        log("no voice model - voice input off for now")
        return
    model = Model(str(model_path))
    q = queue.Queue()

    def cb(indata, frames, t, status):
        q.put(bytes(indata))

    conf = voiceconf.load()
    log("PARKYY is listening. Wake names:", ", ".join(conf["wake_words"]))
    conf_mtime = voiceconf.CONF.stat().st_mtime if voiceconf.CONF.exists() else 0
    awake_until = 0      # conversation mode: talk freely until this time
    awaiting_until = 0   # said just the name, waiting for the command
    while True:                                   # if the mic disappears (earphones unplugged), find another
        dev, name = pick_mic(sd)
        kw = {"device": dev} if dev is not None else {}
        log("listening on:", name)
        rec = KaldiRecognizer(model, SAMPLE_RATE)
        utter = bytearray()                       # audio of the sentence being heard right now
        try:
            with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000, dtype="int16", channels=1, callback=cb, **kw):
                while True:
                    data = q.get()
                    if parkyy_busy():             # PARKYY is talking: ignore it - except "Hey PARKYY" / "stop" (barge-in)
                        utter.clear()
                        if rec.AcceptWaveform(data):
                            bt = json.loads(rec.Result()).get("text", "").strip()
                            bw, _ = voiceconf.wake_match(bt, conf["wake_words"]) if bt else (False, "")
                            if bw or re.fullmatch(r"(?:okay |ok )?(?:stop|wait|stop stop|shut up|enough)", bt):
                                log("interrupted by:", bt)
                                post("/voice/event", {"kind": "interrupt"})
                                awaiting_until = time.time() + COMMAND_WINDOW
                                _busy_cache.update(t=0.0, v=False)
                        continue
                    utter.extend(data)
                    if len(utter) > SAMPLE_RATE * 2 * 20:   # keep at most ~20 s
                        del utter[:len(utter) - SAMPLE_RATE * 2 * 20]
                    if not rec.AcceptWaveform(data):
                        continue
                    pcm = bytes(utter)
                    utter.clear()
                    text = json.loads(rec.Result()).get("text", "").strip()
                    if not text:
                        continue
                    if parkyy_busy():
                        continue
                    # pick up nickname/setting changes without a restart
                    try:
                        mt = voiceconf.CONF.stat().st_mtime if voiceconf.CONF.exists() else 0
                        if mt != conf_mtime:
                            conf = voiceconf.load(); conf_mtime = mt
                            log("wake names updated:", ", ".join(conf["wake_words"]))
                    except OSError:
                        pass
                    log("heard:", text)
                    now_t = time.time()
                    woke, after = voiceconf.wake_match(text, conf["wake_words"])
                    if woke:
                        if voiceconf.can_unlock(text):
                            post("/voice/event", {"kind": "wake"})
                        if after:
                            good = better_text(pcm, text)
                            if good != text:
                                w2, a2 = voiceconf.wake_match(good, conf["wake_words"])
                                after = a2 if (w2 and a2) else re.sub(
                                    r"^\W*(?:(?:hey|hi|ok|okay|yo)\W+)?\w+\W+", "", good, count=1).strip() or after
                                log("whisper heard:", good)
                            post("/voice/event", {"kind": "said", "text": after})
                            awake_until = now_t + conf["conversation_seconds"]
                            awaiting_until = 0
                        else:
                            awaiting_until = now_t + COMMAND_WINDOW
                    elif now_t < awaiting_until or now_t < awake_until:
                        # conversation mode / just-woke: no wake word needed
                        if len(text.split()) < 2 and text in ("the", "a", "uh", "um", "huh", "but", "that", "because", "right"):
                            continue                  # stray noise words
                        text = better_text(pcm, text)
                        if text.lower().strip() in _JUNK or (len(re.findall(r"\w+", text)) < 2 and text.lower().strip(" .!?") not in
                                ("pause", "stop", "skip", "next", "resume", "previous", "yes", "no", "louder", "quieter")):
                            continue              # "yeah", "oh", background noise
                        log("whisper heard:", text)
                        post("/voice/event", {"kind": "said", "text": text})
                        awake_until = now_t + conf["conversation_seconds"]
                        awaiting_until = 0
        except Exception as e:
            log("microphone error:", e, "- trying again in 10 s")
            time.sleep(10)
            while not q.empty():
                q.get_nowait()


if __name__ == "__main__":
    main()
