"""
PARKYY's swappable brains (matches the video's design).

The HARNESS (agent.py) does the thinking-in-steps and tool calls. The BRAIN
is the model plugged into it - and now it's swappable:

  local   - free Hermes model in LM Studio. Offline, no cost. The default.
  claude  - Anthropic Claude   (needs ANTHROPIC_API_KEY in .env)
  gpt     - OpenAI GPT / Codex  (needs OPENAI_API_KEY)
  gemini  - Google Gemini       (needs GEMINI_API_KEY or GOOGLE_API_KEY - has a FREE tier)
  groq    - Groq (FREE tier, very fast; needs GROQ_API_KEY from console.groq.com)
  openrouter - OpenRouter FREE models (needs OPENROUTER_API_KEY from openrouter.ai)
  mistral - Mistral FREE monthly allowance, no card (needs MISTRAL_API_KEY from console.mistral.ai)
  nvidia  - NVIDIA Build FREE (40 requests/min, no daily cap; needs NVIDIA_API_KEY from build.nvidia.com)
  cerebras - Cerebras, very fast (needs CEREBRAS_API_KEY - their free trial now asks for a card)

All four are driven through the same OpenAI-style API (Anthropic, OpenAI and
Google all offer an OpenAI-compatible endpoint), so the harness and its tools
work the same whichever brain is in.

MODE (saved in brains.json, change any time by chatting):
  auto   - PARKYY picks: a cloud brain when it's online AND the task is hard
           (coding, building, R&D, long questions); the free local brain when
           offline or for quick stuff. THIS IS THE DEFAULT.
  local / claude / gpt / gemini - always use that one (falls back to local if
           a cloud brain has no key or there's no internet).

The exact model names change over time, so set them in .env if a default is
out of date, e.g.  PARKYY_CLAUDE_MODEL=claude-sonnet-4-5

NOTE: a ChatGPT/Claude/Gemini *subscription* is not API access - each cloud
brain needs that provider's *API key* (pay-per-use), from its developer site.
"""

import json
import os
import re
import socket
import threading
from pathlib import Path

from openai import OpenAI

from upgrade import current_model as current_local_model

HERE = Path(__file__).resolve().parent
STATE = HERE / "brains.json"

LMSTUDIO_BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")

# base_url, which env var holds the key, default model (override in .env), pretty name
CLOUD = {
    "claude": {
        "base_url": "https://api.anthropic.com/v1/",
        "key_envs": ["ANTHROPIC_API_KEY"],
        "model_env": "PARKYY_CLAUDE_MODEL",
        "default_model": "claude-sonnet-4-5",
        "label": "Claude",
        "console": "console.anthropic.com",
    },
    "gpt": {
        "base_url": "https://api.openai.com/v1",
        "key_envs": ["OPENAI_API_KEY"],
        "model_env": "PARKYY_GPT_MODEL",
        "default_model": "gpt-4o",
        "label": "GPT / Codex",
        "console": "platform.openai.com",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_envs": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "model_env": "PARKYY_GEMINI_MODEL",
        "default_model": "gemini-2.5-flash",
        "label": "Gemini",
        "console": "aistudio.google.com",
    },
    # ---- FREE cloud brains (daily limits, no card needed) ----
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_envs": ["GROQ_API_KEY"],
        "model_env": "PARKYY_GROQ_MODEL",
        "default_model": "llama-3.3-70b-versatile",
        "label": "Groq (free)",
        "console": "console.groq.com",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_envs": ["OPENROUTER_API_KEY"],
        "model_env": "PARKYY_OPENROUTER_MODEL",
        "default_model": "openai/gpt-oss-120b:free",
        "label": "OpenRouter (free)",
        "console": "openrouter.ai/keys",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "key_envs": ["MISTRAL_API_KEY"],
        "model_env": "PARKYY_MISTRAL_MODEL",
        "default_model": "mistral-small-latest",
        "label": "Mistral (free)",
        "console": "console.mistral.ai/api-keys",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_envs": ["NVIDIA_API_KEY"],
        "model_env": "PARKYY_NVIDIA_MODEL",
        "default_model": "meta/llama-3.3-70b-instruct",
        "label": "NVIDIA (free)",
        "console": "build.nvidia.com",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "key_envs": ["CEREBRAS_API_KEY"],
        "model_env": "PARKYY_CEREBRAS_MODEL",
        "default_model": "llama-3.3-70b",
        "label": "Cerebras",
        "console": "cloud.cerebras.ai",
    },
}
ORDER = ["local", "gemini", "groq", "nvidia", "mistral", "openrouter", "cerebras", "claude", "gpt"]
LABELS = {"local": "Local (free, offline)", **{k: v["label"] for k, v in CLOUD.items()}}

# a task is "tough" -> worth a cloud brain in auto mode
TOUGH = re.compile(r"\b(code|coding|program|programming|debug|bug|error|fix|refactor|build|develop|function|"
                   r"class|algorithm|script|regex|sql|api|compile|optimi[sz]e|3d|blender|cad|kicad|touchdesigner|"
                   r"glsl|shader|design|architect|analy[sz]e|research|explain why|strateg|plan out|firmware|"
                   r"circuit|pcb|game|website|app\b|essay|write me|draft)\b", re.I)

_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(d: dict):
    with _lock:
        STATE.write_text(json.dumps(d, indent=2), encoding="utf-8")


def has_key(brain: str) -> bool:
    if brain == "local":
        return True
    return any(os.environ.get(e) for e in CLOUD[brain]["key_envs"])


def available() -> list[str]:
    return [b for b in ORDER if has_key(b)]


def online(timeout: float = 1.5) -> bool:
    for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return True
        except OSError:
            continue
    return False


def mode() -> str:
    return _load().get("mode", "auto")


# ---------------------------------------------------------------- health + routing
_cool: dict[str, float] = {}       # brain -> time until which we skip it (rate limit / outage)


_why: dict[str, str] = {}          # brain -> short reason it's resting


def mark_fail(brain: str, err) -> None:
    """Put a brain on a break that matches the error: a few seconds for a per-minute limit, longer for
    'no credit'. Errors caused by OUR request (too big, bad format) don't rest the brain at all."""
    import time as _t
    t = str(err).lower()
    if "request too large" in t or "413" in t or "thought_signature" in t or "context length" in t:
        return
    secs, why = 0, ""
    m = re.search(r"(?:try again|retry) in (?:(\d+)h)?(?:(\d+)m(?!s))?([\d.]+)\s*(ms|s)\b", t)
    if "credit balance" in t or "insufficient credit" in t or "out of credit" in t or "payment required" in t or " 402" in t:
        secs, why = 6 * 3600, "no credit"
    elif m:
        secs = (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 +
                float(m.group(3)) / (1000 if m.group(4) == "ms" else 1))
        daily = "per day" in t or "tpd" in t or "rpd" in t
        secs, why = min(max(secs + 1, 3), 6 * 3600), ("daily free limit used up" if daily else "rate limit")
    elif "per day" in t or "perday" in t or "daily" in t:
        secs, why = 3600, "daily free limit used up"
    elif "quota" in t or "429" in t or "rate" in t:
        secs, why = 120, "rate limit"
    elif "503" in t or "overload" in t or "high demand" in t or "unavailable" in t:
        secs, why = 60, "overloaded"
    elif "timeout" in t or "timed out" in t or "connection" in t:
        secs, why = 90, "timed out"
    if secs:
        _cool[brain] = _t.time() + secs
        _why[brain] = why


def cooldown_left(brain: str) -> float:
    import time as _t
    return max(0.0, _cool.get(brain, 0) - _t.time())


def resting_text() -> str:
    """'Groq (rate limit, 20s), Gemini (daily free limit used up, 41 min)' - for honest error messages."""
    out = []
    for b in available():
        left = cooldown_left(b) if b != "local" else 0
        if left > 0:
            span = f"{int(left)}s" if left < 90 else f"{int(left // 60)} min"
            out.append(f"{LABELS.get(b, b)} ({_why.get(b, 'resting')}, {span})")
    return ", ".join(out)


def healthy(brain: str) -> bool:
    import time as _t
    return brain == "local" or (has_key(brain) and _cool.get(brain, 0) < _t.time())


FAST = ("groq", "nvidia", "mistral", "gemini", "cerebras", "openrouter", "gpt", "claude")          # quick chat + simple commands
REASON = ("gemini", "nvidia", "mistral", "claude", "gpt", "groq", "cerebras", "openrouter")         # hard problems, code, planning
VISION = ("gemini", "mistral", "gpt", "claude", "openrouter")                # pictures / screens


def route(user_message: str, need: str = "") -> str | None:
    """Capability router: what does this job need, and which healthy brain is best at it - judged by each brain's
    profile AND its learned track record (cortex.py). Old names fast/reason still work."""
    import cortex
    kind = {"fast": "chat", "reason": "reasoning"}.get(need, need) or cortex.classify(user_message)
    ranked = cortex.rank(kind, [b for b in available() if healthy(b)])
    return ranked[0] if ranked else None


def ranked(kind: str) -> list[str]:
    """All cloud brains with a key, best first for this kind of job (health is checked by the caller)."""
    import cortex
    return cortex.rank(kind, available())


def preferred_cloud() -> str | None:
    saved = _load().get("cloud")
    if saved and has_key(saved) and healthy(saved):
        return saved
    for b in ("claude", "gpt", "gemini", "nvidia", "mistral", "groq", "cerebras", "openrouter"):
        if has_key(b) and healthy(b):
            return b
    return None


def _model(brain: str) -> str:
    if brain == "local":
        return current_local_model()
    c = CLOUD[brain]
    return os.environ.get(c["model_env"]) or _found_models().get(brain) or c["default_model"]


# ---------------------------------------------------------------- self-updating model names
# Cloud companies retire model names (gemini-2.5-flash, llama-3.3-70b...). When that happens PARKYY asks
# the service which models it has and switches to the newest good one by itself.
MODELS_FILE = HERE / "data" / "models.json"
_SKIP = re.compile(r"embed|tts|audio|image|vision-only|live|whisper|guard|moderat|transcri|veo|imagen|aqa|"
                   r"learnlm|robotics|computer-use|native|deep-research|prompt-guard|orpheus|compound|safeguard", re.I)
_PREFER = {
    "gemini": [r"^gemini-[\d.]+-flash$", r"^gemini-[\d.]+-flash-latest$", r"^gemini-flash-latest$",
               r"^gemini-[\d.]+-flash", r"^gemini-[\d.]+-pro$"],
    "groq": [r"gpt-oss-120b", r"llama-4-maverick", r"kimi-k2", r"qwen3-32b", r"llama-4", r"llama.*versatile", r"llama"],
    "claude": [r"sonnet", r"opus", r"haiku"],
    "gpt": [r"^gpt-[\d.]+o?$", r"^gpt-[\d.]+-mini$", r"^gpt"],
    "openrouter": [r"gpt-oss-120b:free", r":free$"],
    "mistral": [r"^mistral-small-latest$", r"^mistral-small", r"^mistral-medium-latest$", r"^mistral-large-latest$"],
    "nvidia": [r"deepseek-v4[\w.-]*flash", r"deepseek-v4", r"kimi-k2", r"qwen3\.5|qwen3-235b|qwen3-next-80b", r"kimi-k2-instruct", r"qwen3-235b|qwen3-next-80b", r"deepseek-v3", r"llama-3\.3-70b-instruct",
               r"llama-4-maverick", r"mistral-large", r"nemotron-super", r"gpt-oss-120b"],
    "cerebras": [r"gpt-oss-120b", r"qwen-3-\d+b", r"llama-3\.3-70b", r"llama"],
}


def _found_models() -> dict:
    try:
        return json.loads(MODELS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ver(name: str) -> tuple:
    return tuple(float(x) if x.replace(".", "", 1).isdigit() else 0 for x in re.findall(r"\d+(?:\.\d+)?", name)[:2])


def _note_refresh(brain, best, tried, total):
    try:
        with open(HERE / "data" / "brain.log", "a", encoding="utf-8") as f:
            import time as _t
            f.write(_t.strftime("%Y-%m-%d %H:%M:%S ") + f"refresh {brain}: {total} models listed, probed {tried} -> {best}\n")
    except Exception:
        pass


def refresh_model(brain: str) -> str | None:
    """Ask the service for its model list and save the best one. Returns the new model name (or None)."""
    if brain == "local" or brain not in CLOUD or not has_key(brain):
        return None
    try:
        cl = OpenAI(base_url=CLOUD[brain]["base_url"], api_key=_key(brain), timeout=20, max_retries=0)
        names = [m.id.replace("models/", "") for m in cl.models.list()]
    except Exception as e:
        _note_refresh(brain, None, [f"model list failed: {str(e)[:120]}"], 0)
        return None
    names = [n for n in names if not _SKIP.search(n)]
    # candidates in order of preference; the model LIST includes models this key can't use, so each one is
    # PROBED with a 1-word request and the first that really answers wins (NVIDIA lists ~190, only ~100 work)
    cands = []
    for pat in _PREFER.get(brain, []):
        hits = [n for n in names if re.search(pat, n, re.I) and n not in cands]
        hits.sort(key=lambda n: (_ver(n), "preview" not in n and "exp" not in n), reverse=True)
        cands += [h for h in hits if "preview" not in h and "exp" not in h] + [h for h in hits if "preview" in h or "exp" in h]
    best, tried = None, []
    for n in cands[:6]:
        tried.append(n)
        try:
            cl.with_options(timeout=8).chat.completions.create(
                model=n, messages=[{"role": "user", "content": "hi"}], max_tokens=1)
            best = n
        except Exception as e:
            if re.search(r"429|rate", str(e), re.I):      # exists, just busy right now
                best = n
        if best:
            break
    _note_refresh(brain, best, tried, len(names))
    if not best:
        import time as _t
        _cool[brain] = _t.time() + 3 * 3600          # none of its models answer - stop knocking for a while
        _why[brain] = "no working model on this key"
    if best:
        d = _found_models()
        d[brain] = best
        MODELS_FILE.parent.mkdir(exist_ok=True)
        MODELS_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return best


def _key(brain: str) -> str:
    if brain == "local":
        return "lm-studio"
    for e in CLOUD[brain]["key_envs"]:
        if os.environ.get(e):
            return os.environ[e]
    return ""


_local_lock = threading.Lock()


def local_running() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen(LMSTUDIO_BASE_URL.rstrip("/") + "/models", timeout=1.5).read()
        return True
    except Exception:
        return False


def ensure_local(wait: float = 90) -> bool:
    """The offline brain is only loaded when it's needed (it takes several GB of memory)."""
    if local_running():
        return True
    with _local_lock:
        if local_running():
            return True
        import subprocess, time as _t
        lms = Path.home() / ".lmstudio" / "bin" / ("lms.exe" if os.name == "nt" else "lms")
        if not lms.exists():
            return False
        nw = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run([str(lms), "server", "start"], timeout=60, creationflags=nw, capture_output=True)
            subprocess.run([str(lms), "load", current_local_model(), "-y"], timeout=wait, creationflags=nw, capture_output=True)
        except Exception:
            pass
        t0 = _t.time()
        while _t.time() - t0 < 20:
            if local_running():
                return True
            _t.sleep(1)
    return local_running()


def unload_local():
    """Free the offline brain's memory (several GB) - used after it timed out on a full-RAM laptop."""
    import subprocess
    lms = Path.home() / ".lmstudio" / "bin" / ("lms.exe" if os.name == "nt" else "lms")
    if lms.exists():
        try:
            subprocess.Popen([str(lms), "unload", "--all"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def local_fits() -> bool:
    """Is there room for the offline brain? Loading it with <4 GB free freezes the laptop and still times out."""
    if local_running():
        return True
    try:
        import psutil
        return psutil.virtual_memory().available > 4 * 1024 ** 3
    except Exception:
        return True


def client_for(brain: str):
    """Returns (OpenAI-style client, model_name, brain_key). Falls back to local if a cloud brain isn't usable."""
    if brain != "local" and not has_key(brain):
        brain = "local"
    if brain == "local":
        ensure_local()
        return OpenAI(base_url=LMSTUDIO_BASE_URL, api_key="lm-studio", timeout=75, max_retries=0), _model("local"), "local"
    return OpenAI(base_url=CLOUD[brain]["base_url"], api_key=_key(brain), timeout=45, max_retries=0), _model(brain), brain


def pick(user_message: str) -> str:
    """Which brain to use for this message, honouring the saved mode."""
    m = mode()
    if m in CLOUD:
        if has_key(m) and online():
            return m if healthy(m) else (route(user_message) or m)
        return "local"
    if m == "local":
        return "local"
    # auto: a free cloud brain whenever online (fast, and the offline brain doesn't need to sit in memory);
    # the offline brain only when there's no internet
    if online():
        pc = route(user_message) or preferred_cloud() or next((b for b in ORDER if b != "local" and has_key(b)), None)
        if pc:
            return pc
    return "local"


def status() -> dict:
    return {
        "mode": mode(),
        "preferred_cloud": preferred_cloud(),
        "available": available(),
        "online": online(),
        "local_model": _model("local"),
        "labels": LABELS,
        "cloud_setup": {b: {"have_key": has_key(b), "console": CLOUD[b]["console"], "label": CLOUD[b]["label"]}
                        for b in CLOUD},
    }


def set_mode(new: str) -> str:
    new = (new or "").lower().strip()
    if new not in ("auto", *ORDER):
        return "Brains: auto, local, claude, gpt, gemini, groq, nvidia, mistral, openrouter, cerebras."
    d = _load()
    d["mode"] = new
    if new in CLOUD:
        d["cloud"] = new
    _save(d)
    if new == "auto":
        pc = preferred_cloud()
        if not pc and any(has_key(b) for b in CLOUD):
            return ("Auto brain on. My cloud brains are all resting right now (" + (resting_text() or "limits") +
                    ") - I'll pick the best one for each job as soon as they're back.")
        return (f"Auto brain on: I'll pick the best brain for each job (now: {LABELS.get(pc, 'a cloud brain')}), "
                "and my offline brain only when there's no internet." if pc else
                "Auto brain on, but no cloud key is set yet, so I'll use my free local brain. "
                "Add an API key in .env to unlock a cloud brain (Groq, NVIDIA and OpenRouter have free keys).")
    if new == "local":
        return "Okay, I'll always use my free local brain now."
    if not has_key(new):
        c = CLOUD[new]
        return (f"I'll switch to {c['label']} once its key is set. Add {c['key_envs'][0]}=... to your .env "
                f"(get one from {c['console']}). Until then I'll use my local brain.")
    return f"Okay, I'll always use {LABELS[new]} now."


BRAIN_RE = re.compile(r"^\s*(?:please\s+)?(?:use|switch to|change to|go to)\s+"
                      r"(auto|local|claude|gpt|codex|openai|gemini|google|groq|grok|nvidia|mistral|cerebras|openrouter|open\s+router|free)\s*(?:brain|model)?\s*[.!]?\s*$", re.I)
WHICH_RE = re.compile(r"^\s*(?:which|what)\s+brain\b.*\??\s*$", re.I)
ALIAS = {"codex": "gpt", "openai": "gpt", "google": "gemini", "grok": "groq", "open router": "openrouter",
         "free": "groq"}


def handle_command(user_message: str) -> str | None:
    if WHICH_RE.match(user_message):
        st = status()
        cur = LABELS.get(preferred_cloud() if st["mode"] == "auto" else st["mode"], "my local brain")
        extra = f" (auto picks {cur} for hard tasks)" if st["mode"] == "auto" else ""
        return f"Brain mode: {st['mode']}{extra}. Ready: {', '.join(LABELS[b] for b in st['available'])}."
    m = BRAIN_RE.match(user_message)
    if m:
        name = re.sub(r"\s+", " ", m.group(1).lower())
        return set_mode(ALIAS.get(name, name))
    return None


class _Completions:
    def create(self, **kw):
        """Background thinking (learning facts, news briefs, upgrades): use a free cloud brain when online,
        the offline brain only as a last resort - so it doesn't have to stay loaded in memory."""
        order = []
        if online():
            # background jobs go to the brains Saud's live chat needs least, so they don't eat its free limits
            order = [b for b in ("nvidia", "mistral", "openrouter", "cerebras", "groq", "gemini", "gpt") if has_key(b)]
        if not online() or local_running():
            order.append("local")      # background jobs never LOAD the big offline brain while online
        err = None
        for b in order:
            if b != "local" and not healthy(b):
                continue
            try:
                client, model, _ = client_for(b)
                kw2 = dict(kw, model=model)
                return client.chat.completions.create(**kw2)
            except Exception as e:
                err = e
                mark_fail(b, e)
                if b != "local" and ("404" in str(e) or "not found" in str(e).lower()):
                    refresh_model(b)
        raise err or RuntimeError("no brain available")


class _Chat:
    completions = _Completions()


class SmartLLM:
    """Drop-in for OpenAI(...) used by the learner, news reader and upgrader."""
    chat = _Chat()
