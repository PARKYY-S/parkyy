"""
PARKYY backend server.

Runs once, on whichever machine you designate as "always on" (your
laptop while you're testing, later maybe a small cloud VM or a mini PC).
Both your laptop client and phone client talk to THIS server, so memory
and conversation state are always shared — there's only one PARKYY.

Phase 1 (this file): a text endpoint you can test with curl/Postman
before any voice hardware is involved, and a WebSocket endpoint
stubbed for streaming audio once you pick STT/TTS providers.

Run it:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import socket

# Saud's rule: PARKYY never puts anything on C: - temp files and pip's cache go to D: (inside PARKYY's folder)
_tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tmp")
os.makedirs(_tmp, exist_ok=True)
for _k in ("TEMP", "TMP", "TMPDIR"):
    os.environ[_k] = _tmp
os.environ["PIP_CACHE_DIR"] = os.path.join(_tmp, "pip-cache")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ms-playwright"))
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pathlib import Path as _Path
from pydantic import BaseModel
from agent import Parkyy
import voice
from tools import tools as hands
import brains
import stay_awake
from collections import deque
_voice_q = deque(maxlen=20)

load_dotenv()

app = FastAPI(title="PARKYY")
# The desktop layer loads from a local file, so allow local cross-origin calls.
# The server itself only listens on 127.0.0.1 (see start script), so nothing
# outside this laptop can reach it.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
parkyy = Parkyy()

AUTH_TOKEN = os.environ.get("PARKYY_AUTH_TOKEN", "parkyy-local")

# Serve the PARKYY phone app so your phone can open it over Wi-Fi and "Add to Home screen".
_PHONE = _Path(__file__).resolve().parent / "phone" / "www"
if _PHONE.exists():
    app.mount("/app", StaticFiles(directory=str(_PHONE), html=True), name="app")


@app.get("/")
def _root():
    return RedirectResponse(url="/app/")


@app.get("/app-config")
def _app_config(request: Request):
    """The phone app, when opened FROM this laptop, picks up its token here so
    you don't have to type it. Only answered for your own devices (localhost,
    home LAN, or your private Tailscale network) — not the public internet."""
    import ipaddress
    host = request.client.host if request.client else ""
    ok = host in ("127.0.0.1", "::1")
    if not ok:
        try:
            a = ipaddress.ip_address(host)
            ok = a.is_private or a.is_loopback or a in ipaddress.ip_network("100.64.0.0/10")
        except ValueError:
            ok = False
    if not ok:
        raise HTTPException(status_code=403, detail="Not a trusted device")
    return {"token": AUTH_TOKEN}


def _all_ips() -> list[str]:
    ips = set()
    try:
        for res in socket.getaddrinfo(socket.gethostname(), None):
            ip = res[4][0]
            if ":" not in ip:
                ips.add(ip)
    except OSError:
        pass
    return list(ips)


def _tailscale_ip() -> str:
    import ipaddress
    ts = ipaddress.ip_network("100.64.0.0/10")   # Tailscale's address range
    for ip in _all_ips():
        try:
            if ipaddress.ip_address(ip) in ts:
                return ip
        except ValueError:
            pass
    return ""


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))   # doesn't send anything, just picks the route's IP
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


@app.get("/whoami")
def whoami():
    ip = _lan_ip()
    ts = _tailscale_ip()
    return {"lan_ip": ip, "phone_url": f"http://{ip}:8000/app/",
            "tailscale_ip": ts, "anywhere_url": f"http://{ts}:8000/app/" if ts else ""}


@app.on_event("startup")
def _keep_awake():
    stay_awake.start()


class StayAwake(BaseModel):
    on: bool


@app.get("/stay-awake")
def stay_awake_get(authorization: str = Header(None)):
    check_auth(authorization)
    return {"on": stay_awake.status()}


@app.post("/stay-awake")
def stay_awake_set(s: StayAwake, authorization: str = Header(None)):
    check_auth(authorization)
    return {"reply": stay_awake.set_on(s.on), "on": stay_awake.status()}


@app.on_event("startup")
def _announce():
    ip = _lan_ip()
    ts = _tailscale_ip()
    lines = ["Open on your phone, then 'Add to Home screen':",
             "Same Wi-Fi:  http://%s:8000/app/" % ip]
    if ts:
        lines.append("Anywhere (Tailscale):  http://%s:8000/app/" % ts)
    else:
        lines.append("(Install Tailscale for an address that works anywhere.)")
    try:
        (_Path(__file__).resolve().parent / "desktop" / "phone-url.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def check_auth(authorization: str | None):
    if authorization != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(status_code=401, detail="Not authorized")


class ChatRequest(BaseModel):
    message: str


import json as _json
_CHATLOG = _Path(__file__).resolve().parent / "data" / "chatlog.json"


def _log_chat(user: str, reply: str):
    try:
        d = _json.loads(_CHATLOG.read_text(encoding="utf-8")) if _CHATLOG.exists() else []
    except (OSError, ValueError):
        d = []
    d.append({"u": user, "p": reply, "t": int(__import__("time").time())})
    try:
        _CHATLOG.parent.mkdir(exist_ok=True)
        _CHATLOG.write_text(_json.dumps(d[-300:], ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


@app.post("/chat")
def chat(req: ChatRequest, authorization: str = Header(None)):
    """Plain text endpoint. Use this to prove the brain + memory loop
    works before wiring up voice at all."""
    check_auth(authorization)
    reply = parkyy.handle_message(req.message)
    _log_chat(req.message, reply)
    return {"reply": reply, "learned": parkyy.learner.take_new(), "notes": parkyy.upgrader.take_notes(),
            "asks": hands.take_asks(), "brain": parkyy.last_brain, "phone": hands.take_phone()}


@app.post("/transcribe")
async def transcribe(request: Request, authorization: str = Header(None)):
    """16 kHz mono 16-bit audio in (raw bytes) -> the words Saud said."""
    check_auth(authorization)
    import ears
    from starlette.concurrency import run_in_threadpool
    pcm = await request.body()
    return await run_in_threadpool(ears.transcribe, pcm[: 16000 * 2 * 30])   # max 30 s


@app.post("/listen")
async def listen_now(authorization: str = Header(None)):
    """Record from the laptop mic (Python side) until Saud stops talking -> his words."""
    check_auth(authorization)
    import ears
    from starlette.concurrency import run_in_threadpool
    mic_busy_for(14)                      # the Hey-PARKYY ears stay quiet while the mic button is recording
    try:
        return await run_in_threadpool(ears.listen)
    except Exception as e:
        return {"text": "", "engine": "none", "error": f"mic problem: {type(e).__name__}: {e}", "failed": True}
    finally:
        mic_busy_for(0.8)


@app.post("/listen/stop")
def listen_stop(authorization: str = Header(None)):
    check_auth(authorization)
    import ears
    ears.stop_listening()
    return {"ok": True}


@app.get("/chatlog")
def chatlog(authorization: str = Header(None)):
    """Recent conversation, kept on the laptop so the phone can reload it and both stay in sync."""
    check_auth(authorization)
    try:
        d = _json.loads(_CHATLOG.read_text(encoding="utf-8")) if _CHATLOG.exists() else []
    except (OSError, ValueError):
        d = []
    return {"log": d[-120:]}


class AddLog(BaseModel):
    u: str = ""
    p: str = ""


@app.post("/chatlog/add")
def chatlog_add(item: AddLog, authorization: str = Header(None)):
    """Things the phone handled on its own (like "open WhatsApp"), so they're kept in the shared chat too."""
    check_auth(authorization)
    if item.u or item.p:
        _log_chat(item.u[:2000], item.p[:4000])
    return {"ok": True}


class ClearLog(BaseModel):
    ok: bool = True


@app.post("/chatlog/clear")
def chatlog_clear(_: ClearLog, authorization: str = Header(None)):
    check_auth(authorization)
    try:
        _CHATLOG.write_text("[]", encoding="utf-8")
    except OSError:
        pass
    return {"ok": True}


class Confirm(BaseModel):
    id: str
    yes: bool


@app.post("/confirm")
def confirm(c: Confirm, authorization: str = Header(None)):
    """Saud tapped Yes/No on something PARKYY wanted to do."""
    check_auth(authorization)
    return {"reply": hands.confirm(c.id, c.yes)}


@app.get("/events")
def events(authorization: str = Header(None)):
    """Everything the UI should show without being asked: due reminders, things learned, upgrades."""
    check_auth(authorization)
    return {"events": hands.take_events(), "learned": parkyy.learner.take_new(),
            "notes": parkyy.upgrader.take_notes(), "asks": hands.take_asks(), "phone": hands.take_phone()}


@app.get("/hud")
def hud(authorization: str = Header(None)):
    """Live data for the JARVIS-style HUD: system, context, mission, sentinel, security."""
    check_auth(authorization)
    from tools import core
    return core.hud_data()


@app.get("/phone/inbox")
def phone_inbox(take: bool = False, authorization: str = Header(None)):
    """Notes/results PARKYY sent to the phone (the v0.8 phone app reads this)."""
    check_auth(authorization)
    from tools import prime
    return {"items": prime.phone_inbox(take)}


@app.get("/greet")
def greet(authorization: str = Header(None)):
    """Context-aware hello when PARKYY wakes (at most every few hours)."""
    check_auth(authorization)
    from tools import core
    return {"text": core.greet_once()}


@app.get("/today")
def today(authorization: str = Header(None)):
    check_auth(authorization)
    return hands.today_summary()


@app.get("/learned")
def learned(authorization: str = Header(None)):
    """Facts PARKYY picked up on its own since the last check."""
    check_auth(authorization)
    return {"learned": parkyy.learner.take_new(), "notes": parkyy.upgrader.take_notes()}


class Answer(BaseModel):
    yes: bool


@app.get("/world")
def world(authorization: str = Header(None)):
    """Latest brief, topics PARKYY follows, and any topic it wants to ask about."""
    check_auth(authorization)
    return parkyy.world.status()


@app.post("/world/answer")
def world_answer(a: Answer, authorization: str = Header(None)):
    check_auth(authorization)
    return {"reply": parkyy.world.answer(a.yes)}


@app.post("/world/refresh")
def world_refresh(authorization: str = Header(None)):
    import threading
    check_auth(authorization)
    threading.Thread(target=parkyy.world.cycle, daemon=True).start()
    return {"ok": True}


class ProposalAnswer(BaseModel):
    id: str
    yes: bool


@app.get("/proposals")
def proposals(authorization: str = Header(None)):
    """Upgrades PARKYY wants to make to itself - each waits for Saud's yes."""
    check_auth(authorization)
    return {"pending": parkyy.upgrader.pending()}


@app.post("/proposals/answer")
def proposals_answer(a: ProposalAnswer, authorization: str = Header(None)):
    check_auth(authorization)
    return {"reply": parkyy.upgrader.answer(a.id, a.yes)}


@app.get("/skills")
def skills(authorization: str = Header(None)):
    check_auth(authorization)
    return {"skills": parkyy.upgrader.skills()}


class BrainMode(BaseModel):
    mode: str


@app.get("/brain")
def brain(authorization: str = Header(None)):
    """Which brains are available and which mode PARKYY is in."""
    check_auth(authorization)
    return brains.status()


@app.post("/brain/set")
def brain_set(b: BrainMode, authorization: str = Header(None)):
    check_auth(authorization)
    return {"reply": brains.set_mode(b.mode)}


class VoiceEvent(BaseModel):
    kind: str
    text: str = ""


@app.post("/voice/event")
def voice_event(v: VoiceEvent, authorization: str = Header(None)):
    """The ears (voice_input.py) heard the wake word or a command."""
    check_auth(authorization)
    _voice_q.append({"kind": v.kind, "text": v.text})
    return {"ok": True}


# ---- "PARKYY is talking / recording" flag, so the Hey-PARKYY ears ignore PARKYY's own voice
_mic_busy = {"until": 0.0}


def mic_busy_for(secs: float):
    import time as _t
    _mic_busy["until"] = _t.time() + max(0.0, float(secs))


class MicBusy(BaseModel):
    secs: float = 0.8


@app.post("/mic/busy")
def mic_busy_set(b: MicBusy, authorization: str = Header(None)):
    check_auth(authorization)
    mic_busy_for(min(b.secs, 120))
    return {"ok": True}


@app.get("/mic/busy")
def mic_busy_get(authorization: str = Header(None)):
    import time as _t
    check_auth(authorization)
    return {"busy": _t.time() < _mic_busy["until"]}


@app.get("/voice/pull")
def voice_pull(authorization: str = Header(None)):
    """The window polls this fast to react to voice instantly."""
    check_auth(authorization)
    out = list(_voice_q)
    _voice_q.clear()
    return {"events": out}


class AccessSet(BaseModel):
    group: str
    enabled: bool


@app.get("/access")
def access(authorization: str = Header(None)):
    """What PARKYY can touch, and whether each is on."""
    check_auth(authorization)
    return {"access": hands.access_status()}


@app.post("/access/set")
def access_set(a: AccessSet, authorization: str = Header(None)):
    check_auth(authorization)
    return {"reply": hands.set_access(a.group, a.enabled), "access": hands.access_status()}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/memory")
def memory(authorization: str = Header(None)):
    check_auth(authorization)
    parkyy.memory.sync()
    return {"facts": parkyy.memory.facts, "diary": parkyy.learner.diary()[-7:]}


class SpeakRequest(BaseModel):
    text: str
    stage: str = "baby"
    prefer: str = "auto"


@app.post("/speak")
def speak(req: SpeakRequest, authorization: str = Header(None)):
    """PARKYY's voice: ElevenLabs when set up + online, Piper offline otherwise."""
    check_auth(authorization)
    mic_busy_for(30)                      # about to talk - the window sets the exact time when it plays
    audio, mime, engine = voice.speak(req.text, req.stage, req.prefer)
    if audio is None:
        raise HTTPException(status_code=503, detail="No voice engine available")
    return Response(content=audio, media_type=mime, headers={"X-Voice-Engine": engine})


@app.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket):
    """
    Streaming voice endpoint — stub.

    Once you've picked an STT provider (e.g. ElevenLabs Scribe Realtime
    or Deepgram) and a TTS provider (e.g. ElevenLabs or Cartesia):
      1. Accept the incoming audio stream from the client (laptop/phone mic)
      2. Pipe it to your STT provider, get back text
      3. Call parkyy.handle_message(text) to get the reply
      4. Pipe the reply text to your TTS provider
      5. Stream the resulting audio back over this same socket

    Keeping this as a thin pass-through means the STT/TTS provider choice
    never touches agent.py — swap providers here only.
    """
    await websocket.accept()
    await websocket.send_json(
        {"status": "voice pipeline not wired up yet — use /chat for now"}
    )
    await websocket.close()
