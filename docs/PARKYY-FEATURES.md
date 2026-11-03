# PARKYY: Features and Growth Potential

*3 Nov 2026 · Saud Parkar*

PARKYY is a personal AI assistant for Windows that cannot act without its owner's "Yes" and checks the real result of everything it does. Saud built it solo on a $0 budget, using free cloud AI models plus a local offline model. He directed AI coding assistants (Claude and ChatGPT) and did the testing and design decisions himself.

- Code: https://github.com/PARKYY-S/parkyy
- 1-minute demo: https://youtu.be/tKXz5s0G9vM
- Latest results (2-3 Nov 2026): self-test 21/21, own benchmark 19/20 (core 13/13, hidden tests 93%), USB edition 11/11 on real hardware

## Features

"Verified live" means tested on Saud's real laptop on 2-3 Nov 2026. "Built" means it works in the code but has no recorded end-to-end test yet.

| Area | Feature | Status |
| --- | --- | --- |
| Safety | Asks for a Yes before acting: every action has a risk level 0-4; risky ones need a Yes, the most critical can require a PIN | Verified live (asked before deleting a file; file untouched on disk) |
| Safety | Checks the real result (file on disk, note saved, calendar entry) instead of trusting what the AI says it did | Verified live (benchmark scores real results) |
| Safety | Never rewrites its own code unsupervised: it can propose an upgrade, test and benchmark it, then waits for approval | Built |
| Safety | Safety gate chain: permissions, safe/guest mode, privacy filter, mission guard, simulation (dry-run) mode, risk level, decision journal | Verified live (safety and simulation tests passed) |
| Safety | Works only on an approved drive ("D: only" rule) | Verified live (self-test) |
| AI brains | Router ("Cortex") that classifies each task (chat, reasoning, coding, research, vision, mission) and picks the best available AI model | Verified live |
| AI brains | Free providers: Groq, Gemini, OpenRouter, plus an offline local model (Hermes 8B) | Verified live (Groq, Gemini, offline) |
| AI brains | Automatic failover: when a provider fails, runs out of credit or hits a limit, it switches by itself, even mid-task | Verified live (finished its benchmark on one free provider) |
| AI brains | Learns a scoreboard of which model is good at what, and turns rate-limit messages into exact cooldowns | Built |
| Work | Gmail: read and summarise mail, draft emails (sending goes through the Yes gate) | Reading verified live; sending built |
| Work | Google Calendar: read the schedule, add events (through the Yes gate) | Reading verified live; adding built |
| Work | Multi-step "missions": splits a job into steps, asks for a Yes where needed, checks each step | Verified live (benchmark) |
| Work | Web research with sources | Verified live |
| Work | Reminders, to-dos, habits, goals | Verified live (self-test) |
| Work | Files: find the biggest files, plan a Downloads clean-up (moves nothing until approved) | Verified live (benchmark) |
| Work | Laptop health: "why is my laptop slow?", memory, disk and battery alerts | Verified live (benchmark) |
| Work | Connected apps: GitHub, Spotify, LG TV; makes web projects | Built (GitHub and Spotify pass the self-test) |
| Interface | Windows desktop app: see-through HUD, Ctrl+Space to summon, tray menu, lock screen | Verified live |
| Interface | "Hey PARKYY" voice wake word and spoken replies | Built |
| Interface | Hand-gesture control | Built |
| Interface | A robot character that walks along the top of open windows, flies, reads with glasses when a document is open, sleeps when the user is away, and shows replies in a speech bubble | Verified live |
| Interface | Grows up in real time (baby to adult) and levels up with XP as it is used | Verified live |
| Memory | Remembers facts across sessions, forgets on request | Verified live (memory test) |
| Portable | USB edition: runs from a USB stick on any Windows PC with no install, offline AI on the stick, free cloud AI when there's internet, falls back to offline by itself, syncs memory with the laptop, has its own desktop character | Verified live (11/11 checks) |
| Self-testing | 21-check self-test on every start; own benchmark with 13 core tests and 7 hidden tests regenerated every run | Verified live |
| Mobile | Android phone app: texting, PARKYY calling the phone, laptop-to-phone transfer | In progress |

## Proof

The benchmark was made harder on purpose in October. Scores dropped, the bugs it found were fixed, and the core suite is back to 13/13 with the hidden tests on top.

| Date | Test | Result |
| --- | --- | --- |
| 3 Nov 2026 | USB edition, run from a real USB stick on the laptop | 11/11: offline AI answered, cloud AI answered, web search, automatic fallback to offline, memory sync, desktop character |
| 2 Nov 2026 | Benchmark v1.2 (13 core + 7 hidden tests, 24 min) | 19/20 · core 13/13 · hidden 93% · Cognitive 100% · System 100% |
| 2 Nov 2026 | Live checks in the app: self-test, Gmail and Calendar (read-only), delete request | Self-test 21/21; Google answered from the real accounts; delete was held for a Yes and the file stayed |
| 7 Oct 2026 | Benchmark v1.2, first run | 15/20 · core dropped to 9/13 (found bugs, then fixed) |
| 6 Oct 2026 | Benchmark v1.1 | 13/13 · Cognitive 100% · System 100% |
| 3 Oct 2026 | Benchmark v1.0 baseline | 12/13 · Cognitive 80% · System 100% |

Full report and run history are in this repo (`docs/` and `data/bench_history.json`).

## Honest limits today

- Sending email and creating calendar events go through the Yes gate but have not had a recorded end-to-end test; reading both was tested live.
- Missions finish the real work, but on the hidden real-file test PARKYY did not tick every step (scored partial). A fix for how approvals resume a mission is in the code; its live re-test is pending.
- Offline AI is slow on a busy 16 GB laptop: about 4 minutes to load from the USB stick and several minutes per answer while other apps use the memory.
- Free AI tiers rate-limit: on 2 Nov only one free provider (Groq) stayed available to the end of the benchmark; PARKYY kept working through it.
- Windows only so far; the phone app is in progress.

## What's holding it back, and what would unlock it

PARKYY has a lot of room to grow. Three things limit it today:

- **The laptop:** an i5 with 16 GB RAM and no dedicated graphics card. Offline AI takes minutes per answer.
- **The AI brains:** free tiers rate-limit, and stronger models cost money.
- **Tools:** each new integration takes time to build and test alone.

Better hardware, AI or cloud credits, or working with a company team would remove these limits directly.

## Growth potential

PARKYY's core idea, an AI that asks before it acts and proves what it did, matters more as AI agents get access to real accounts and files. The near-term steps come from the project's own roadmap; the later ones are directions it could grow into. None of this is finished work.

Each phase builds on the one before: first prove every feature end to end, then make PARKYY smarter and available on more platforms, then turn its safety layer into something other teams can use.

- **Personal assistant:** a free, private assistant for students and job-seekers, and for anyone without a paid AI plan.
- **Safe-agent layer for companies:** the Yes gate, result checking and decision journal packaged so other AI agents can use them, with an audit trail of who approved what.
- **Private, offline AI:** the USB edition points to assistants for places with poor internet or strict privacy rules, where data must stay on the device.
- **Honest benchmarking:** hidden tests regenerated every run, scored on real results, is a method other agent builders can reuse.
