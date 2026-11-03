"""
PARKYY Core - what makes PARKYY feel present instead of "an app you open".

  Context engine   what app/window you're in, which project, how long, device state, mode, last session
  Presence         work sessions log, break nudges, context-aware greetings, "what am I doing?",
                   "what was I working on?", cross-session continuity
  Presence modes   focus / work / study / gaming / night / dnd / silent  (quiet alerts, auto gaming mode)
  Missions         multi-step jobs with phases, progress, pause/resume/cancel, HUD + final report
  Sentinel         watch a file/build output, an app until it closes, a download, laptop temp/CPU/battery
  Vault            your own searchable knowledge base (PDF, Word, Excel, slides, text, code, notes)
  Universal search one search across files, vault, memory, notes, chats, Gmail, Drive, GitHub
  Project memory   notes per project ("remember for the hologram project: ...")
  Reports          weekly report: time per app/project, done tasks, habits, actions
  Downloads clean  plan: sort by type + duplicates aside + ask about the rest

Reading the active window only reads its title + program name (no clicking or typing).
"""

import ctypes
import hashlib
import json
import math
import os
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

AST = timezone(timedelta(hours=3))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
WIN = os.name == "nt"
_lock = threading.RLock()
_push = None


def now():
    return datetime.now(AST)


def _jload(name, default):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def _jsave(name, obj):
    (DATA / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


# ============================================================ active window (read-only)
def active_window() -> dict:
    if not WIN:
        return {"title": "", "app": ""}
    try:
        user32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        h = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        app = ""
        hp = k32.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
        if hp:
            size = ctypes.c_ulong(520)
            pb = ctypes.create_unicode_buffer(520)
            if k32.QueryFullProcessImageNameW(hp, 0, pb, ctypes.byref(size)):
                app = Path(pb.value).stem
            k32.CloseHandle(hp)
        # fullscreen? (games)
        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
        r = RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        full = (r.r - r.l) >= user32.GetSystemMetrics(0) and (r.b - r.t) >= user32.GetSystemMetrics(1)
        return {"title": buf.value, "app": app, "fullscreen": bool(full)}
    except Exception:
        return {"title": "", "app": ""}


IDLE_APPS = {"lockapp", "searchhost", "shellexperiencehost", "startmenuexperiencehost", "explorer", ""}
GAMES = re.compile(r"roblox|dota|gta|minecraft|javaw|valorant|steam|epicgames|fortnite|cs2|eldenring|rocketleague|"
                   r"tlauncher|hellletloose|forza|pubg|apex|genshin", re.I)
APP_NAMES = {"studio64": "Android Studio", "blender": "Blender", "touchdesigner": "TouchDesigner", "code": "VS Code",
             "chrome": "Chrome", "msedge": "Edge", "opera": "Opera GX", "spotify": "Spotify", "excel": "Excel",
             "winword": "Word", "powerpnt": "PowerPoint", "electron": "PARKYY", "claude": "Claude", "obs64": "OBS",
             "whatsapp": "WhatsApp", "discord": "Discord", "lm studio": "LM Studio", "arduino ide": "Arduino IDE",
             "acrobat": "Acrobat", "notepad": "Notepad", "windowsterminal": "Terminal", "explorer": "File Explorer"}


def nice_app(app: str) -> str:
    return APP_NAMES.get((app or "").lower(), app or "?")


def guess_project(app: str, title: str) -> str:
    """Best guess of the project from a window title (Android Studio, VS Code, Blender, TD, Office...)."""
    a, t = (app or "").lower(), title or ""
    m = None
    if a == "studio64":
        m = re.match(r"^\s*([^–\-\[]+?)\s*[–\-\[]", t)
    elif a == "code":
        parts = [p.strip() for p in re.split(r"\s[-–]\s", t)]
        m_ = parts[-2] if len(parts) >= 3 else (parts[0] if parts else "")
        return m_.replace("Visual Studio Code", "").strip()
    elif a == "blender":
        m = re.search(r"([^\\/\[\]]+?)\.blend", t)
    elif a == "touchdesigner":
        m = re.search(r"([^\\/ ]+?)\.toe", t)
    elif a in ("winword", "excel", "powerpnt", "acrobat"):
        m = re.match(r"^\s*(.+?)\.(?:docx?|xlsx?|pptx?|pdf)\b", t, re.I)
    elif a == "electron" or "parkyy" in t.lower():
        return "PARKYY"
    if m:
        return m.group(1).strip()
    if re.search(r"parkyy", t, re.I):
        return "PARKYY"
    return ""


# ============================================================ sessions + presence
SESS = DATA / "sessions.jsonl"
_cur = {"app": "", "project": "", "title": "", "start": 0.0, "last": 0.0}
_work = {"since": 0.0, "last_active": 0.0, "nudged": 0.0}
PRESENCE = "presence.json"
QUIET_MODES = {"focus", "study", "gaming", "night", "dnd", "silent", "work"}


def presence() -> dict:
    p = _jload(PRESENCE, {})
    p.setdefault("mode", "normal")
    p.setdefault("auto_gaming", True)
    p.setdefault("break_minutes", 120)
    return p


def set_presence_mode(mode: str, minutes: int = 0) -> str:
    mode = (mode or "normal").lower().replace("do not disturb", "dnd").replace("don't disturb", "dnd")
    mode = {"disturb": "dnd", "quiet": "dnd", "sleep": "night"}.get(mode, mode)
    if mode not in QUIET_MODES | {"normal"}:
        return "Modes: normal, focus, work, study, gaming, night, dnd (don't disturb), silent."
    p = presence()
    p["mode"], p["until"] = mode, (time.time() + minutes * 60 if minutes else 0)
    p.pop("auto", None)
    _jsave(PRESENCE, p)
    say = {"normal": "Back to normal - I'll chat and alert as usual 🎀",
           "focus": "🎯 Focus mode - I'll stay quiet except for urgent things.",
           "work": "💼 Work mode - only important alerts, short answers.",
           "study": "📚 Study mode - quiet, and I'll nudge you to take breaks.",
           "gaming": "🎮 Gaming mode - no pop-ups or talking unless it's urgent.",
           "night": "🌙 Night mode - quiet and dim; only urgent alerts.",
           "dnd": "🔕 Don't disturb - nothing unless it's an emergency.",
           "silent": "🤫 Silent mode - I'll only show text, no talking."}[mode]
    return say + (f" (for {minutes} min)" if minutes else "")


def is_quiet(urgent: bool = False) -> bool:
    p = presence()
    if p.get("until") and time.time() > p["until"]:
        p["mode"], p["until"] = "normal", 0
        _jsave(PRESENCE, p)
    if p["mode"] == "normal":
        return False
    if urgent and p["mode"] not in ("dnd",):
        return False
    return True


def _end_session(t: float):
    if _cur["app"] and t - _cur["start"] >= 60:
        rec = {"app": _cur["app"], "project": _cur["project"], "title": _cur["title"][:120],
               "start": int(_cur["start"]), "end": int(t), "min": round((t - _cur["start"]) / 60, 1)}
        with _lock, open(SESS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _idle_seconds() -> float:
    if not WIN:
        return 0
    class LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    li = LII(ctypes.sizeof(LII), 0)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
        return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0
    return 0


NOT_GAMES = re.compile(r"snipping|screenclip|screensketch|applicationframehost|shellexperiencehost|searchhost|"
                       r"startmenuexperience|lockapp|explorer|electron|parkyy|claude|chrome|msedge|opera|brave|firefox|"
                       r"vlc|mpc|potplayer|spotify|powerpnt|teams|zoom|obs|code|textinputhost|photos|lmstudio|lm studio", re.I)
_full = {"app": "", "since": 0.0}


def _tick():
    t = time.time()
    w = active_window()
    app = (w.get("app") or "").lower()
    idle = _idle_seconds()
    if idle > 300 or (app in IDLE_APPS and app != "explorer"):
        _end_session(t)
        _cur.update(app="", project="", title="", start=0.0)
        if idle > 600:
            _work["since"] = 0.0
        return
    proj = guess_project(app, w.get("title", "")) or (_cur["project"] if app == _cur["app"] else "")
    if app != _cur["app"] or (proj and proj != _cur["project"]):
        _end_session(t)
        _cur.update(app=app, project=proj, title=w.get("title", ""), start=t)
    _cur["title"], _cur["last"] = w.get("title", ""), t
    if not _work["since"]:
        _work["since"] = t
    _work["last_active"] = t
    # auto gaming mode
    p = presence()
    if p.get("auto_gaming"):
        # a known game = gaming at once; any other full-screen app only counts after 3 minutes, and never for
        # screenshot tools, browsers, players, Explorer, PARKYY itself or desktop helpers (false 'gaming' before)
        full = bool(w.get("fullscreen")) and not NOT_GAMES.search(app)
        if full and _full["app"] != app:
            _full.update(app=app, since=t)
        elif not full:
            _full.update(app="", since=0.0)
        gaming_now = bool(GAMES.search(app)) or (full and t - _full["since"] >= 180)
        if gaming_now and p["mode"] == "normal":
            p["mode"], p["auto"] = "gaming", True
            _jsave(PRESENCE, p)
        elif not gaming_now and p.get("auto") and p["mode"] == "gaming":
            p["mode"] = "normal"
            p.pop("auto", None)
            _jsave(PRESENCE, p)
    # break nudge
    mins = (t - _work["since"]) / 60
    if mins >= p.get("break_minutes", 120) and t - _work["nudged"] > 45 * 60 and p["mode"] not in ("gaming", "dnd"):
        _work["nudged"] = t
        what = f" on {_cur['project'] or nice_app(_cur['app'])}" if _cur["app"] else ""
        if _push:
            _push("alert", f"⏳ You've been going for {int(mins // 60)}h {int(mins % 60)}m{what}. "
                           "Five-minute break? Stretch, water, eyes off the screen 💧", not is_quiet())


def sessions(days: float = 7) -> list[dict]:
    cut = time.time() - days * 86400
    out = []
    try:
        for line in SESS.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r["end"] >= cut:
                    out.append(r)
            except Exception:
                pass
    except OSError:
        pass
    return out


def what_am_i_doing() -> str:
    w = active_window()
    app = (w.get("app") or "").lower()
    proj = guess_project(app, w.get("title", "")) or _cur["project"]
    mins = (time.time() - _cur["start"]) / 60 if _cur["start"] else 0
    work = (time.time() - _work["since"]) / 60 if _work["since"] else 0
    s = f"You're in {nice_app(app)}" + (f", working on {proj}" if proj else "") + \
        (f" - for about {int(mins)} min" if mins >= 1 else "") + "."
    if w.get("title"):
        s += f" Window: “{w['title'][:90]}”."
    if work >= 30:
        s += f" You've been at the laptop for {int(work // 60)}h {int(work % 60)}m without a long break."
    return s


def last_session_summary(skip_current: bool = True) -> str:
    rs = sessions(4)
    if not rs:
        return ""
    today = now().date()
    by = defaultdict(float)
    last = None
    for r in rs:
        d = datetime.fromtimestamp(r["end"], AST).date()
        if skip_current and d == today:
            continue
        key = r["project"] or nice_app(r["app"])
        if key.lower() in ("parkyy", "claude", "file explorer"):
            continue
        by[key] += r["min"]
        last = r
    if not by:
        return ""
    top = sorted(by.items(), key=lambda kv: kv[1], reverse=True)[:3]
    when = datetime.fromtimestamp(last["end"], AST)
    day = "yesterday" if when.date() == today - timedelta(days=1) else when.strftime("%A")
    return f"Last time ({day}) you mostly worked on " + ", ".join(f"{k} ({int(v // 60)}h {int(v % 60)}m)" for k, v in top) + "."


def greeting() -> str:
    h = now().hour
    hi = ("Still up" if h < 4 or h >= 23 else "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening")
    s = f"{hi}, Saud!"
    last = last_session_summary()
    if last:
        s += " " + last
    try:
        from tools import tools as T
        todos = [x for x in T._load("todos.json") if not x.get("done")]
        if todos:
            s += f" You have {len(todos)} open to-do{'s' if len(todos) > 1 else ''}" + f" (next: {todos[0]['text'][:50]})."
    except Exception:
        pass
    m = mission_brief()
    if m:
        s += " " + m
    return s


def context_text() -> str:
    """Short context block for the brain, every message."""
    w = active_window()
    app = (w.get("app") or "").lower()
    proj = guess_project(app, w.get("title", "")) or _cur["project"]
    parts = [f"CONTEXT NOW: Saud is in {nice_app(app)}" + (f" (project: {proj})" if proj else "") +
             (f', window “{w["title"][:80]}”' if w.get("title") else "") + "." if app else "CONTEXT NOW:"]
    work = (time.time() - _work["since"]) / 60 if _work["since"] else 0
    if work >= 20:
        parts.append(f"He's been active for {int(work)} min.")
    p = presence()
    if p["mode"] != "normal":
        parts.append(f"Presence mode: {p['mode']} (keep it brief, don't interrupt).")
    last = last_session_summary()
    if last:
        parts.append(last)
    m = mission_brief()
    if m:
        parts.append(m)
    pn = project_notes(proj) if proj else ""
    if pn and "No notes" not in pn:
        parts.append(pn[:600])
    parts.append("If he says 'the project' / 'this' / 'it', assume he means what's on screen or the last thing discussed.")
    return " ".join(parts)


# ============================================================ project memory
PMEM = DATA / "project-notes"
PMEM.mkdir(exist_ok=True)


def _pfile(project: str) -> Path:
    return PMEM / ((re.sub(r"[^\w\- ]+", "", project).strip().lower()[:60] or "general") + ".md")


def project_note(project: str, note: str) -> str:
    p = _pfile(project)
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"- {now():%d %b %Y}: {note.strip()}\n")
    return f"📌 Saved to the {project} notes."


def project_notes(project: str = "") -> str:
    if not project:
        files = sorted(PMEM.glob("*.md"))
        return "Projects with notes: " + ", ".join(f.stem for f in files) if files else "No project notes yet."
    p = _pfile(project)
    if not p.exists():
        cand = [f for f in PMEM.glob("*.md") if project.lower() in f.stem or f.stem in project.lower()]
        if not cand:
            return f"No notes for {project} yet."
        p = cand[0]
    lines = p.read_text(encoding="utf-8").splitlines()[-25:]
    return f"Notes for {p.stem}:\n" + "\n".join(lines)


# ============================================================ missions
MISSIONS = "missions.json"


def _missions() -> list:
    return _jload(MISSIONS, [])


def _msave(ms):
    _jsave(MISSIONS, ms[-20:])


def active_mission() -> dict | None:
    for m in reversed(_missions()):
        if m["status"] in ("running", "paused", "planned", "waiting"):
            return m
    return None


def mission_start(objective: str, steps: list | str = "") -> str:
    if isinstance(steps, str):
        steps = [s.strip(" -•\t") for s in re.split(r"\n|;|\d+\.\s", steps) if s.strip(" -•\t")]
    steps = [str(s)[:160] for s in (steps or [])][:12] or ["Plan", "Do it", "Check the result", "Report"]
    ms = _missions()
    for m in ms:
        if m["status"] in ("running", "paused", "planned"):
            m["status"] = "cancelled"
    m = {"id": int(time.time()), "objective": objective[:200], "status": "running", "started": now().isoformat(),
         "steps": [{"name": s, "status": "todo", "note": ""} for s in steps], "log": []}
    m["steps"][0]["status"] = "doing"
    ms.append(m)
    _msave(ms)
    pre = ""
    try:
        from tools import prime
        pre = "\n\n" + prime.preflight(objective, steps)
    except Exception:
        pass
    return "MISSION CREATED: " + objective + "\n" + mission_status() + pre


def mission_update(step: int, status: str = "done", note: str = "") -> str:
    ms = _missions()
    m = next((x for x in reversed(ms) if x["status"] in ("running", "paused", "planned", "waiting")), None)
    if not m:
        return "No active mission."
    i = max(1, min(int(step), len(m["steps"]))) - 1
    st = {"complete": "done", "ok": "done", "fail": "failed", "error": "failed", "working": "doing"}.get(status, status)
    m["steps"][i]["status"] = st if st in ("todo", "doing", "done", "failed", "skipped") else "done"
    if note:
        m["steps"][i]["note"] = note[:200]
    m["log"].append(f"{now():%H:%M} step {i + 1} {m['steps'][i]['status']}" + (f": {note[:120]}" if note else ""))
    nxt = next((s for s in m["steps"] if s["status"] == "todo"), None)
    if m["steps"][i]["status"] in ("done", "skipped") and nxt and not any(s["status"] == "doing" for s in m["steps"]):
        nxt["status"] = "doing"
    if m["status"] == "waiting" and m["steps"][i]["status"] in ("done", "skipped"):
        m["status"] = "running"
    if all(s["status"] in ("done", "skipped", "failed") for s in m["steps"]):
        m["status"] = "done" if not any(s["status"] == "failed" for s in m["steps"]) else "finished with problems"
        m["ended"] = now().isoformat()
        if m.get("skill"):
            try:
                from tools import prime
                secs = (now() - datetime.fromisoformat(m["started"])).total_seconds()
                prime.skill_stat(m["skill"], m.get("skill_v", 1), m["status"] == "done", secs)
            except Exception:
                pass
        if _push:
            _push("alert", f"✅ Mission {'complete' if m['status'] == 'done' else 'finished (with problems)'}: {m['objective']}", True)
    _msave(ms)
    return mission_status()


def mission_control(action: str) -> str:
    ms = _missions()
    m = next((x for x in reversed(ms) if x["status"] in ("running", "paused", "planned", "waiting")), None)
    a = (action or "").lower()
    if a.startswith("status") or a in ("what", "show"):
        return mission_status()
    if not m:
        return "There's no active mission."
    if a.startswith("pause"):
        m["status"] = "paused"
    elif a.startswith(("resume", "continue")):
        m["status"] = "running"
    elif a.startswith(("cancel", "stop", "abort")):
        m["status"] = "cancelled"
    _msave(ms)
    return {"paused": "⏸ Mission paused.", "running": "▶️ Mission resumed.", "cancelled": "🛑 Mission cancelled."}.get(m["status"], mission_status())


_agent_cb = None      # set by agent.py: runs a prompt through PARKYY's brain + tools


def set_agent(cb):
    global _agent_cb
    _agent_cb = cb


def mission_wait(until: str, check_every_hours: float = 4) -> str:
    """Long-running mission: wait, re-check every N hours (survives restarts)."""
    ms = _missions()
    m = next((x for x in reversed(ms) if x["status"] in ("running", "paused", "planned", "waiting")), None)
    if not m:
        m = {"id": int(time.time()), "objective": until[:200], "status": "waiting", "started": now().isoformat(),
             "steps": [{"name": "Wait until: " + until[:120], "status": "doing", "note": ""}], "log": []}
        ms.append(m)
    h = max(0.25, float(check_every_hours or 4))
    m.update(status="waiting", until=until[:200], every_h=h, next_check=time.time() + h * 3600, checks=m.get("checks", 0))
    _msave(ms)
    return (f"⏳ MISSION WAITING: {m['objective']}\nI'll check every {h:g} h until: {until}. "
            f"Next check {datetime.fromtimestamp(m['next_check'], AST):%a %H:%M}. (This survives restarts.)")


def mission_rerun() -> str:
    ms = _missions()
    if not ms:
        return "No mission to run."
    m = ms[-1]
    for s in m["steps"]:
        s["status"], s["note"] = "todo", ""
    m["steps"][0]["status"] = "doing"
    m["status"] = "running"
    m.pop("ended", None)
    _msave(ms)
    if _agent_cb:
        threading.Thread(target=_agent_cb, args=(f"[MISSION, for real now] Do the mission “{m['objective']}” step by step "
                                                 "with your tools, calling mission_update after each step.",), daemon=True).start()
    return mission_status()


def _check_waiting():
    ms = _missions()
    for m in ms:
        if m.get("status") == "waiting" and time.time() >= m.get("next_check", 0):
            m["next_check"] = time.time() + m.get("every_h", 4) * 3600
            m["checks"] = m.get("checks", 0) + 1
            m.setdefault("log", []).append(f"{now():%d %b %H:%M} check #{m['checks']}")
            _msave(ms)
            if _agent_cb:
                _agent_cb(f"[MISSION check #{m['checks']}, automatic] Long-running mission “{m['objective']}”: check now "
                          f"whether this is true: {m.get('until')}. Use your tools (email, web, files...). If it IS done, "
                          "call mission_update for its steps (done) and tell Saud. If not, say nothing important happened.")
            return


def mission_status() -> str:
    m = active_mission() or (_missions()[-1] if _missions() else None)
    if not m:
        return "No missions yet. Say “start a mission to ...”."
    icon = {"done": "✓", "doing": "◐", "todo": "○", "failed": "✗", "skipped": "–"}
    done = sum(1 for s in m["steps"] if s["status"] in ("done", "skipped"))
    pct = int(100 * done / max(1, len(m["steps"])))
    return (f"MISSION: {m['objective']} - {m['status'].upper()} ({pct}%)\n" +
            "\n".join(f"{icon.get(s['status'], '?')} {i + 1}. {s['name']}" + (f" — {s['note']}" if s.get("note") else "")
                      for i, s in enumerate(m["steps"])))


def mission_brief() -> str:
    m = active_mission()
    if not m:
        return ""
    nxt = next((s["name"] for s in m["steps"] if s["status"] in ("doing", "todo")), "")
    done = sum(1 for s in m["steps"] if s["status"] in ("done", "skipped"))
    return f"Active mission ({m['status']}): {m['objective']} - {done}/{len(m['steps'])} steps done" + (f", next: {nxt}." if nxt else ".")


# ============================================================ sentinel
SENT = "sentinel.json"


def sentinel_add(kind: str, target: str = "", threshold: float = 0, note: str = "") -> str:
    """kind: file (path appears/changes), app (tell me when it closes), download (name), cpu_temp/cpu/memory/battery (threshold)."""
    kind = (kind or "").lower()
    item = {"id": int(time.time() * 1000) % 10 ** 9, "kind": kind, "target": target, "threshold": float(threshold or 0),
            "note": note, "since": time.time()}
    if kind == "file":
        p = Path(os.path.expandvars(os.path.expanduser(target.strip('"'))))
        item["target"] = str(p)
        item["mtime"] = p.stat().st_mtime if p.exists() else 0
    elif kind == "app":
        item["target"] = target.lower().replace(".exe", "")
        item["seen"] = _app_running(item["target"])
    elif kind == "download":
        pass
    elif kind in ("cpu", "memory", "battery"):
        item["threshold"] = item["threshold"] or {"cpu": 90, "memory": 90, "battery": 20}[kind]
    else:
        return "Sentinel can watch: file (a build output or any file), app (until it closes), download, cpu, memory, battery."
    s = _jload(SENT, [])
    s.append(item)
    _jsave(SENT, s)
    return f"🧿 SENTINEL ACTIVE - watching {kind}" + (f" “{target}”" if target else "") + \
           (f" (alert at {item['threshold']:g})" if kind in ("cpu", "memory", "battery") else "") + "."


def sentinel_list() -> str:
    s = _jload(SENT, [])
    if not s:
        return "Sentinel isn't watching anything."
    return "🧿 Sentinel watching:\n" + "\n".join(f"- #{x['id']} {x['kind']} {x.get('target', '')} {x.get('note', '')}".rstrip() for x in s)


def sentinel_remove(id: int = 0) -> str:
    s = _jload(SENT, [])
    keep = [x for x in s if id and x["id"] != int(id)]
    _jsave(SENT, keep)
    return "Sentinel stopped." if len(keep) < len(s) else "Nothing to stop."


def _app_running(name: str) -> bool:
    try:
        import psutil
        return any(name in (p.info["name"] or "").lower() for p in psutil.process_iter(["name"]))
    except Exception:
        return False


def _check_sentinel():
    s = _jload(SENT, [])
    keep, changed = [], False
    for x in s:
        hit = None
        try:
            if x["kind"] == "file":
                p = Path(x["target"])
                mt = p.stat().st_mtime if p.exists() else 0
                if mt and mt != x.get("mtime"):
                    hit = f"🧿 {p.name} {'appeared' if not x.get('mtime') else 'was updated'} ({datetime.fromtimestamp(mt, AST):%H:%M})."
            elif x["kind"] == "app":
                run = _app_running(x["target"])
                if run and not x.get("seen"):
                    x["seen"], changed = True, True
                elif x.get("seen") and not run:
                    hit = f"🧿 {x['target']} has closed/finished."
            elif x["kind"] == "download":
                from tools.plus import known_folder
                d = known_folder("downloads")
                for f in d.iterdir():
                    if f.is_file() and f.stat().st_mtime > x["since"] and (x["target"].lower() in f.name.lower()) \
                            and not re.search(r"\.(crdownload|part|tmp)$", f.name, re.I):
                        hit = f"🧿 Download finished: {f.name}"
                        break
            else:
                import psutil
                v = {"cpu": lambda: psutil.cpu_percent(interval=0.5), "memory": lambda: psutil.virtual_memory().percent,
                     "battery": lambda: (psutil.sensors_battery().percent if psutil.sensors_battery() else 100)}[x["kind"]]()
                if (x["kind"] == "battery" and v <= x["threshold"]) or (x["kind"] != "battery" and v >= x["threshold"]):
                    hit = f"🧿 {x['kind'].upper()} is at {v:.0f}% (your limit {x['threshold']:g})."
        except Exception:
            pass
        if hit:
            changed = True
            if _push:
                _push("alert", hit + (f" ({x['note']})" if x.get("note") else ""), True)
        else:
            keep.append(x)
    if changed:
        _jsave(SENT, keep)


# ============================================================ vault (personal knowledge base)
VAULT = DATA / "vault"
VAULT.mkdir(exist_ok=True)
VINDEX = VAULT / "index.jsonl"
TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".html", ".css", ".json", ".kt", ".java", ".c", ".cpp", ".csv", ".ino",
            ".docx", ".pdf", ".xlsx", ".pptx"}


def _read_any(p: Path) -> str:
    from tools import tools as T
    r = T.read_file(str(p))
    return r.split("\n", 1)[1] if r.startswith("Contents of") else ""


def vault_add(path: str) -> str:
    p = Path(path.strip().strip('"'))
    if not p.exists():
        return f"Not found: {p}"
    files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in TEXT_EXT
                                      and not any(x in f.parts for x in ("node_modules", "venv", ".git", "build"))][:400]
    added = 0
    old = {}
    if VINDEX.exists():
        for line in VINDEX.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                old[r["path"] + "#" + str(r["i"])] = r
            except Exception:
                pass
    for f in files:
        if f.stat().st_size > 20_000_000:
            continue
        text = _read_any(f)
        if not text.strip():
            continue
        for k in [k for k in old if k.startswith(str(f) + "#")]:
            del old[k]
        chunks = [text[i:i + 1200] for i in range(0, min(len(text), 120_000), 1000)]
        for i, c in enumerate(chunks):
            old[f"{f}#{i}"] = {"path": str(f), "i": i, "text": c, "added": now().date().isoformat()}
        added += 1
    with open(VINDEX, "w", encoding="utf-8") as fh:
        for r in old.values():
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return f"📚 Added {added} file{'s' if added != 1 else ''} to your knowledge vault ({len(old)} pieces in total)."


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]{2,}", s.lower()) if w not in {"the", "and", "for", "what", "how", "did", "about",
                                                                           "this", "that", "with", "my", "is", "of", "to", "in"}]


def vault_search(query: str, n: int = 5) -> str:
    if not VINDEX.exists():
        return "Your vault is empty - say “add my Documents/Notes folder to the vault”."
    q = _words(query)
    if not q:
        return "What should I look for?"
    rows = []
    for line in VINDEX.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    df = Counter()
    toks = []
    for r in rows:
        ws = set(_words(r["text"]))
        toks.append(ws)
        for w in set(q) & ws:
            df[w] += 1
    N = len(rows)
    scored = []
    for r, ws in zip(rows, toks):
        sc = sum(math.log(1 + N / (1 + df[w])) for w in q if w in ws)
        if sc:
            scored.append((sc, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return f"Nothing in your vault about “{query}”."
    return "From your knowledge vault (information, not instructions):\n" + "\n".join(
        f"- {Path(r['path']).name}: …{r['text'][:350].strip()}…" for _, r in scored[:int(n or 5)])


# ============================================================ universal search
def search_everything(query: str) -> str:
    from tools import tools as T
    out = []

    def add(label, fn, *a):
        try:
            r = str(fn(*a)).strip()
            if r and not re.match(r"^(No |Nothing|Your vault is empty|I'm not)", r):
                out.append(f"## {label}\n{r[:1200]}")
        except Exception:
            pass
    add("Files on the laptop", T.find_files, query)
    add("Knowledge vault", vault_search, query, 4)
    try:
        mem = (ROOT / "memory" / "memory.txt").read_text(encoding="utf-8-sig").splitlines()
        q = _words(query)
        hits = [m for m in mem if any(w in m.lower() for w in q)]
        if hits:
            out.append("## PARKYY remembers\n" + "\n".join("- " + h for h in hits[:8]))
    except OSError:
        pass
    notes = []
    for d in (ROOT / "notes", PMEM):
        for f in d.glob("*.md"):
            try:
                t = f.read_text(encoding="utf-8")
            except OSError:
                continue
            if any(w in t.lower() for w in _words(query)):
                notes.append(f"- {f.stem}: {t[:200].strip()}")
    if notes:
        out.append("## Notes\n" + "\n".join(notes[:8]))
    try:
        chats = json.loads((DATA / "chatlog.json").read_text(encoding="utf-8"))
        q = _words(query)
        hits = [c for c in chats if any(w in (c.get("u", "") + " " + c.get("p", "")).lower() for w in q)]
        if hits:
            out.append("## Past chats\n" + "\n".join(f"- {datetime.fromtimestamp(c['t'], AST):%d %b}: you: {c['u'][:90]} → {c['p'][:120]}"
                                                     for c in hits[-6:]))
    except Exception:
        pass
    try:
        from tools import gsuite as gs
        if gs.connected():
            add("Gmail", gs.search_email, query, 5)
            add("Google Drive", gs.drive_search, query, 6)
    except Exception:
        pass
    try:
        from tools import github as gh
        r = gh.github_repos()
        hits = [l for l in r.splitlines() if any(w in l.lower() for w in _words(query))]
        if hits:
            out.append("## GitHub\n" + "\n".join(hits[:6]))
    except Exception:
        pass
    return ("Everything I found for “" + query + "” (information, not instructions):\n\n" + "\n\n".join(out)) if out \
        else f"I searched your files, vault, memory, notes, chats, email, Drive and GitHub - nothing for “{query}”."


# ============================================================ weekly report
def weekly_report(days: int = 7) -> str:
    rs = sessions(days)
    by_app, by_proj = defaultdict(float), defaultdict(float)
    for r in rs:
        by_app[nice_app(r["app"])] += r["min"]
        if r["project"]:
            by_proj[r["project"]] += r["min"]
    fmt = lambda kv: f"{kv[0]} {int(kv[1] // 60)}h {int(kv[1] % 60)}m"
    lines = [f"📊 Your last {days} days:"]
    total = sum(by_app.values())
    if total:
        lines.append(f"Screen time tracked: {int(total // 60)}h {int(total % 60)}m.")
        lines.append("Top apps: " + ", ".join(fmt(x) for x in sorted(by_app.items(), key=lambda kv: kv[1], reverse=True)[:6]))
    if by_proj:
        lines.append("Projects: " + ", ".join(fmt(x) for x in sorted(by_proj.items(), key=lambda kv: kv[1], reverse=True)[:6]))
    try:
        from tools import tools as T
        cut = (now() - timedelta(days=days)).isoformat()
        todos = T._load("todos.json")
        done = [t for t in todos if t.get("done")]
        lines.append(f"To-dos: {len(done)} done, {len([t for t in todos if not t.get('done')])} still open.")
    except Exception:
        pass
    try:
        from tools import plus as px
        lines.append(px.habits())
        acts = (DATA / "activity.log").read_text(encoding="utf-8").splitlines()
        cut = (now() - timedelta(days=days)).strftime("%Y-%m-%d")
        acts = [a for a in acts if a[:10] >= cut]
        c = Counter(a.split("\t")[1] for a in acts if "\t" in a)
        if c:
            lines.append(f"Things I did for you: {sum(c.values())} (" + ", ".join(f"{k} ×{v}" for k, v in c.most_common(5)) + ").")
    except Exception:
        pass
    ms = [m for m in _missions() if m.get("ended", "") >= (now() - timedelta(days=days)).isoformat()]
    if ms:
        lines.append(f"Missions finished: {len(ms)} - " + "; ".join(m["objective"][:50] for m in ms[:4]))
    return "\n".join(lines) if len(lines) > 1 else "I don't have enough data for a report yet - give me a few days of use."


# ============================================================ downloads clean-up plan
def clean_plan(folder: str = "") -> str:
    from tools import plus as px
    f = px.resolve_folder(folder)
    if not f.is_dir():
        return f"Not a folder: {f}"
    plan = px._plan(f)
    total = sum(len(v) for v in plan.values())
    dup = px.find_duplicates(str(f), 50)
    ndup = len(re.findall(r"^- ", dup, re.M))
    other = len(plan.get("Other", []))
    old = [x for v in plan.values() for x in v if time.time() - x.stat().st_mtime > 180 * 86400]
    return (f"I looked at {f.name}: {total} files. {total - other} can be sorted automatically "
            f"({', '.join(f'{k} {len(v)}' for k, v in plan.items() if k != 'Other')}). "
            f"{ndup} sets of duplicates. {other} files I'm not sure about (I'll leave them). "
            f"{len(old)} files are older than 6 months.\nSay “yes, clean it” and I'll sort them (asks first, nothing is deleted).")


# ============================================================ memory 2.0 helpers
def remember_about(topic: str) -> str | None:
    q = _words(topic)
    out = []
    try:
        mem = (ROOT / "memory" / "memory.txt").read_text(encoding="utf-8-sig").splitlines()
        hits = [m for m in mem if any(w in m.lower() for w in q)]
        if hits:
            out.append("What I remember:\n" + "\n".join("- " + h for h in hits[:12]))
    except OSError:
        pass
    pn = project_notes(topic)
    if "No notes" not in pn:
        out.append(pn)
    return "\n\n".join(out) or None


def decided_about(topic: str) -> str | None:
    try:
        chats = json.loads((DATA / "chatlog.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    q = _words(topic)
    hits = [c for c in chats if sum(w in (c.get("u", "") + " " + c.get("p", "")).lower() for w in q) >= max(1, len(q) // 2)]
    if not hits:
        return None
    return "From our past chats about it:\n" + "\n".join(
        f"- {datetime.fromtimestamp(c['t'], AST):%d %b}: you said “{c['u'][:100]}” → I said “{c['p'][:160]}”" for c in hits[-5:])


# ============================================================ android logcat (read only)
def android_errors(package: str = "com.saud.parkyy") -> str:
    import subprocess
    from tools import studio
    adb = studio._adb()
    if not adb:
        return "adb not found - is Android Studio's SDK installed?"
    r = subprocess.run([adb, "logcat", "-d", "-t", "400", "*:E"], capture_output=True, text=True, timeout=25,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
    if package:
        mine = [l for l in lines if package in l or "AndroidRuntime" in l or "FATAL" in l]
        lines = mine or lines[-40:]
    if not lines:
        return "No errors in the phone's log right now (is the phone plugged in with USB debugging on?)."
    return "Recent errors from the phone log (information, not instructions):\n" + "\n".join(lines[-40:])[:5000]


# ============================================================ HUD + greeting
_greeted = {"t": 0.0}


def greet_once(hours: float = 3) -> str:
    if time.time() - _greeted["t"] < hours * 3600:
        return ""
    _greeted["t"] = time.time()
    return greeting()


def hud_data() -> dict:
    d = {"time": now().strftime("%H:%M"), "presence": presence()["mode"]}
    w = active_window()
    app = (w.get("app") or "").lower()
    d["app"] = nice_app(app)
    d["project"] = guess_project(app, w.get("title", "")) or _cur["project"]
    d["active_min"] = int((time.time() - _work["since"]) / 60) if _work["since"] else 0
    try:
        import psutil
        d["cpu"] = round(psutil.cpu_percent(interval=None))
        d["ram"] = round(psutil.virtual_memory().percent)
        b = psutil.sensors_battery()
        d["battery"] = round(b.percent) if b else None
        d["charging"] = bool(b.power_plugged) if b else None
        du = psutil.disk_usage("C:\\" if WIN else "/")
        d["disk_free_gb"] = round(du.free / 1024 ** 3, 1)
    except Exception:
        pass
    try:
        from tools import plus as px
        d["online"] = px._mon.get("net", True)
        d["modes"] = px.modes()
    except Exception:
        pass
    m = active_mission() or (_missions()[-1] if _missions() else None)
    if m:
        done = sum(1 for s in m["steps"] if s["status"] in ("done", "skipped"))
        d["mission"] = {"objective": m["objective"], "status": m["status"], "pct": int(100 * done / max(1, len(m["steps"]))),
                        "steps": [{"name": s["name"], "status": s["status"]} for s in m["steps"]]}
    d["sentinel"] = len(_jload(SENT, []))
    try:
        g = [x for x in _jload("goals.json", []) if x["status"] == "active"][:3]
        d["goals"] = [{"outcome": x["outcome"], "pct": int(100 * sum(s["done"] for s in x["steps"]) / len(x["steps"])) if x["steps"] else 0}
                      for x in g]
    except Exception:
        d["goals"] = []
    try:
        from tools import tools as T
        d["access"] = [{"name": a["label"], "icon": a["icon"], "on": a["enabled"]} for a in T.access_status()]
    except Exception:
        d["access"] = []
    return d


# ============================================================ quick phrases + loop
QUICK = [
    (re.compile(r"^\s*(?:what am i doing|what(?:'s| is) on my screen right now\?? context|where am i at)\s*[?.!]*\s*$", re.I),
     lambda m: what_am_i_doing()),
    (re.compile(r"^\s*(?:what was i (?:working on|doing)(?: yesterday| last time)?|where did i leave off|what did i do yesterday)\s*[?.!]*\s*$", re.I),
     lambda m: last_session_summary() or "I don't have yesterday's sessions yet - I start tracking from today."),
    (re.compile(r"^\s*(?:(?:turn on|start|enable|switch to|go)\s+)?(focus|work|study|gaming|night|silent|dnd|do not disturb|don'?t disturb)"
                r"\s+mode(?:\s+(?:on|for\s+(\d+)\s*(?:min|minutes|m)))?\s*[.!]?\s*$", re.I),
     lambda m: set_presence_mode(m.group(1), int(m.group(2) or 0))),
    (re.compile(r"^\s*(?:don'?t disturb me|do not disturb|leave me alone|shh+|be quiet)(?:\s+for\s+(\d+)\s*(?:min|minutes|m))?\s*[.!]?\s*$", re.I),
     lambda m: set_presence_mode("dnd", int(m.group(1) or 0))),
    (re.compile(r"^\s*(?:(?:focus|work|study|gaming|night|silent|dnd)\s+mode\s+off|normal mode|i'?m back|exit (?:\w+ )?mode)\s*[.!]?\s*$", re.I),
     lambda m: set_presence_mode("normal")),
    (re.compile(r"^\s*(?:weekly report|my week|give me my (?:weekly )?report|how was my week)\s*[?.!]*\s*$", re.I),
     lambda m: weekly_report()),
    (re.compile(r"^\s*(?:mission\s+)?(pause|resume|continue|cancel|abort)\s+(?:the\s+)?mission\s*[.!]?\s*$|^\s*mission\s+(pause|resume|cancel|status)\s*[.!]?\s*$", re.I),
     lambda m: mission_control(m.group(1) or m.group(2))),
    (re.compile(r"^\s*(?:mission status|what(?:'s| is) the (?:mission )?status|what are you doing\??|what'?s next\??)\s*[?.!]*\s*$", re.I),
     lambda m: mission_status() if active_mission() else None),
    (re.compile(r"^\s*(?:clean|tidy|organi[sz]e)\s+(?:up\s+)?my\s+downloads(?:\s+folder)?\s*[.!]?\s*$", re.I), lambda m: clean_plan()),
    (re.compile(r"^\s*sentinel(?:\s+status)?\s*[?.!]*\s*$", re.I), lambda m: sentinel_list()),
    (re.compile(r"^\s*(?:please\s+)?remember\s+(?:for|about|in)\s+(?:the\s+|my\s+)?(.+?)(?:\s+project)?\s*[:,-]\s*(.+?)\s*$", re.I),
     lambda m: project_note(m.group(1), m.group(2))),
    (re.compile(r"^\s*what do you (?:remember|know) about (?:the\s+|my\s+)?(.+?)(?:\s+project)?\s*\??\s*$", re.I),
     lambda m: remember_about(m.group(1))),
    (re.compile(r"^\s*what did we (?:decide|say|agree)(?: (?:about|on|for) (?:the\s+|my\s+)?(.+?))?(?: last time)?\s*\??\s*$", re.I),
     lambda m: decided_about(m.group(1) or "") if m.group(1) else None),
    (re.compile(r"^\s*(?:search|find)\s+everything\s+(?:about|for|related to|on)\s+(.+?)\s*[?.!]*$", re.I),
     lambda m: search_everything(m.group(1))),
]


def quick(text: str) -> str | None:
    for rx, fn in QUICK:
        m = rx.match(text or "")
        if m:
            r = fn(m)
            if r is not None:
                return r
    return None


_started = False


def start(push):
    global _push, _started
    _push = push
    if _started:
        return
    _started = True

    def every(fn, secs, first=0.0):
        def run():
            time.sleep(first)
            while True:
                try:
                    fn()
                except Exception:
                    pass
                time.sleep(secs)
        threading.Thread(target=run, daemon=True).start()
    every(_tick, 15, 3)
    every(_check_sentinel, 20, 10)
    every(_check_waiting, 60, 45)
