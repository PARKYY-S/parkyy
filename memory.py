"""
PARKYY's memory layer - local, offline, and shared with USB PARKYY.

Format (identical on laptop and USB, so they can sync):
  memory/memory.txt     one fact per line
  memory/forgotten.txt  one fact per line - facts deleted on either side,
                        so a sync never brings them back

Sync rule: union of both sides' facts, minus anything in either side's
forgotten list. It runs when PARKYY starts and after every change, whenever
the USB stick (any drive with PARKYY-USB\\parkyy.ps1) is plugged in.
The USB edition runs the same rule from its side.
"""

import os
import re
import string
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL_DIR = HERE / "memory"
USB_FOLDER = "PARKYY-USB"
MAX_FACTS_IN_PROMPT = 40
STOP = {"the", "and", "for", "you", "are", "what", "that", "this", "with", "have", "can",
        "how", "his", "her", "was", "saud", "parkyy", "about", "please", "tell", "does", "did"}

REMEMBER_RE = re.compile(r"^\s*(?:please\s+)?remember(?:\s+that)?\s+(.+?)\s*[.!]?\s*$", re.I)
FORGET_RE = re.compile(r"^\s*(?:please\s+)?forget(?:\s+that)?\s+(.+?)\s*[.!]?\s*$", re.I)


def _read(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _write(path: Path, lines: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Windows PowerShell 5.1 on the USB reads it correctly
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8-sig")


def _unique(lines: list[str]) -> list[str]:
    seen, out = set(), []
    for line in lines:
        key = line.casefold()
        if key not in seen:
            seen.add(key)
            out.append(line)
    return out


def find_usb_memory_dir() -> Path | None:
    """Return <drive>:\\PARKYY-USB\\memory if the stick is plugged in."""
    if os.name != "nt":
        return None
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\") / USB_FOLDER
        try:
            if (root / "parkyy.ps1").exists():
                return root / "memory"
        except OSError:
            continue
    return None


# ---------------------------------------------------------------- memory quality (importance, expiry, history)
import json as _json
import time as _time

TEMP_WORDS = re.compile(r"\b(today|tonight|yesterday|this morning|right now|currently|at the moment|tired|sleepy|"
                        r"hungry|bored|busy today|this week)\b", re.I)
HIGH_WORDS = re.compile(r"\b(deadline|birthday|anniversary|allerg|password manager|always|never|prefer|goal|"
                        r"job|interview|project|lives? in|works? at|name is|important)\b", re.I)
SUBJECT_RE = re.compile(r"^(.{4,80}?)\s+(?:is|are|was|=|changed to|moved to|will be|becomes)\s+(.+)$", re.I)


def _meta_for(fact: str, source: str = "user") -> dict:
    imp = "high" if HIGH_WORDS.search(fact) else "low" if TEMP_WORDS.search(fact) else "medium"
    return {"importance": imp, "source": source, "added": _time.strftime("%Y-%m-%d"),
            "expires": (_time.strftime("%Y-%m-%d", _time.localtime(_time.time() + 7 * 86400)) if imp == "low" else ""),
            "last_used": ""}


class Memory:
    def __init__(self, local_dir: Path = LOCAL_DIR):
        self.dir = Path(local_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.sync()
        try:
            self.prune_expired()
        except Exception:
            pass

    # ---- storage ----
    @property
    def facts(self) -> list[str]:
        return _read(self.dir / "memory.txt")

    @property
    def forgotten(self) -> list[str]:
        return _read(self.dir / "forgotten.txt")

    # ---- quality metadata + temporal history ----
    def _meta(self) -> dict:
        try:
            return _json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_meta(self, meta: dict):
        (self.dir / "meta.json").write_text(_json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    def history(self, query: str = "") -> list[dict]:
        out = []
        try:
            for line in (self.dir / "history.jsonl").read_text(encoding="utf-8").splitlines():
                r = _json.loads(line)
                if not query or query.casefold() in (r["old"] + " " + r["new"]).casefold():
                    out.append(r)
        except OSError:
            pass
        return out

    def prune_expired(self) -> list[str]:
        """Low-importance, temporary facts ("I'm tired today") fade after a week, so memory doesn't bloat."""
        meta, today = self._meta(), _time.strftime("%Y-%m-%d")
        gone = [f for f in self.facts if meta.get(f, {}).get("expires") and meta[f]["expires"] < today]
        if gone:
            _write(self.dir / "memory.txt", [f for f in self.facts if f not in gone])
            self._retire(gone)            # so a sync with the USB stick can't bring them back
            for f in gone:
                meta.pop(f, None)
            self._save_meta(meta)
            self.sync()
        return gone

    def _retire(self, facts: list[str]):
        """Record facts that were removed (replaced or expired) in forgotten.txt, like forget() does.
        Without this, sync() would merge them back from the USB copy of memory.txt."""
        if facts:
            _write(self.dir / "forgotten.txt", _unique(self.forgotten + list(facts)))

    def add(self, fact: str, source: str = "user") -> None:
        fact = fact.strip()
        if not fact:
            return
        # same subject with a new value? keep the old one in history instead of silently overwriting
        m = SUBJECT_RE.match(fact)
        replaced = []
        if m:
            subj = m.group(1).casefold().strip()
            for old in self.facts:
                om = SUBJECT_RE.match(old)
                if om and om.group(1).casefold().strip() == subj and old.casefold() != fact.casefold():
                    with open(self.dir / "history.jsonl", "a", encoding="utf-8") as fh:
                        fh.write(_json.dumps({"date": _time.strftime("%Y-%m-%d %H:%M"), "subject": m.group(1),
                                              "old": old, "new": fact}, ensure_ascii=False) + "\n")
                    _write(self.dir / "memory.txt", [f for f in self.facts if f != old])
                    replaced.append(old)
        self._retire(replaced)            # the old value must not come back from the USB copy
        meta = self._meta()
        meta.setdefault(fact, _meta_for(fact, source))
        self._save_meta(meta)
        _write(self.dir / "memory.txt", _unique(self.facts + [fact]))
        # re-remembering something un-forgets it
        _write(self.dir / "forgotten.txt",
               [f for f in self.forgotten if f.casefold() != fact.casefold()])
        self.sync()

    def forget(self, text: str) -> list[str]:
        """Forget every fact containing `text`. Returns what was removed."""
        needle = text.strip().casefold()
        removed = [f for f in self.facts if needle and needle in f.casefold()]
        if removed:
            _write(self.dir / "memory.txt", [f for f in self.facts if f not in removed])
            _write(self.dir / "forgotten.txt", _unique(self.forgotten + removed))
            self.sync()
        return removed

    # ---- sync with the USB stick ----
    def sync(self) -> bool:
        usb = find_usb_memory_dir()
        if usb is None:
            return False
        try:
            gone = _unique(self.forgotten + _read(usb / "forgotten.txt"))
            gone_keys = {g.casefold() for g in gone}
            merged = [f for f in _unique(self.facts + _read(usb / "memory.txt"))
                      if f.casefold() not in gone_keys]
            for d in (self.dir, usb):
                _write(d / "memory.txt", merged)
                _write(d / "forgotten.txt", gone)
            # PARKYY's diary: keep every line from both sides
            lap_d, usb_d = self.dir / "diary.txt", usb / "diary.txt"
            diary = _unique(_read(lap_d) + _read(usb_d))
            if diary:
                for d in (lap_d, usb_d):
                    _write(d, diary)
            # the "About Saud" profile: newest copy wins
            lap_p, usb_p = HERE / "about-saud.md", usb.parent / "about-saud.md"
            if lap_p.exists() and (not usb_p.exists() or lap_p.stat().st_mtime > usb_p.stat().st_mtime + 2):
                usb_p.write_bytes(lap_p.read_bytes())
            elif usb_p.exists() and (not lap_p.exists() or usb_p.stat().st_mtime > lap_p.stat().st_mtime + 2):
                lap_p.write_bytes(usb_p.read_bytes())
            return True
        except OSError:
            return False  # stick pulled out mid-sync, read-only, etc.

    # ---- used by agent.py ----
    def relevant_context(self, query: str, limit: int = MAX_FACTS_IN_PROMPT) -> str:
        """The newest facts, plus the older facts that share words with the question."""
        facts = self.facts
        if not facts:
            return ""
        if len(facts) > limit:
            words = {w for w in re.findall(r"[a-z0-9]{3,}", query.casefold())} - STOP
            recent = facts[-15:]
            older = facts[:-15]
            scored = sorted(older, key=lambda f: -len(words & set(re.findall(r"[a-z0-9]{3,}", f.casefold()))))
            picked = [f for f in scored[: limit - 15]
                      if words & set(re.findall(r"[a-z0-9]{3,}", f.casefold()))]
            facts = [f for f in older if f in picked] + recent
        return "Things you know about Saud:\n" + "\n".join(f"- {f}" for f in facts)

    def handle_command(self, user_message: str) -> str | None:
        """'remember that X' / 'forget X' are handled directly, no model needed."""
        m = REMEMBER_RE.match(user_message)
        if m:
            self.add(m.group(1))
            return f"Got it - I'll remember: {m.group(1)}"
        m = FORGET_RE.match(user_message)
        if m:
            removed = self.forget(m.group(1))
            if removed:
                return "Forgotten: " + "; ".join(removed)
            return f"I don't have anything saved about '{m.group(1)}'."
        return None

    def remember(self, user_message: str, assistant_message: str):
        """Kept for agent.py compatibility; saving is explicit via handle_command."""
        return None
