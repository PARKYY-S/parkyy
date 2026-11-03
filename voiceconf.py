"""
How PARKYY knows you're talking to it.

You don't have to say "Hey PARKYY" every time. Two things make it natural:

1. NICKNAMES - it wakes to any name/phrase in voice-config.json, not just
   "parkyy". Defaults include buddy, bud, hey buddy, yo parkyy, etc. You can
   add your own just by telling PARKYY: "call yourself champ" / "add wake
   word yo bestie". Edit voice-config.json directly too.

2. CONVERSATION MODE - once you've woken it, you can keep talking for a
   while (default 25s, rolling) WITHOUT a wake word. So:
     You: "Hey buddy, what's up? Pull up the her-world project."
     PARKYY: (answers)
     You: "cool, now add a new page"        <- no wake word needed
   It goes back to sleep after a quiet gap.

Wake matching is fuzzy, so small mispronunciations still land.
"""

import difflib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONF = HERE / "voice-config.json"

DEFAULTS = {
    "wake_words": ["parkyy", "parky", "hey parkyy", "hey parky", "okay parkyy", "ok parkyy",
                   "buddy", "bud", "hey buddy", "yo parkyy", "yo buddy", "hey pookie"],
    "conversation_seconds": 25,   # keep listening this long after you speak, no wake word needed
    "unlock_phrase": "",          # set to require a secret phrase for voice unlock
}


def load() -> dict:
    try:
        d = json.loads(CONF.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in d.items() if v not in (None, "")})
    out["wake_words"] = [w.strip().lower() for w in out.get("wake_words", []) if str(w).strip()] or DEFAULTS["wake_words"]
    return out


def save(d: dict):
    CONF.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def add_wake_word(phrase: str) -> str:
    phrase = re.sub(r"\s+", " ", (phrase or "").strip().lower()).strip(" .!,")
    if not phrase or len(phrase) > 30:
        return "Tell me a short name to answer to, like “call yourself champ”."
    d = load()
    words = d.get("wake_words", list(DEFAULTS["wake_words"]))
    if phrase in words:
        return f"I already answer to “{phrase}”. 🎀"
    words.append(phrase)
    d["wake_words"] = words
    save(d)
    return f"Yay! I'll answer to “{phrase}” now too. Say it and I'll wake up."


def wake_match(text: str, wake_words: list[str]) -> tuple[bool, str]:
    """Did the text address PARKYY? Returns (yes, whatever was said after the name)."""
    t = " " + re.sub(r"[^\w ]+", " ", text.lower()) + " "
    t = re.sub(r"\s+", " ", t)
    # direct substring hit (longest names first, so "hey parkyy" beats "parkyy")
    for w in sorted(wake_words, key=len, reverse=True):
        pat = " " + w + " "
        i = t.find(pat)
        if i != -1:
            after = t[i + len(pat):].strip(" ,.")
            return True, after
        if t.strip().startswith(w):
            return True, t.strip()[len(w):].strip(" ,.")
    # how the offline ears often mishear "hey PARKYY": "hi patty", "a party", "hey porky", "he barky"...
    m = re.search(r"^ ?(?:hey|hi|hay|a|he|ok|okay|yo) (?:p|b)(?:a|o|e|u)(?:r|rr)?(?:k|t|tt|d)(?:y|ie|i|ey|ee)( .*)?$", t.rstrip())
    if m:
        return True, (m.group(1) or "").strip(" ,.")
    if any(" parky " in t or " party " == t or f" {x} " in t for x in ("patty", "parky", "parkey", "parkie", "porky", "perky", "barky")):
        for x in ("patty", "parky", "parkey", "parkie", "porky", "perky", "barky", "party"):
            i = t.find(f" {x} ")
            if i != -1 and (x != "party" or t.strip() == "party"):
                return True, t[i + len(x) + 2:].strip(" ,.")
    # fuzzy: any single spoken word close to a one-word wake name (buddy/parkyy/parky)
    tokens = t.split()
    singles = [w for w in wake_words if " " not in w]
    for idx, tok in enumerate(tokens):
        for w in singles:
            if difflib.SequenceMatcher(None, tok, w).ratio() >= 0.82:
                return True, " ".join(tokens[idx + 1:]).strip(" ,.")
    return False, ""


def can_unlock(text: str) -> bool:
    phrase = load().get("unlock_phrase", "").strip().lower()
    return True if not phrase else (phrase in text.lower())


ADD_RE = re.compile(r"^\s*(?:please\s+)?(?:call\s+your\s?self|call\s+you|answer\s+to|"
                    r"add\s+(?:a\s+)?wake\s*word|wake\s*word|your\s+nickname\s+is)\s+(.+?)\s*[.!]?\s*$", re.I)


def handle_command(msg: str):
    m = ADD_RE.match(msg or "")
    if m:
        return add_wake_word(m.group(1))
    return None
