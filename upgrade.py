"""
PARKYY upgrades itself (step 3c) - always with Saud's yes first.

Learning is not enough: what PARKYY learns has to become part of it.
Once a week (and whenever Saud says "upgrade yourself") PARKYY:

  1. INSIGHTS - automatic, no question needed.
     Reads its week of news briefs + diary and writes knowledge/insights.md:
     "what I know now that matters for Saud". This goes into PARKYY's own
     instructions for every chat, so new knowledge changes how it thinks.

  2. NEW BRAIN - asks first.
     Looks at the newest free local AI models on Hugging Face, checks which
     ones fit this laptop's memory, and asks: "Want me to upgrade my brain
     to X?" On yes it downloads it with LM Studio and switches, keeping the
     old brain so "go back to your old brain" undoes it.

  3. NEW SKILLS - asks first.
     From what Saud does a lot + what's new in the world, it designs a new
     skill (a named routine like "Interview prep") and asks to add it.
     Approved skills appear as buttons and PARKYY follows them in chat.

  4. UPGRADE IDEAS - asks first.
     Ideas for new features for its own program (e.g. "add GitHub trending
     to my news"). Approved ideas go to knowledge/upgrade-ideas.md for Saud
     (and Claude) to build. PARKYY never rewrites its own code by itself -
     that keeps it from breaking or doing something unsafe.

Every question waits in knowledge/proposals.json until Saud answers.
"""

import ctypes
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

AST = timezone(timedelta(hours=3))
HERE = Path(__file__).resolve().parent
KDIR = HERE / "knowledge"
PROPOSALS = KDIR / "proposals.json"
INSIGHTS = KDIR / "insights.md"
IDEAS = KDIR / "upgrade-ideas.md"
SKILLS = HERE / "skills"
BRAIN = HERE / "brain.json"
LOG = KDIR / "upgrade-log.txt"
LMS = Path.home() / ".lmstudio" / "bin" / ("lms.exe" if os.name == "nt" else "lms")
UA = "Mozilla/5.0 PARKYY/0.1 (personal assistant)"
DEFAULT_MODEL = "hermes-2-pro-llama-3-8b"

GOOD_FAMILIES = re.compile(r"qwen|llama|mistral|gemma|phi|hermes|granite|deepseek|olmo|smollm|glm", re.I)
SKIP = re.compile(r"vl\b|vision|embed|rerank|guard|base\b|-base|reward|tts|whisper|ocr|draft|abliterat|uncensor", re.I)

INSIGHT_PROMPT = """You are PARKYY. Below are your diary and the news briefs you wrote this week. \
Write your updated "what I know now" notes for helping Saud: max 150 words, bullet points, \
only things that stay useful for weeks (big AI/tech shifts, tools worth using, job-market \
signals for Saudi Arabia/India, things about Saud's projects). Information only."""

SKILL_PROMPT = """You are PARKYY, Saud's AI. Based on what Saud has been doing (diary) and what \
is new in the world (insights), design ONE new skill that would genuinely help him and that \
isn't in EXISTING SKILLS. A skill is a named routine you follow in chat. Answer JSON only:
{"name": "2-4 words", "why": "one cute sentence", "steps": "what you do, max 80 words"}"""

IDEA_PROMPT = """You are PARKYY, an AI assistant program (Python backend, Electron desktop, \
local LLM, news reader, memory). From the insights below, suggest ONE concrete feature to add \
to your own program that would make you more useful for Saud. Not already in EXISTING IDEAS. \
Answer JSON only: {"title": "short", "why": "one sentence", "how": "max 50 words"}"""


def _now():
    return datetime.now(AST)


def _json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def _log(msg):
    KDIR.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{_now():%Y-%m-%d %H:%M} {msg}\n")


# ---------- which brain am I using? ----------
def current_model() -> str:
    try:
        return json.loads(BRAIN.read_text(encoding="utf-8")).get("model") or DEFAULT_MODEL
    except (OSError, json.JSONDecodeError):
        return os.environ.get("LOCAL_MODEL", DEFAULT_MODEL)


def _set_brain(model: str, previous: str | None):
    BRAIN.write_text(json.dumps({"model": model, "previous": previous,
                                 "since": f"{_now():%Y-%m-%d}"}, indent=2), encoding="utf-8")


# ---------- how much memory does this laptop have? ----------
def hardware() -> dict:
    ram = 0.0
    if os.name == "nt":
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        s = MS(); s.dwLength = ctypes.sizeof(MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            ram = s.ullTotalPhys / 1024 ** 3
    vram = 0.0
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        vram = max(float(x) for x in out.split()) / 1024 if out.strip() else 0.0
    except Exception:
        pass
    # a Q4 model needs about 0.62 GB per billion parameters + ~1.5 GB for chat memory
    budget = max(vram, ram * 0.45) - 1.5
    return {"ram_gb": round(ram, 1), "vram_gb": round(vram, 1), "max_params_b": max(0.0, round(budget / 0.62, 1))}


class Upgrader:
    def __init__(self, llm, memory, learner, world):
        self.llm, self.memory, self.learner, self.world = llm, memory, learner, world
        KDIR.mkdir(exist_ok=True)
        SKILLS.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self._notes: list[str] = []
        self._notes_lock = threading.Lock()

    # ---------- proposals (questions for Saud) ----------
    def proposals(self) -> list[dict]:
        try:
            return json.loads(PROPOSALS.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def _save(self, props):
        PROPOSALS.write_text(json.dumps(props, indent=2, ensure_ascii=False), encoding="utf-8")

    def pending(self) -> list[dict]:
        return [p for p in self.proposals() if p["status"] == "pending"]

    def _propose(self, kind, title, why, data):
        props = self.proposals()
        if any(p["kind"] == kind and p["title"].casefold() == title.casefold() for p in props):
            return  # already asked (answered or not) - never nag
        props.append({"id": f"{kind}-{len(props) + 1}", "kind": kind, "title": title, "why": why,
                      "data": data, "status": "pending", "date": f"{_now():%Y-%m-%d}"})
        self._save(props)

    def answer(self, pid: str, yes: bool) -> str:
        props = self.proposals()
        p = next((x for x in props if x["id"] == pid and x["status"] == "pending"), None)
        if not p:
            return "That question was already answered."
        p["status"] = "yes" if yes else "no"
        self._save(props)
        _log(f"{p['kind']} '{p['title']}': {'YES' if yes else 'no'}")
        if not yes:
            return f"Okay, skipping “{p['title']}”."
        if p["kind"] == "brain":
            threading.Thread(target=self._install_brain, args=(p["data"]["repo"],), daemon=True).start()
            return (f"Ooh, new brain! Downloading {p['title']} now - that can take a while. "
                    "I'll switch when it's ready and keep my old brain just in case.")
        if p["kind"] == "skill":
            self._add_skill(p["title"], p["data"].get("steps", ""))
            return f"New skill unlocked: {p['title']}! You'll see its button."
        if p["kind"] == "idea":
            with IDEAS.open("a", encoding="utf-8") as f:
                f.write(f"\n## {p['title']}  (approved {p['date']})\n{p['why']}\nHow: {p['data'].get('how', '')}\n")
            return f"Added “{p['title']}” to my upgrade list. Ask Claude to build it with you anytime!"
        return "Done."

    # ---------- 1. insights: knowledge becomes part of PARKYY ----------
    def make_insights(self):
        briefs = sorted((KDIR / "briefs").glob("*.md"))[-7:] if (KDIR / "briefs").exists() else []
        text = "\n\n".join(b.read_text(encoding="utf-8")[:1500] for b in briefs)
        diary = "\n".join(self.learner.diary()[-7:])
        old = INSIGHTS.read_text(encoding="utf-8") if INSIGHTS.exists() else ""
        if not text and not diary:
            return
        out = self.llm.chat.completions.create(
            model=current_model(), max_tokens=350, temperature=0.3,
            messages=[{"role": "system", "content": INSIGHT_PROMPT},
                      {"role": "user", "content": f"LAST WEEK'S NOTES:\n{old}\n\nDIARY:\n{diary}\n\nBRIEFS:\n{text}"}],
        ).choices[0].message.content
        if out and out.strip():
            INSIGHTS.write_text(f"# What PARKYY knows now (updated {_now():%d %b %Y})\n\n{out.strip()}\n", encoding="utf-8")
            _log("insights updated")

    def insights_text(self) -> str:
        if INSIGHTS.exists():
            return "Your own up-to-date knowledge (from your reading):\n" + INSIGHTS.read_text(encoding="utf-8")[:1500]
        return ""

    # ---------- 2. new brain ----------
    def check_brain(self):
        hw = hardware()
        cur = current_model().casefold()
        url = "https://huggingface.co/api/models?search=GGUF&sort=trendingScore&direction=-1&limit=60"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            models = json.loads(r.read())
        for m in models:
            repo = m.get("id", "")
            name = repo.split("/")[-1]
            size = re.search(r"(\d+(?:\.\d+)?)\s*[bB](?![a-z])", name)
            if not size or not GOOD_FAMILIES.search(name) or SKIP.search(name):
                continue
            params = float(size.group(1))
            if params < 3 or params > hw["max_params_b"]:
                continue
            base = re.sub(r"[-_.]?gguf", "", name, flags=re.I).casefold()
            if base in cur or cur in base:
                continue
            self._propose("brain", name,
                          f"It's one of the most popular new free brains this week and fits your laptop "
                          f"({params:g}B; you have {hw['ram_gb']} GB RAM"
                          + (f", {hw['vram_gb']} GB GPU" if hw["vram_gb"] else "") + "). "
                          "Newer isn't always better at everything, so I'll keep my old brain as backup.",
                          {"repo": repo, "params_b": params})
            return

    def _lms(self, *args, timeout=3600):
        return subprocess.run([str(LMS), *args], capture_output=True, text=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _install_brain(self, repo: str):
        with self.lock:
            try:
                if not LMS.exists():
                    raise RuntimeError("LM Studio's lms tool not found")
                r = self._lms("get", f"https://huggingface.co/{repo}", "-y")
                _log(f"lms get {repo}: exit {r.returncode} {r.stdout[-300:]} {r.stderr[-300:]}")
                ls = self._lms("ls", "--json", timeout=60)
                key = None
                stem = repo.split("/")[-1].casefold().replace("-gguf", "")
                for m in json.loads(ls.stdout or "[]"):
                    k = m.get("modelKey") or m.get("path") or ""
                    if stem[:12] in k.casefold() or stem[:12] in (m.get("path") or "").casefold():
                        key = m.get("modelKey") or k
                if not key:
                    raise RuntimeError("download didn't show up in LM Studio")
                old = current_model()
                self._lms("unload", "--all", timeout=120)
                ld = self._lms("load", key, "-y", timeout=900)
                if ld.returncode != 0:
                    self._lms("load", old, "-y", timeout=900)
                    raise RuntimeError("new brain wouldn't load: " + (ld.stderr or ld.stdout)[-200:])
                _set_brain(key, old)
                self._notify(f"🧠 Brain upgraded to {key}! Say “go back to your old brain” if I get worse.")
            except Exception as e:
                _log(f"brain upgrade failed: {e}")
                self._notify(f"My brain upgrade didn't work ({e}). I'm still on my old brain - you can "
                             f"download {repo} in LM Studio yourself and tell me.")

    def revert_brain(self) -> str:
        try:
            info = json.loads(BRAIN.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "I'm already on my original brain."
        prev = info.get("previous")
        if not prev:
            return "I don't have an older brain saved."
        def go():
            with self.lock:
                self._lms("unload", "--all", timeout=120)
                self._lms("load", prev, "-y", timeout=900)
                _set_brain(prev, info.get("model"))
                self._notify(f"Back on my old brain ({prev}).")
        threading.Thread(target=go, daemon=True).start()
        return f"Okay, switching back to {prev}… give me a minute."

    # ---------- 3. skills ----------
    def skills(self) -> list[dict]:
        out = []
        for f in sorted(SKILLS.glob("*.md")):
            lines = f.read_text(encoding="utf-8").splitlines()
            out.append({"name": lines[0].lstrip("# ").strip() if lines else f.stem,
                        "steps": " ".join(lines[1:]).strip()})
        return out

    def _add_skill(self, name, steps):
        safe = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:40] or "skill"
        (SKILLS / f"{safe}.md").write_text(f"# {name}\n{steps}\n", encoding="utf-8")

    def skills_text(self) -> str:
        sk = self.skills()
        if not sk:
            return ""
        return "Skills you have learned (when Saud asks for one by name, follow its steps):\n" + "\n".join(
            f"- {s['name']}: {s['steps'][:300]}" for s in sk)

    def suggest_skill(self):
        existing = [s["name"] for s in self.skills()] + [p["title"] for p in self.proposals() if p["kind"] == "skill"]
        out = self.llm.chat.completions.create(
            model=current_model(), max_tokens=200, temperature=0.7,
            messages=[{"role": "system", "content": SKILL_PROMPT},
                      {"role": "user", "content": "EXISTING SKILLS: " + (", ".join(existing) or "Write email, Plan my day, "
                       "Gadget R&D, Build a website, Summarise a file") + "\n\nDIARY:\n" + "\n".join(self.learner.diary()[-10:])
                       + "\n\nINSIGHTS:\n" + (INSIGHTS.read_text(encoding="utf-8") if INSIGHTS.exists() else "")}],
        ).choices[0].message.content
        j = _json(out)
        if j and j.get("name") and j.get("steps"):
            self._propose("skill", str(j["name"])[:40], str(j.get("why", ""))[:200], {"steps": str(j["steps"])[:600]})

    # ---------- 4. ideas for its own program ----------
    def suggest_idea(self):
        if not INSIGHTS.exists():
            return
        existing = [p["title"] for p in self.proposals() if p["kind"] == "idea"]
        out = self.llm.chat.completions.create(
            model=current_model(), max_tokens=200, temperature=0.7,
            messages=[{"role": "system", "content": IDEA_PROMPT},
                      {"role": "user", "content": "EXISTING IDEAS: " + (", ".join(existing) or "none")
                       + "\n\nINSIGHTS:\n" + INSIGHTS.read_text(encoding="utf-8")}],
        ).choices[0].message.content
        j = _json(out)
        if j and j.get("title"):
            self._propose("idea", str(j["title"])[:60], str(j.get("why", ""))[:200], {"how": str(j.get("how", ""))[:400]})

    # ---------- running it ----------
    def _notify(self, text):
        with self._notes_lock:
            self._notes.append(text)

    def take_notes(self) -> list[str]:
        with self._notes_lock:
            out, self._notes = self._notes, []
        return out

    def weekly(self, force=False):
        stamp = KDIR / "last-upgrade-check.txt"
        last = stamp.read_text().strip() if stamp.exists() else ""
        if not force and last and last > f"{_now() - timedelta(days=7):%Y-%m-%d}":
            return
        stamp.write_text(f"{_now():%Y-%m-%d}")
        for step in (self.make_insights, self.check_brain, self.suggest_skill, self.suggest_idea):
            with self.lock:
                try:
                    step()
                except Exception as e:
                    _log(f"{step.__name__} failed: {type(e).__name__} {e}")

    def upgrade_now(self) -> str:
        threading.Thread(target=self.weekly, kwargs={"force": True}, daemon=True).start()
        return ("Ooh, upgrade time! I'm reviewing what I've learned, checking for a better brain, and "
                "thinking up new skills. I'll ask you before changing anything.")
