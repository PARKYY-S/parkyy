"""
PARKYY's shared internal state - one place that says what's going on right now, kept up to date in the background.

  data/state.json  =  USER (activity, project, presence, goals)  +  ENVIRONMENT (laptop, internet)
                      +  MISSION (objective, progress, next step)  +  BRAINS (healthy / resting)  +  MODES

Every brain gets a SHORT snapshot of it (snapshot_text) instead of each part building its own blob of context.
"""
import json
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "state.json"
_state: dict = {}
_lock = threading.Lock()


def build() -> dict:
    s = {"updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        from tools import core as cx
        h = cx.hud_data()
    except Exception:
        h = {}
    s["user"] = {"app": h.get("app"), "project": h.get("project"), "presence": h.get("presence"),
                 "active_min": h.get("active_min"), "goals": h.get("goals", [])}
    s["environment"] = {"cpu": h.get("cpu"), "ram": h.get("ram"), "battery": h.get("battery"),
                        "charging": h.get("charging"), "disk_c_free_gb": h.get("disk_free_gb"), "online": h.get("online")}
    mi = h.get("mission")
    if mi and mi.get("status") in ("running", "paused", "waiting", "planned"):
        nxt = next((x["name"] for x in mi.get("steps", []) if x["status"] in ("doing", "todo")), "")
        s["mission"] = {"objective": mi["objective"], "status": mi["status"], "pct": mi.get("pct"), "next": nxt}
    try:
        import brains
        av = [b for b in brains.available() if b != "local"]
        s["brains"] = {"healthy": [b for b in av if brains.healthy(b)],
                       "resting": {b: brains._why.get(b, "resting") for b in av if not brains.healthy(b)}}
    except Exception:
        pass
    s["modes"] = h.get("modes", {})
    return s


def refresh() -> dict:
    global _state
    st = build()
    with _lock:
        _state = st
    try:
        FILE.parent.mkdir(exist_ok=True)
        FILE.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")
    except Exception:
        pass
    return st


def get(max_age: float = 60) -> dict:
    with _lock:
        st = _state
    if not st or time.time() - time.mktime(time.strptime(st["updated"], "%Y-%m-%d %H:%M:%S")) > max_age:
        st = refresh()
    return st


def snapshot_text() -> str:
    """~5 short lines for the brain prompt."""
    st = get()
    u, e = st.get("user", {}), st.get("environment", {})
    lines = ["STATE NOW (live):"]
    act = u.get("app") or "?"
    if u.get("project"):
        act += f" · project {u['project']}"
    if u.get("presence") and u["presence"] != "normal":
        act += f" · {u['presence']} mode"
    lines.append(f"- Saud: in {act}" + (f", active {u['active_min']} min" if u.get("active_min") else ""))
    if u.get("goals"):
        lines.append("- Goals: " + "; ".join(f"{g['outcome']} ({g['pct']}%)" for g in u["goals"]))
    env = [f"CPU {e['cpu']}%" if e.get("cpu") is not None else "", f"RAM {e['ram']}%" if e.get("ram") is not None else "",
           f"C: {e['disk_c_free_gb']} GB free" if e.get("disk_c_free_gb") is not None else "",
           f"battery {e['battery']}%" if e.get("battery") is not None else "", "offline" if e.get("online") is False else ""]
    lines.append("- Laptop: " + ", ".join(x for x in env if x))
    m = st.get("mission")
    if m:
        lines.append(f"- Mission ({m['status']}, {m['pct']}%): {m['objective']}" + (f" · next: {m['next']}" if m.get("next") else ""))
    b = st.get("brains", {})
    if b.get("resting"):
        lines.append("- Brains resting: " + ", ".join(f"{k} ({v})" for k, v in b["resting"].items()))
    md = st.get("modes") or {}
    on = [k for k in ("safe", "guest", "dry") if md.get(k)]
    if on:
        lines.append("- Modes ON: " + ", ".join({"dry": "simulation"}.get(x, x) for x in on))
    return "\n".join(lines)


def start():
    def loop():
        while True:
            try:
                refresh()
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()
