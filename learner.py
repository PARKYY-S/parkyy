"""
PARKYY learns on its own (step 3 of the build).

1. After every chat, PARKYY quietly asks its own brain: "did Saud just tell
   me anything worth remembering for the long run?" New facts go into
   memory/memory.txt (the same file "remember that ..." uses, so they sync to
   the USB stick too). PARKYY tells Saud what it learned, and "forget ..."
   removes anything he doesn't want kept.

2. Every conversation is written to a daily journal:
   memory/journal/2026-09-27.md

3. Reflection: the first time PARKYY runs on a new day, it reads the
   journals of earlier days it hasn't reflected on yet and writes a short
   diary line for each ("27 Sep 2026: ...") into memory/diary.txt. The last
   few diary lines are part of what PARKYY knows in every chat, so it
   remembers what you've been up to lately.

Everything runs on the local brain (LM Studio) - free and offline.
Turn auto-learning off with PARKYY_AUTOLEARN=0 in .env.
"""

import difflib
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from upgrade import current_model

AST = timezone(timedelta(hours=3))
HERE = Path(__file__).resolve().parent
PROFILE_FILE = HERE / "about-saud.md"

MAX_NEW_FACTS = 3          # per chat turn, keeps junk out
SIMILAR = 0.82             # "same fact" threshold for de-duplication
DIARY_IN_PROMPT = 5        # how many recent diary lines PARKYY always knows

EXTRACT_PROMPT = """You are PARKYY's memory. Read the latest exchange between Saud and PARKYY \
and pull out NEW long-term facts about Saud's life that PARKYY should remember for weeks or \
months: people in his life, plans, goals, preferences, projects, deadlines, decisions, \
important dates, likes and dislikes.

Rules:
- Only facts Saud himself said or clearly confirmed. Nothing PARKYY said or suggested.
- Skip small talk, questions, one-off requests, and anything already in KNOWN FACTS.
- Skip passwords, bank or card numbers, ID numbers, and health details.
- Each fact is one short sentence starting with "Saud" or a person's name, e.g.
  "Saud has an interview with Aramco on 3 October."
- At most {max} facts. If there is nothing new, return an empty list.

Answer with JSON only, like: {{"facts": ["...", "..."]}}"""

REFLECT_PROMPT = """You are PARKYY, Saud's cute personal AI. Below is the journal of your chats \
with Saud on {day}. Write ONE diary line (max 40 words) summarising what Saud worked on, \
decided, or felt that day and anything to follow up on. Plain text, no quotes, no date."""


def _now():
    return datetime.now(AST)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().strip("-• ").strip()


def _similar(a: str, b: str) -> bool:
    a, b = a.casefold(), b.casefold()
    return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR


def _parse_facts(text: str) -> list[str]:
    """Small local models sometimes wrap JSON in prose - dig it out."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            facts = json.loads(m.group(0)).get("facts", [])
            return [_clean(str(f)) for f in facts if isinstance(f, (str, int, float))]
        except (json.JSONDecodeError, AttributeError):
            pass
    m = re.search(r"\[.*\]", text or "", re.S)
    if m:
        try:
            return [_clean(str(f)) for f in json.loads(m.group(0))]
        except json.JSONDecodeError:
            pass
    return []


BLOCK = re.compile(r"password|passcode|pin\b|otp|cvv|card number|iban|account number|"
                   r"iqama|passport no|api key|\bsk_[a-z0-9]", re.I)


class Learner:
    def __init__(self, llm, model: str, memory):
        self.llm, self.model, self.memory = llm, model, memory
        self.dir = memory.dir
        self.journal_dir = self.dir / "journal"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.diary_file = self.dir / "diary.txt"
        self.enabled = os.environ.get("PARKYY_AUTOLEARN", "1") != "0"
        self.lock = threading.Lock()          # one background brain job at a time
        self._new: list[str] = []             # learned facts not yet shown to Saud
        self._new_lock = threading.Lock()

    # ---------- journal ----------
    def log(self, user: str, reply: str):
        now = _now()
        path = self.journal_dir / f"{now:%Y-%m-%d}.md"
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n[{now:%H:%M}] Saud: {user.strip()}\n[{now:%H:%M}] PARKYY: {reply.strip()}\n")

    # ---------- diary (reflection) ----------
    def diary(self) -> list[str]:
        if not self.diary_file.exists():
            return []
        return [l.strip() for l in self.diary_file.read_text(encoding="utf-8-sig").splitlines() if l.strip()]

    def recent_diary(self) -> str:
        lines = self.diary()[-DIARY_IN_PROMPT:]
        return ("Your diary of recent days with Saud:\n" + "\n".join(f"- {l}" for l in lines)) if lines else ""

    def reflect_pending(self):
        """Write a diary line for every past day that has a journal but no diary line."""
        today = f"{_now():%Y-%m-%d}"
        done = {l.split(":")[0].strip() for l in self.diary()}
        for path in sorted(self.journal_dir.glob("*.md")):
            day = path.stem
            if day >= today:
                continue
            label = datetime.strptime(day, "%Y-%m-%d").strftime("%d %b %Y")
            if label in done:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")[-12000:]
            try:
                out = self.llm.chat.completions.create(
                    model=current_model(), max_tokens=120, temperature=0.4,
                    messages=[{"role": "system", "content": REFLECT_PROMPT.format(day=label)},
                              {"role": "user", "content": text}],
                ).choices[0].message.content
            except Exception:
                return  # brain not ready - try again next start
            line = _clean(out).strip('"')
            if line:
                with self.diary_file.open("a", encoding="utf-8") as f:
                    f.write(f"{label}: {line}\n")
                # also mine that whole day for facts missed in the moment
                self._extract(text[-6000:])

    def start_reflection(self):
        threading.Thread(target=self._locked, args=(self.reflect_pending,), daemon=True).start()

    # ---------- auto-learning ----------
    def after_chat(self, user: str, reply: str):
        """Called after every reply. Runs in the background so chat stays fast."""
        try:
            self.log(user, reply)
        except OSError:
            pass
        if self.enabled and len(user.split()) >= 4:   # "ok", "thanks" etc. teach nothing
            convo = f"Saud: {user}\nPARKYY: {reply}"
            threading.Thread(target=self._locked, args=(self._extract, convo), daemon=True).start()

    def _locked(self, fn, *args):
        with self.lock:
            try:
                fn(*args)
            except Exception:
                pass  # learning must never break chatting

    def _known(self) -> list[str]:
        known = list(self.memory.facts) + list(self.memory.forgotten)
        try:
            known += [l.strip("- ").strip() for l in PROFILE_FILE.read_text(encoding="utf-8-sig").splitlines()
                      if len(l.strip()) > 8 and not l.startswith("#")]
        except OSError:
            pass
        return known

    def _extract(self, convo: str):
        known = self._known()
        facts_block = "\n".join(f"- {k}" for k in self.memory.facts[-60:]) or "(none yet)"
        out = self.llm.chat.completions.create(
            model=current_model(), max_tokens=250, temperature=0.1,
            messages=[{"role": "system", "content": EXTRACT_PROMPT.format(max=MAX_NEW_FACTS)},
                      {"role": "user", "content": f"KNOWN FACTS:\n{facts_block}\n\nLATEST EXCHANGE:\n{convo}"}],
        ).choices[0].message.content
        added = []
        for fact in _parse_facts(out)[:MAX_NEW_FACTS]:
            if not (8 <= len(fact) <= 200) or BLOCK.search(fact):
                continue
            if any(_similar(fact, k) for k in known + added):
                continue
            added.append(fact)
        for fact in added:
            self.memory.add(fact, source="learned")
        if added:
            with self._new_lock:
                self._new += added

    def take_new(self) -> list[str]:
        """Facts learned since the last time the UI asked (shown as 'I learned...')."""
        with self._new_lock:
            out, self._new = self._new, []
        return out
