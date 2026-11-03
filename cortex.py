"""
PARKYY's cortex - the model-agnostic layer between PARKYY and its brains.

  PROFILES    what each brain is good at (a starting guess, 0..1). Any new brain just needs a profile here.
  scoreboard  what each brain ACTUALLY did, per kind of task: success, speed, failures, Saud's corrections.
              Saved in data/brain_scores.json and learned automatically from every call.
  classify()  what a message needs: chat / reasoning / coding / research / vision / mission (+ tools, privacy).
  rank()      orders the brains for that need: profile + learned evidence + speed + reliability.

So the router isn't "Gemini is the thinker" any more - it's "for this kind of task, my own history says X works best".
"""
import json
import re
import threading
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
SCORES = DATA / "brain_scores.json"
KINDS = ("chat", "reasoning", "coding", "research", "vision", "mission")

# Starting beliefs (0..1). Learned results take over as evidence comes in.
#            chat  reason code  research vision tools speed context privacy paid
_P = {
    "groq":       (.85, .80, .82, .75, .0, .85, .97, .60, .3, 0),
    "gemini":     (.86, .92, .88, .90, .95, .82, .75, .98, .3, 0),
    "nvidia":     (.82, .83, .83, .78, .0, .80, .80, .70, .3, 0),
    "mistral":    (.80, .80, .80, .75, .70, .80, .80, .70, .3, 0),
    "openrouter": (.75, .78, .76, .70, .0, .70, .55, .70, .2, 0),
    "cerebras":   (.80, .78, .78, .70, .0, .80, .99, .40, .3, 0),
    "claude":     (.92, .95, .96, .90, .85, .95, .70, .90, .4, 1),
    "gpt":        (.90, .92, .92, .86, .90, .92, .75, .90, .3, 1),
    "local":      (.55, .50, .50, .40, .0, .50, .30, .30, 1.0, 0),
}
_F = ("chat", "reasoning", "coding", "research", "vision", "tools", "speed", "context", "privacy", "paid")
PROFILES = {b: dict(zip(_F, v)) for b, v in _P.items()}
_NEED = {"chat": "chat", "reasoning": "reasoning", "coding": "coding", "research": "research", "vision": "vision",
         "mission": "tools"}

_CODE = re.compile(r"\b(code|coding|python|javascript|script|function|class|bug|debug|error|traceback|regex|sql|"
                   r"html|css|kotlin|gradle|compile|refactor|api|json)\b", re.I)
_RESEARCH = re.compile(r"\b(research|compare|comparison|best|latest|news|sources?|look up|find out|review|versus|vs\.?)\b", re.I)
_VISION = re.compile(r"\b(screen|image|photo|picture|screenshot|look at|what'?s this|see this)\b", re.I)
_REASON = re.compile(r"\b(why|plan|strategy|design|architect|explain|analy[sz]e|decide|should i|pros and cons|"
                     r"think|solve|calculate|math|prove|what if)\b", re.I)


def classify(msg: str) -> str:
    """What kind of job is this message? (cheap rules - no brain call)"""
    m = msg or ""
    if m.startswith("[MISSION") or re.search(r"\bmission\b|step by step|and then\b", m, re.I):
        return "mission"
    if _VISION.search(m):
        return "vision"
    if _CODE.search(m):
        return "coding"
    if _RESEARCH.search(m):
        return "research"
    if _REASON.search(m) or len(m) > 280:
        return "reasoning"
    return "chat"


# ------------------------------------------------------------------ scoreboard
_lock = threading.Lock()
_mem: dict | None = None
_dirty = 0.0
_last = {"brain": "", "kind": "", "t": 0.0}


def _load() -> dict:
    global _mem
    if _mem is None:
        try:
            _mem = json.loads(SCORES.read_text(encoding="utf-8"))
        except Exception:
            _mem = {}
    return _mem


def _save(force=False):
    global _dirty
    if not force and time.time() - _dirty < 20:
        return
    _dirty = time.time()
    try:
        DATA.mkdir(exist_ok=True)
        SCORES.write_text(json.dumps(_load(), indent=1), encoding="utf-8")
    except Exception:
        pass


def record(brain: str, kind: str, ok: bool, secs: float, err: str = ""):
    """Every brain call reports here. Rate limits only lower 'reliability'; real failures lower success too."""
    if not brain:
        return
    kind = kind if kind in KINDS else "chat"
    limit = bool(re.search(r"429|rate|quota|limit|503|overload|high demand|credit|timeout|timed out", err or "", re.I))
    with _lock:
        d = _load().setdefault(brain, {})
        k = d.setdefault(kind, {"n": 0, "ok": 0, "secs": 0.0})
        if ok:
            k["n"] += 1
            k["ok"] += 1
            k["secs"] += secs
        elif not limit:
            k["n"] += 1
        rec = d.setdefault("recent", [])
        rec.append([int(time.time()), 1 if ok else 0])
        del rec[:-30]
        if ok:
            _last.update(brain=brain, kind=kind, t=time.time())
        _save()


def correction():
    """Saud said the last answer was wrong -> that brain loses the point it got for it."""
    with _lock:
        if not _last["brain"] or time.time() - _last["t"] > 900:
            return
        k = _load().get(_last["brain"], {}).get(_last["kind"])
        if k and k["ok"] > 0:
            k["ok"] -= 1
            d = _load()[_last["brain"]]
            d["corrections"] = d.get("corrections", 0) + 1
        _save(force=True)


CORRECTION_RE = re.compile(r"^\s*(no[,.!]?\s+(that'?s|thats|it'?s)\s+(wrong|not right|incorrect)|that'?s (wrong|not right|incorrect)|"
                           r"wrong( answer)?|incorrect|you'?re wrong|not true)\b", re.I)


# ------------------------------------------------------------------ ranking
def _success(brain: str, kind: str) -> tuple[float, int]:
    prior = PROFILES.get(brain, {}).get(_NEED[kind], .5)
    k = _load().get(brain, {}).get(kind, {})
    n, ok = k.get("n", 0), k.get("ok", 0)
    return (ok + prior * 6) / (n + 6), n            # evidence slowly overrides the starting guess


def _speed(brain: str, kind: str) -> float:
    prior = PROFILES.get(brain, {}).get("speed", .5)
    k = _load().get(brain, {}).get(kind, {})
    if k.get("ok", 0) >= 3:
        avg = k["secs"] / k["ok"]
        return .5 * prior + .5 * (1 / (1 + avg / 8))
    return prior


def _reliability(brain: str) -> float:
    rec = [r for r in _load().get(brain, {}).get("recent", []) if time.time() - r[0] < 6 * 3600]
    if len(rec) < 3:
        return .9
    return .5 + .5 * sum(r[1] for r in rec) / len(rec)


def score(brain: str, kind: str) -> float:
    p = PROFILES.get(brain)
    if not p:
        return 0.0
    if kind == "vision" and p["vision"] < .5:
        return 0.0
    if kind == "mission" and p["tools"] < .6:
        return 0.0
    q, _ = _success(brain, kind)
    w_speed = .45 if kind == "chat" else .2
    s = (1 - w_speed) * q + w_speed * _speed(brain, kind)
    s *= _reliability(brain)
    if p["paid"]:
        s *= .97            # tiny nudge to save money when a free brain is just as good
    return round(s, 4)


def rank(kind: str, candidates: list[str]) -> list[str]:
    """Best first. Brains that can't do the job (e.g. no vision) are dropped."""
    scored = [(score(b, kind), b) for b in candidates if b != "local"]
    return [b for s, b in sorted(scored, reverse=True) if s > 0]


def explain(kind: str, candidates: list[str]) -> str:
    parts = [f"{b} {score(b, kind):.2f}" for b in rank(kind, candidates)]
    return f"[{kind}] " + " > ".join(parts)


def scoreboard_text(labels: dict | None = None) -> str:
    labels = labels or {}
    d = _load()
    if not d:
        return "🧠 Brain scoreboard: no results yet - it fills in as I answer things."
    lines = ["🧠 BRAIN SCOREBOARD (learned from my own results; success % · calls · avg seconds)"]
    for b in sorted(d, key=lambda x: -sum(v.get("n", 0) for k, v in d[x].items() if isinstance(v, dict))):
        cells = []
        for k in KINDS:
            v = d[b].get(k)
            if v and v.get("n"):
                avg = f"{v['secs'] / v['ok']:.0f}s" if v.get("ok") else "-"
                cells.append(f"{k} {100 * v['ok'] // v['n']}% ·{v['n']} ·{avg}")
        if cells:
            extra = f" · corrected {d[b]['corrections']}×" if d[b].get("corrections") else ""
            lines.append(f"• {labels.get(b, b)}: " + " | ".join(cells) + f" · reliability {100 * _reliability(b):.0f}%{extra}")
    return "\n".join(lines)


SCORE_RE = re.compile(r"^\s*(?:show\s+(?:me\s+)?)?(?:the\s+|my\s+|your\s+)?brain\s*(?:score|scores|scoreboard|stats|ranking|rankings)\s*[?.!]*\s*$|"
                      r"^\s*which brain is (?:the )?best\b.*$", re.I)


def flush():
    _save(force=True)
