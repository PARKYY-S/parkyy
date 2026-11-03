# PARKYY

**A personal AI assistant that can't act without your "Yes" - and checks its own work.**
It runs free (cloud free tiers + a local model), keeps one memory across laptop and USB stick,
and lives on your desktop as a little robot that walks on your windows and flies.

<!-- ![PARKYY demo](docs/demo.gif) -->

**▶ 1-minute demo:** [watch on YouTube](https://youtu.be/tKXz5s0G9vM) · **Code:** https://github.com/PARKYY-S/parkyy

> Built solo by Saud, at $0 budget, with Claude and ChatGPT as pair-programmers.
> Inspired by JARVIS, not a copy of it.

---

## Why it's different from the usual "Jarvis" repos

Most voice-assistant repos stop at "it can send an email". PARKYY is built around the part that matters
if you ever let an AI touch your real computer: **trust.**

| | What PARKYY does |
|---|---|
| **Asks before acting** | Every action has a risk level (0-4). Anything risky needs your Yes; the most dangerous needs a PIN. |
| **Verifies, doesn't trust** | After a tool runs, PARKYY checks the *real result* (file exists, note saved), not what the model *says* it did. |
| **Never rewrites itself** | It can *propose* a change to its own code, test it and benchmark it - then waits for you to approve. |
| **Can't be stuck on one AI** | A router sends each task to the best available brain (Groq, Gemini, OpenRouter, a local Hermes 8B), learns a scoreboard of who is good at what, and fails over when a free limit runs out - even mid-mission. |
| **Works with no internet** | A portable USB edition runs a local model (Hermes 8B via llamafile) from the stick, switches to free cloud brains when there's internet, falls back to offline by itself when they fail, and syncs memory with the laptop. *Tested on a real Windows 11 laptop, 3 Nov 2026: 11/11 checks.* The offline brain is slow on a busy 16 GB laptop (minutes per answer). |
| **Has a personality** | The original PARKYY face grows from baby to adult over real time, levels up with XP, and roams your desktop. |

## How it thinks

```
voice / text / phone ──▶  Instant layer  (no AI needed: status, timers, memory, modes, self-test)
                              │
                              ▼
                        Cortex (router)  classify task → pick brain → fail over
                              │              Groq · Gemini · OpenRouter · local Hermes
                              ▼
                        Safety gate      permissions → privacy → mission guard → simulation
                              │              → risk level → your Yes / PIN → decision journal
                              ▼
                        Tools + missions  calendar, email, files, GitHub, Spotify, web …
                              │
                              ▼
                        Verify from system state  ──▶  Memory + learned scoreboard
```

- **Missions:** multi-step jobs are split into steps, each one confirmed and checked. If the AI forgets to
  tick a step, PARKYY ticks it from the tools that actually ran.
- **Rate limits are understood:** "try again in 9m3s" becomes an exact cooldown, a daily cap is labelled as one,
  and only the brain that failed rests.
- **Shared state:** a small `state.json` (what Saud is doing, the laptop's health, the current mission, brain
  health) is refreshed every minute and summarised for the brain.

## Measured, not claimed

PARKYY has its own benchmark (`tools/bench.py`): 13 core tests scored on **Cognitive** (reasoning, coding,
research, planning, missions) and **System** (safety, recovery, memory, tools, self-checks).

| Date | Suite | Result |
|---|---|---|
| 3 Oct 2026 | v1.0 baseline (13 tests) | Cognitive 80% · System 100% · 12/13 passed |
| 6 Oct 2026 | v1.1 (mission fix, timeouts, Gemini hand-off) | **Cognitive 100% · System 100% · 13/13 passed** |
| 7 Oct 2026 | v1.2 = 13 core + 7 **hidden tests generated fresh each run** | 15/20 · hidden challenge **93%** (reasoning, coding, planning, research 100%; real mission 50%) · core 9/13 |
| **2 Nov 2026** | **v1.2, build v0.9.26** | **19/20 · core 13/13 · hidden challenge 93% · Cognitive 100% · System 100%** |

Honest notes: the benchmark found real bugs (a frozen scan, a rejected hand-off between providers, a core
regression to 9/13 on the first v1.2 run) and each one was fixed and re-measured - the 2 Nov run is back to 13/13
with the harder hidden set on top. It finished on a single free brain (Groq) after the others were rate-limited,
so the failover was part of the test. The one non-pass is the hidden real-file mission (PARTIAL): PARKYY found the
right file and saved the note after a Yes, but didn't tick every mission step. The hidden tests use random names
and numbers with answers computed by Python, so PARKYY can't memorise them. Run history: `data/bench_history.json`.

A built-in self-test also runs at start-up: **21 of 21 checks pass** (2 Nov 2026), including the safety rules
(deleting and commands need a Yes, "D: drive only") and the Gmail & Calendar connection.

## What's in the box

- **Desktop app (Windows, Electron):** transparent HUD, `Ctrl+Space` to summon, "Hey PARKYY" voice input,
  spoken replies, tray icon. When idle, PARKYY walks along the top of your windows, flies around, wears glasses
  when you open a document, and sleeps when you're away.
- **Backend (FastAPI):** the brain router, safety gate, memory and tools. One server, many thin clients.
- **USB edition (`PARKYY-USB/`):** a portable PowerShell version with a local llamafile brain, `/web` search,
  free-tier cloud brains when online, and a little desktop pet. No install needed on the host PC.
- **Phone app (in progress):** texting, PARKYY calling you, laptop-to-phone transfer.

## Run it

```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env           # then add free keys: Groq, Gemini, OpenRouter
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Desktop app: `START-PARKYY.bat` (or `RESTART-PARKYY.bat` to reload it). No paid keys are needed -
PARKYY works with free brains and falls back to a local model.

USB edition: copy `PARKYY-USB/` to an exFAT stick, add a `llamafile` and a `.gguf` model,
double-click `start.bat`. See `PARKYY-USB/README.txt`.

## Roadmap (what is *not* done yet)

- Gmail / Google Calendar: the tools exist, but the connection currently fails its self-test and needs
  re-authorising and an end-to-end test. The USB edition can draft but not send.
- Fix the v1.2 core regression (9/13) and re-run.
- Phone app v0.8, watch-based mood tracking.
- Beliefs with evidence, a planner that re-plans after each step, reflection after each mission.

## Principles

1. No action without a Yes. 2. Check the result, not the claim. 3. Never edit yourself unsupervised.
4. Free first. 5. Say plainly what isn't done.

## License

Add one before publishing (MIT is a good default).
