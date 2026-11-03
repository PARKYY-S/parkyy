"""
PARKYY Guard - reliability, privacy and governance (rules enforced in CODE, not just asked of the AI).

  Status            "PARKYY, status": core, memory, mission, security, model, brains resting, tools, health, limits
  Recovery          notices when a resting brain is back ("Gemini is available again")
  Privacy router    private things (passwords, bank, IDs, health, "private/confidential") -> processed by the offline
                    brain; privacy level maximum / private / balanced / cloud
  Where to run      local or cloud advice (privacy + speed + memory + internet)
  Regression guard  self-test of every core system at start-up; compares with the last run and blocks nothing silently
  Versions          automatic build number + changelog from the code files themselves
  Mission scope     capability tokens per mission: actions outside the mission's scope pause the mission
  Anomaly guard     a mission suddenly doing far too many actions -> paused
  Blast radius      before deleting/moving: files, size, projects, git repos, missions affected, recoverable?
  Constitution      PARKYY's fixed rules + which ones the code enforces
  Weaknesses        "find your three biggest weaknesses" - from real logs, not generic talk
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

AST = timezone(timedelta(hours=3))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
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


# ============================================================ privacy router
PRIVATE_RE = re.compile(
    r"\b(password|passcode|pin code|otp|one[- ]time code|cvv|card number|credit card|debit card|iban|account number|"
    r"bank (?:statement|details|login)|passport|national id|iqama|aadhaar|pan card|social security|ssn|"
    r"salary slip|payslip|medical|diagnos|prescription|therapy|private|confidential|secret|do not share)\b"
    r"|\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b", re.I)
LEVELS = ("maximum", "private", "balanced", "cloud")


def privacy_level() -> str:
    lv = _jload("privacy.json", {}).get("level", "balanced")
    return lv if lv in LEVELS else "balanced"


def set_privacy(level: str) -> str:
    lv = (level or "").lower()
    lv = {"max": "maximum", "local": "maximum", "normal": "balanced", "high": "private"}.get(lv, lv)
    if lv not in LEVELS:
        return "Privacy levels: maximum (offline only), private (offline for anything private), balanced, cloud."
    _jsave("privacy.json", {"level": lv})
    return {"maximum": "🔒 Privacy MAXIMUM - everything stays on this laptop (offline brain, slower; no screen pictures to the cloud).",
            "private": "🔐 Privacy PRIVATE - anything that looks private is handled offline; cloud only for normal stuff.",
            "balanced": "⚖️ Privacy BALANCED - private-looking things offline, the rest uses the fast cloud brains.",
            "cloud": "☁️ Privacy CLOUD - cloud brains first (fastest). I'll still warn you about passwords/IDs."}[lv]


def privacy_route(text: str) -> tuple[str | None, str]:
    """Returns (forced_brain or None, note for Saud)."""
    lv = privacy_level()
    if lv == "maximum":
        return "local", ""
    if PRIVATE_RE.search(text or ""):
        if lv in ("private", "balanced"):
            return "local", "🔐 That looks private, so I'm handling it with my offline brain (it stays on this laptop)."
        return None, "⚠️ That looks private and your privacy level is CLOUD - it's going to a cloud brain."
    return None, ""


def cloud_vision_allowed() -> bool:
    return privacy_level() != "maximum"


def where_to_run(task: str = "") -> str:
    import brains
    lines = []
    priv = bool(PRIVATE_RE.search(task or ""))
    try:
        import psutil
        free = psutil.virtual_memory().available / 1024 ** 3
    except Exception:
        free = 8
    from tools import plus as px
    net = px._internet()
    healthy = [b for b in brains.available() if b != "local" and brains.healthy(b)]
    if priv or privacy_level() == "maximum":
        lines.append("LOCAL - it's private" if priv else "LOCAL - privacy level is maximum")
    elif not net or not healthy:
        lines.append("LOCAL - " + ("no internet" if not net else "no cloud brain is available right now"))
    else:
        lines.append(f"CLOUD ({healthy[0]}) - faster and smarter for this, nothing private in it")
    lines.append(f"Free memory {free:.1f} GB - " + ("fine for the offline brain" if free > 6 else
                                                     "tight: the offline brain needs ~6 GB and will be slow"))
    return "WHERE TO RUN: " + "\n".join(lines)


# ============================================================ brain recovery notices
_was_resting: set = set()


def brain_watch():
    import brains
    # only long breaks are worth a popup - a 20-second rate-limit pause is handled silently
    resting = {b for b in brains.available() if b != "local" and brains.cooldown_left(b) > 300}
    for b in _was_resting - resting:
        if _push:
            _push("alert", f"✅ {brains.LABELS.get(b, b)} is available again - back to normal.", False)
    for b in resting - _was_resting:
        alt = next((x for x in brains.available() if x != "local" and brains.healthy(x)), "local")
        if _push:
            _push("alert", f"⚠️ {brains.LABELS.get(b, b)} is resting ({brains._why.get(b, 'limit/outage')}). Impact: answers may be a bit "
                           f"different. Using {brains.LABELS.get(alt, alt)} meanwhile - I'll tell you when it's back.", False)
    _was_resting.clear()
    _was_resting.update(resting)


# ============================================================ status
def status() -> str:
    import brains
    from tools import tools as T
    from tools import plus as px
    from tools import core as cx
    m = px.modes()
    sec = "SAFE MODE" if m.get("safe") else "GUEST" if m.get("guest") else "SIMULATION" if m.get("dry") else "NORMAL (asks before actions)"
    av = [b for b in brains.available() if b != "local"]
    resting = [brains.LABELS.get(b, b) for b in av if not brains.healthy(b)]
    acc = T.access_status()
    on = sum(a["enabled"] for a in acc)
    try:
        import psutil
        res = f"CPU {psutil.cpu_percent(interval=0.3):.0f}% · RAM {psutil.virtual_memory().percent:.0f}%"
    except Exception:
        res = "?"
    mis = cx.active_mission()
    st = _jload("selftest.json", {})
    last = st.get("runs", [{}])[-1] if st.get("runs") else {}
    ver = version_info()
    rows = [("Core", "ONLINE"), ("Version", ver.get("version", "?")),
            ("Brain (last answer)", _last_brain()), ("Cloud brains", ", ".join(brains.LABELS.get(b, b) for b in av if brains.healthy(b)) or "none"),
            ("Resting", ", ".join(resting) or "none"),
            ("Offline brain", "loaded" if brains.local_running() else "sleeping (loads when needed)"),
            ("Memory", f"{_count_facts()} facts"), ("Mission", cx.mission_brief() or "IDLE"),
            ("Security", sec), ("Privacy", privacy_level().upper()), ("Presence", cx.presence()["mode"]),
            ("Abilities", f"{on}/{len(acc)} on · {len(T.TOOLS)} tools"), ("Resources", res),
            ("Self-test", f"{last.get('passed', '?')}/{last.get('total', '?')} passed ({last.get('time', 'never')[:16]})")]
    lim = ["TouchDesigner - scripts only", "Phone calls / watch - v0.8"]
    try:
        from tools import prime
        s = prime._service_status()
        lim += [f"{k} - not connected" for k in ("LG TV", "Spotify", "GitHub", "Gmail & Google") if not s.get(k)]
    except Exception:
        pass
    w = max(len(k) for k, _ in rows)
    return "PARKYY STATUS\n" + "\n".join(f"{k.ljust(w)}  {v}" for k, v in rows) + "\n\nLIMITATIONS\n" + "\n".join(lim)


def _last_brain():
    try:
        line = (DATA / "brain.log").read_text(encoding="utf-8").splitlines()[-1]
        mm = re.search(r" ok (\S+)", line)
        return mm.group(1) if mm else "?"
    except Exception:
        return "?"


def _count_facts():
    try:
        return len((ROOT / "memory" / "memory.txt").read_text(encoding="utf-8-sig").splitlines())
    except OSError:
        return 0


# ============================================================ versions + changelog
CODE = ["agent.py", "brains.py", "main.py", "memory.py", "learner.py", "world.py", "upgrade.py", "ears.py", "voice.py",
        "voice_input.py", "voiceconf.py", "desktop/index.html", "desktop/hands.js", "desktop/hud.js", "desktop/main.js"]


def _code_files():
    out = [ROOT / c for c in CODE] + sorted((ROOT / "tools").glob("*.py"))
    return [p for p in out if p.exists()]


def version_info() -> dict:
    v = _jload("version.json", {"build": 0, "files": {}, "history": []})
    cur = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha1(p.read_bytes()).hexdigest()[:10] for p in _code_files()}
    if cur != v.get("files"):
        changed = sorted(k for k in cur if v.get("files", {}).get(k) != cur[k])
        removed = sorted(k for k in v.get("files", {}) if k not in cur)
        tools_now = _tool_names()
        new_tools = sorted(set(tools_now) - set(v.get("tools", [])))
        v["build"] = v.get("build", 0) + 1
        v["history"].append({"build": v["build"], "date": now().isoformat(timespec="minutes"), "changed": changed,
                             "removed": removed, "new_tools": new_tools if v.get("tools") else []})
        v["history"] = v["history"][-40:]
        v["files"], v["tools"] = cur, tools_now
        _jsave("version.json", v)
    v["version"] = f"v0.9.{v['build']}"
    return v


def _tool_names():
    try:
        from tools import tools as T
        return sorted(T.TOOLS)
    except Exception:
        return []


def changelog(n: int = 3) -> str:
    v = version_info()
    if not v["history"]:
        return "No changes recorded yet."
    out = []
    for h in v["history"][-max(1, int(n or 3)):]:
        out.append(f"v0.9.{h['build']} ({h['date'][:16].replace('T', ' ')}): changed {len(h['changed'])} file(s): "
                   + ", ".join(h["changed"][:10]) + (f"; new tools: {', '.join(h['new_tools'][:15])}" if h.get("new_tools") else ""))
    return f"PARKYY {v['version']}\n" + "\n".join(out)


# ============================================================ regression guardian (self-test)
def _tests():
    from tools import tools as T
    from tools import plus as px
    from tools import core as cx
    from tools import prime, minds
    import brains
    tests = {
        "tool registry": lambda: len(T.TOOLS) > 100 and all(callable(t[0]) for t in T.TOOLS.values()),
        "permissions file": lambda: isinstance(T._perms(), dict),
        "reminders": lambda: isinstance(T.list_reminders(), str),
        "to-dos": lambda: isinstance(T.list_todos(), str),
        "laptop monitor": lambda: "CPU" in px.system_monitor(),
        "habits": lambda: isinstance(px.habits(), str),
        "missions": lambda: isinstance(cx.mission_status(), str),
        "context engine": lambda: cx.context_text().startswith("CONTEXT"),
        "vault search": lambda: isinstance(cx.vault_search("test"), str),
        "goals": lambda: isinstance(prime.goals(), str),
        "world model": lambda: isinstance(prime.whats_important(), str),
        "memory files": lambda: (ROOT / "memory").exists(),
        "skills folder": lambda: (ROOT / "skills").exists(),
        "D: only rule": lambda: _c_rule_ok(),
        "safety: deleting needs a Yes": lambda: T.TOOLS["recycle_path"][1] and T.risk_of("recycle_path") >= 3,
        "safety: commands need a Yes": lambda: T.TOOLS["run_command"][1] and T.risk_of("run_command") >= 4,
        "a cloud brain is configured": lambda: any(b != "local" for b in brains.available()),
        "internet": lambda: px._internet(),
    }
    try:
        from tools import gsuite as gs
        if (DATA / "google-token.json").exists():
            tests["Gmail & Calendar"] = lambda: gs.connected()
    except Exception:
        pass
    if (DATA / "spotify.json").exists():
        tests["Spotify"] = lambda: __import__("tools.spotify", fromlist=["x"]).status().find("✅") >= 0
    if (DATA / "github-token.txt").exists():
        tests["GitHub"] = lambda: "connected" in __import__("tools.github", fromlist=["x"]).status().lower()
    return tests


def _c_rule_ok():
    from tools import plus as px
    if os.name != "nt":
        return True
    try:
        px._dest_path("C:\\PARKYY-selftest")
        return False
    except ValueError:
        return True


def self_test(announce: bool = False) -> str:
    res = {}
    for name, fn in _tests().items():
        try:
            res[name] = bool(fn())
        except Exception:
            res[name] = False
    st = _jload("selftest.json", {"runs": []})
    prev = st["runs"][-1]["results"] if st["runs"] else {}
    v = version_info()
    run = {"time": now().isoformat(timespec="minutes"), "version": v["version"], "results": res,
           "passed": sum(res.values()), "total": len(res)}
    st["runs"] = (st["runs"] + [run])[-30:]
    _jsave("selftest.json", st)
    broke = [k for k, ok in res.items() if not ok and prev.get(k)]
    fixed = [k for k, ok in res.items() if ok and prev.get(k) is False]
    out = (f"SELF-TEST {v['version']}: {run['passed']}/{run['total']} passed\n" +
           "\n".join(f"{'✓' if ok else '✗'} {k}" for k, ok in res.items()))
    if broke:
        out += "\n\n⚠ REGRESSION: these worked last time and fail now: " + ", ".join(broke) + \
               "\n(Check what changed: “PARKYY changelog”.)"
        if announce and _push:
            _push("alert", f"⚠️ Self-test: {', '.join(broke)} stopped working since the last run ({v['version']}). Ask “PARKYY status”.", True)
    if fixed:
        out += "\nFixed since last time: " + ", ".join(fixed)
    return out


# ============================================================ mission scope (capability tokens) + anomaly guard
SAFE_ALWAYS = {"mission_update", "mission_control", "mission_wait", "write_note", "add_todo", "set_timer", "project_note",
               "goal_update", "lab_record", "send_to_phone", "skill_create"}
_counts: dict = {}


def mission_scope(m: dict) -> dict:
    """Which ability groups + folders a mission may touch (decided when it starts)."""
    if "scope" in m:
        return m["scope"]
    from tools import prime
    text = m["objective"] + " " + " ".join(s["name"] for s in m["steps"])
    groups = sorted({g for g, rx in prime.CAP_WORDS.items() if re.search(rx, text, re.I)})
    paths = re.findall(r"[A-Za-z]:\\[^\s,;\"']+", text)
    if re.search(r"downloads", text, re.I):
        from tools.plus import known_folder
        paths.append(str(known_folder("downloads")))
    return {"groups": groups, "paths": paths}


def check_action(tool: str, group: str | None, args: dict, risk: int) -> str | None:
    """Called for every ACTION while a mission runs. Returns a reason to stop, or None."""
    if risk <= 0 or tool in SAFE_ALWAYS:
        return None
    from tools import core as cx
    m = cx.active_mission()
    if not m or m.get("status") != "running":
        return None
    ms = cx._missions()
    mm = next((x for x in ms if x["id"] == m["id"]), None)
    if mm is None:
        return None
    if "scope" not in mm:
        mm["scope"] = mission_scope(mm)
        cx._msave(ms)
    sc = mm["scope"]
    reason = None
    gmap = {"filesops": "filesops", "files": "files"}
    if group and sc["groups"] and group not in sc["groups"] and gmap.get(group, group) not in sc["groups"]:
        reason = f"“{tool}” ({group}) is outside this mission's scope ({', '.join(sc['groups'])})"
    if not reason and sc["paths"]:
        for k in ("path", "source", "destination", "folder"):
            p = str(args.get(k, ""))
            if p and not any(p.lower().startswith(x.lower()) for x in sc["paths"]) and not p.upper().startswith("D:\\PARKYY-SORTED"):
                reason = f"{p} is outside the folders this mission is about ({', '.join(sc['paths'])})"
                break
    c = _counts.setdefault(m["id"], {"n": 0, "risky": 0})
    c["n"] += 1
    c["risky"] += int(risk >= 3)
    limit = max(25, 6 * len(m["steps"]))
    anomaly = False
    if not reason and (c["n"] > limit or c["risky"] > max(10, 3 * len(m["steps"]))):
        anomaly = True
        reason = f"this mission has already tried {c['n']} actions ({c['risky']} risky) - far more than its {len(m['steps'])} steps need"
    if reason and not anomaly:
        # outside the mission's scope isn't necessarily wrong - ask Saud instead of stopping the whole mission
        return "ASK:" + reason
    if reason:
        cx.mission_control("pause")
        if _push:
            _push("alert", f"🛡️ Mission paused: {reason}. Say “resume mission” if that's really OK.", True)
        return f"STOPPED BY SAFETY GUARD: {reason}. The mission is paused. Tell Saud exactly this and wait for him."
    return None


# ============================================================ blast radius
def blast_radius(path: str) -> str:
    p = Path(os.path.expandvars(os.path.expanduser((path or "").strip().strip('"'))))
    if not p.exists():
        return ""
    files, size, gits = 0, 0, 0
    if p.is_dir():
        for f in p.rglob("*"):
            if f.is_file():
                files += 1
                try:
                    size += f.stat().st_size
                except OSError:
                    pass
            elif f.name == ".git":
                gits += 1
            if files > 20000:
                break
    else:
        files, size = 1, p.stat().st_size
    projects = []
    try:
        from tools import prime
        for x in prime._jload("goals.json", []):
            if p.name.lower() in (x["outcome"] + " ".join(s["name"] for s in x["steps"])).lower():
                projects.append(x["outcome"])
    except Exception:
        pass
    mis = []
    try:
        from tools import core as cx
        mis = [m["objective"] for m in cx._missions() if m["status"] in ("running", "waiting", "paused")
               and p.name.lower() in json.dumps(m).lower()]
    except Exception:
        pass
    level = "HIGH" if files > 200 or gits or projects or mis else "MEDIUM" if files > 20 else "LOW"
    return (f"BLAST RADIUS: {files} file(s), {size / 1024 ** 2:.0f} MB" + (f", {gits} git repo(s)" if gits else "") +
            (f", goals: {', '.join(projects[:2])}" if projects else "") + (f", missions: {', '.join(mis[:2])}" if mis else "") +
            f" · recoverable from the Recycle Bin · risk {level}")


# ============================================================ constitution
CONSTITUTION = [
    ("Never act without Saud's approval for anything that changes things (level 1+).", "code: every action tool waits for Yes"),
    ("Never disable or bypass its own safety controls or permissions.", "code: no tool can change permissions/safe mode; only Saud's words/UI"),
    ("Never put anything on C: - always D:.", "code: file tools refuse C: destinations; temp/cache on D:"),
    ("Never touch system folders or its own program files.", "code: protected-path check"),
    ("Never hide what it did.", "code: activity log + decision journal for every action"),
    ("Never claim a result it didn't get.", "prompt + tools return NOT DONE / SIMULATED explicitly"),
    ("Always report failures honestly.", "prompt + self-test + brain log"),
    ("Stay inside a mission's scope; stop when the scope or intent is unclear.", "code: mission scope + anomaly guard pause the mission"),
    ("Private data stays local when the privacy level says so.", "code: privacy router"),
    ("Critical actions need Saud's PIN (if set).", "code: level-4 PIN check"),
    ("Never modify its own code by itself - only proposals Saud approves.", "design: no self-code-writing tool"),
    ("Emergency stop always works.", "code: 'emergency' handled before the AI even sees the message"),
]


def constitution() -> str:
    return "PARKYY CONSTITUTION\n" + "\n".join(f"{i + 1}. {r}\n   ↳ enforced by {e}" for i, (r, e) in enumerate(CONSTITUTION))


# ============================================================ weaknesses (from evidence)
def weaknesses() -> str:
    ev = []
    try:
        bl = (DATA / "brain.log").read_text(encoding="utf-8").splitlines()[-300:]
        fails = [l for l in bl if " FAIL " in l]
        secs = [float(x) for x in re.findall(r" ok \S+ (\d+(?:\.\d+)?)s", "\n".join(bl))]
        if fails:
            kinds = {}
            for f in fails:
                k = "rate limit" if "429" in f else "no credit" if "credit" in f else "retired model" if "404" in f else "overloaded" if "503" in f else "other"
                kinds[k] = kinds.get(k, 0) + 1
            ev.append(f"Brain failures: {len(fails)} of the last {len(bl)} calls ({', '.join(f'{k} ×{v}' for k, v in kinds.items())}).")
        if secs:
            slow = sum(1 for s in secs if s > 15)
            ev.append(f"Speed: median {sorted(secs)[len(secs) // 2]:.1f}s per brain call, {slow} calls took over 15s.")
    except OSError:
        pass
    try:
        lines = (DATA / "ears.log").read_text(encoding="utf-8").splitlines()[-60:]
        silent = sum("silent" in l for l in lines)
        empty = sum("text=''" in l for l in lines)
        ev.append(f"Hearing: {silent} silent-mic and {empty} empty results in the last {len(lines)} tries.")
    except OSError:
        pass
    try:
        acts = (DATA / "activity.log").read_text(encoding="utf-8").splitlines()[-800:]
        fails = [a for a in acts if re.search(r"failed|error|couldn't|not found|isn't connected", a, re.I)]
        from collections import Counter
        c = Counter(a.split("\t")[1] for a in fails if "\t" in a)
        if c:
            ev.append("Tools failing most: " + ", ".join(f"{k} ×{v}" for k, v in c.most_common(5)))
    except OSError:
        pass
    st = _jload("selftest.json", {}).get("runs", [])
    if st:
        bad = [k for k, ok in st[-1]["results"].items() if not ok]
        if bad:
            ev.append("Self-test failing: " + ", ".join(bad))
    try:
        from tools import core as cx
        stuck = [m for m in cx._missions() if any(s.get("status") == "failed" for s in m["steps"])]
        if stuck:
            ev.append(f"Missions with failed steps: {len(stuck)} (e.g. {stuck[-1]['objective'][:60]})")
    except Exception:
        pass
    if not ev:
        return "I don't have enough logs yet to judge my weaknesses honestly - use me for a few days and ask again."
    from tools import minds
    try:
        verdict = minds._ask("You are PARKYY assessing YOURSELF. Using ONLY this evidence, name your 3 biggest weaknesses, "
                         "each with the evidence line it comes from and one concrete fix. No generic AI criticism.",
                             "\n".join(ev), 600)
    except Exception:
        verdict = "(My brains are resting right now, so here's just the raw evidence - ask again later for my analysis.)"
    return "MY 3 BIGGEST WEAKNESSES (from my own logs)\nEvidence:\n- " + "\n- ".join(ev) + "\n\n" + verdict


# ============================================================ quick + loop
QUICK = [
    (re.compile(r"^\s*(?:parkyy[,\s]+)?status\s*[?.!]*\s*$|^\s*(?:system|parkyy|your) status\s*[?.!]*\s*$", re.I), lambda m: status()),
    (re.compile(r"^\s*(?:privacy|privacy level|privacy mode)\s+(maximum|max|private|balanced|normal|cloud|local|high)\s*[.!]?\s*$|"
                r"^\s*(?:set )?(maximum|max|private|balanced|cloud) privacy\s*[.!]?\s*$", re.I),
     lambda m: set_privacy(m.group(1) or m.group(2))),
    (re.compile(r"^\s*(?:run (?:a |the )?)?self[- ]?test\s*[?.!]*\s*$|^\s*test yourself\s*[?.!]*\s*$", re.I), lambda m: self_test()),
    (re.compile(r"^\s*(?:parkyy )?(?:changelog|what(?:'s| is) new in (?:you|parkyy)|what changed in (?:you|parkyy)|your version|version)\s*[?.!]*\s*$", re.I),
     lambda m: changelog()),
    (re.compile(r"^\s*(?:(?:show|read) (?:me )?)?(?:your |the )?constitution\s*[?.!]*\s*$|^\s*your rules\s*[?.!]*\s*$", re.I), lambda m: constitution()),
    (re.compile(r"^\s*(?:find |what are )?your (?:three |3 )?(?:biggest )?weakness(?:es)?\s*[?.!]*\s*$", re.I), lambda m: weaknesses()),
    (re.compile(r"^\s*should (?:i|you|we) run (?:this|it) (?:locally|local|in the cloud|on the cloud)(?: or (?:locally|in the cloud))?\??\s*(.*)$", re.I),
     lambda m: where_to_run(m.group(1) or "")),
]


def quick(text: str) -> str | None:
    for rx, fn in QUICK:
        mm = rx.match(text or "")
        if mm:
            return fn(mm)
    return None


_started = False


def start(push):
    global _push, _started
    _push = push
    if _started:
        return
    _started = True
    import threading

    def boot():
        time.sleep(90)
        try:
            self_test(announce=True)
        except Exception:
            pass
        while True:
            try:
                brain_watch()
            except Exception:
                pass
            try:
                from tools import prime
                prime.meeting_watch(_push)
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=boot, daemon=True).start()
