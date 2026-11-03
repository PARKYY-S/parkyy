# PARKYY - project record (the source of truth, kept on D:)

Saved here so the history never depends on a chat again. Update it after each milestone.

## Rules Saud set
- Never write anything to C: - always D:.
- Every action needs Saud's Yes (risk levels 0-4, PIN for level 4).
- PARKYY never rewrites its own code: it proposes, tests and benchmarks, then Saud approves.
- Verify actions from system state and tool results, never from what a brain *says* it did.
- Benchmark: one clean run per change. Don't burn free quotas re-running it.

## Architecture (as of 3 Oct 2026)
- **Instant layer (no brain needed):** status, self-test, "why is my laptop slow", modes, timers, memory commands, benchmarks, Yes/No.
- **Shared state:** `data/state.json` - Saud's activity and goals, the laptop, the current mission, brain health, modes. Refreshed every minute; the brains get a short snapshot of it.
- **Cortex (`cortex.py`):**
  - Brain profiles (skill cards).
  - Task classifier: chat / reasoning / coding / research / vision / mission.
  - Learned scoreboard (`data/brain_scores.json`).
  - Capability router.
- **Brain identity = provider + endpoint + model.** Groq/gpt-oss-120b and NVIDIA/gpt-oss-120b count as different brains, and only the one that failed rests.
- **Rate limits are parsed into cooldowns:**
  - "try again in 9m3s" becomes exactly 9m3s.
  - A daily limit is labelled as one.
  - "No credit" means 6 hours.
- **Retired models:** PARKYY lists the provider's models, probes the candidates, and keeps one that actually answers.
- **Offline brain (Hermes):** used only with no internet, when it's already loaded, or when there's enough RAM.
- **Safety gate:** permissions, then safe/guest mode, then privacy, then the mission guard, then simulation, then risk level, then Yes/PIN, then the decision journal.
- **Missions:** if the brain skips creating a mission, PARKYY creates it itself and splits it into steps.

## Brains
| Brain | Status |
|---|---|
| Groq (gpt-oss-120b) | ✅ main workhorse; about 200k tokens a day free |
| Gemini Flash | ✅ daily free cap, sometimes overloaded |
| OpenRouter | ✅ key added; its free model is often busy |
| NVIDIA | ⚠️ key is valid, but none of its models answer (NVIDIA-side) |
| Claude | ❌ no credit |
| Mistral | ❌ free plan has no API access |
| Hermes 8B | offline backup |

## Benchmark method
- 13 tests.
- **Two scores:** Cognitive (reasoning, coding, research, planning, missions) and System (safety, recovery, memory, tools, self-checks).
- **Coverage:** the report shows which brains were available.
- If no brain is available, a test is marked SKIPPED, not FAIL.
- History is kept in `data/bench_history.json`.
- **Later:** hidden tests that change each run, real-task scores, and Saud's feedback, so PARKYY doesn't just learn to pass its own 13 tests.

## Benchmark suite v1.2 (built 6 Oct, first run 7 Oct)
- **Core regression:** the original 13 tests. They must stay 13/13.
- **Hidden challenge (7 tests), freshly generated every run** from a pool, with random numbers and names so it can't be memorised:
  - 2 reasoning (ordering, calendar maths, rates, times past midnight, multi-step counting)
  - 2 coding (read code, closure trap, buggy function's real output, recursion, dicts); answers are computed by Python itself
  - 1 planning (task chains, does-it-fit scheduling)
  - 1 web research: must use a web tool AND give the right fact
  - 1 real mission in a fresh folder of random files. Scored separately on **execution** (acted, saved the note), **correctness** (named the right largest file) and **all steps ticked**.
- The report shows Core x/13, a Challenge % by skill, and a comparison with the last run.

## Results
| Date | Run | Result |
|---|---|---|
| 3 Oct, 03:43-03:51 | Availability-limited (free quotas exhausted) | 56% - NOT a cognitive score; infrastructure worked |
| **3 Oct, 15:23** | **v1.0 baseline** | **Cognitive 80% · System 100% · 13/13 ran · 12/13 passed** |
| **6 Oct, 18:55** | **v1.1 (mission fix + timeouts + Gemini handoff)** | **Cognitive 100% · System 100% · 13/13 ran · 13/13 passed** |

The only failure in the v1.0 baseline was the mission test: the brain described a mission without creating it. Fixed and confirmed in v1.1 (6 Oct).

**3 Oct, 18:44 - invalid run.** "Clean my Downloads" ran a duplicate scan that walked a huge folder (`D:\Downloads\sources\android-37.0`) and froze PARKYY for minutes. Fixed: the scan now stops after 20s, and any single tool is cut off after 90s.

**3 Oct, 19:16 - mission-fix check, cut short by limits.**
- Coverage 7/13; System 93%; Cognitive not measurable.
- Groq's free daily limit had been used up by the day's runs.
- The mission fix works: the mission was really created and step 1 was done (it found the 3 biggest files). The brains then ran out before step 2.
- New bug found and fixed: Gemini rejected chats where Groq had made the earlier tool calls (missing "thought signature"). It now accepts them.

**6 Oct, 18:55 - v1.1 clean run: 13/13.**
- Mission went from fail to pass: PARKYY created the mission, found the 3 biggest files, asked for a Yes, and saved the note.
- Honest caveat: the brain forgot to tick off steps 1-2, so the mission log said "finished with problems" even though the work was done. The benchmark checks the real result (files found and note saved), so it passed.
- Gemini handoff confirmed live: Groq hit its limit mid-run, Gemini took over the mission, and it worked.
- Fixed after the run (not yet measured):
  - mission tools are never cut from a brain's tool list while a mission runs (Groq was refused `mission_update`)
  - if a brain does a step's work but forgets to tick it, PARKYY ticks it, based on which tools actually ran
- Scoreboard so far: Groq is reliable (mission 77%), Gemini handles missions well but research failed 3/3 under load, NVIDIA 0/36.

## Next
1. v1.2 clean run (when Groq's daily limit is fresh): core must stay 13/13, the challenge % becomes the new baseline, and missions should finish with every step ticked.
2. Then the C: clean-up as the first real-world mission: scan, plan, Yes for each step, one action at a time, verify. Never "clean everything".
3. Phase 2, decided from the numbers:
   - beliefs with evidence and confidence
   - memory split four ways: what happened, facts, how-to, what worked
   - planner that re-plans after each step
   - reflection after each mission
4. Scoreboard: separate model, tool, routing, context and user-correction failures.
5. Phone app v0.8:
   - texting
   - PARKYY calling Saud's phone
   - sending things from laptop to phone
   - watch mood tracking
6. Later: LG TV, website control (INSTALL-STUDIO), freeing space on C:.

## Milestone 1 Nov 2026 - roaming PARKYY, online USB, repo prep (done with Claude)
- **Roaming PARKYY (one character):** when roaming is on, the big face in the PARKYY window steps aside and PARKYY walks
  on the top edge of your windows, flies, reads with glasses when a document is open, sleeps when you're away, and shows
  listening/thinking/speaking + a speech bubble. Files: desktop/roam.html, roam.js, pet-main.js, pet-preload.js, fgwin.ps1.
  Tray: "Roam on desktop (walk & fly)". Off: PARKYY_PET=0. Seen working on the real desktop (screenshot, 1 Nov 22:33).
- **USB edition online:** Groq -> Gemini when there's internet, offline Hermes otherwise or when the cloud fails
  (60 s cooldown). /web search with sources, /status /online /offline /setup-online (copies ONLY Groq/Gemini keys, asks first).
  USB pet (pet.ps1, WPF) walks + flies next to the console. Tested in a sandbox with PowerShell 7 + a mock brain; NOT yet on real Windows.
- **Repo prep:** new README, docs/DEMO-SCRIPT.md, docs/PRE-PUBLISH-CHECKLIST.md, a .gitignore that keeps secrets and
  personal data out. RESTART-PARKYY.bat added. Desktop log capped at ~20 MB (it had grown to 313 MB).
- **Status on 1 Nov:** self-test 20/21 - Gmail & Calendar fails because the Google login expired (re-run CONNECT-GOOGLE.bat).
- **Results recorded:** v1.2 run 7 Oct - 15/20, hidden challenge 93%, core 9/13, cognitive 70%, system 86%.

## Live test session 2 Nov 2026, 01:24-01:55 (done by Claude on the real laptop, through PARKYY's own window)
- **Self-test v0.9.26: 21/21** (Gmail & Calendar fixed since 1 Nov).
- **Google, read-only:** "what's on my calendar this week" -> answered from Google Calendar (nothing scheduled);
  "how many unread emails" -> answered a count from Gmail. Nothing was sent, created or changed.
- **Safety gate, live:** "delete news-check.log" -> PARKYY asked first (offered the Recycle Bin, not a hard delete);
  answered No -> "leaving the file as it is". Verified from disk: file still there, unchanged.
- **Failover, live:** NVIDIA (no working model) and Claude (no credit) were rested automatically; Groq answered.
- **Benchmark v1.2 (24 min): 19/20 · core 13/13 · hidden challenge 93% · cognitive 100% · system 100%.**
  Only brain left by the end: Groq. Report: notes/benchmarks/benchmark 2026-11-02 0154.md
- **Roaming PARKYY seen live:** walking/flying on the real desktop, speech bubble mirrors PARKYY's replies.
- **Bugs found (open):**
  1. Yes/No buttons: clicking Yes on a mission's approval card can reply "That was already answered" while the
     mission keeps waiting -> the brain then asks again in plain text and the mission says "stuck on step 2".
     This is why the hidden real-mission test is PARTIAL (steps not all ticked). Fix before filming a mission.
  2. Chat shows raw **markdown** stars (e.g. "You have **4 unread emails**").
  3. Simulation mode reply said "your Downloads folder has been virtually organized" - nothing was moved (test
     confirms), but the wording can read as if it was. Reword to "here's the plan, nothing moved yet".
  4. Roaming PARKYY could stay "carried" after a drag if the mouse was released outside him -> FIXED in roam.js
     (drop on pointercancel / lost capture / blur / 4 s watchdog). Needs a PARKYY restart to load.

## Fixes 2 Nov 2026, ~02:45 (Claude)
- **Yes-button / stuck-mission bug FIXED in code** (agent.py + tools/tools.py): every Yes/No answer (button, typed
  yes/no, or the benchmark) now (1) tells the brain what happened so it never asks again, (2) ticks the mission step
  that was waiting, from the real tool result, (3) carries the mission on by itself. Before, tapping Yes in the app
  never resumed the mission at all. Double-tapping an old card now says "already answered, nothing more to do".
  Tested against PARKYY's real mission code in a sandbox (step ticked, mission continued, No path fine).
  NOT yet re-tested live: run RELOAD-BACKEND.bat, then a mission or "run the benchmark".
- Chat bubbles now show **bold** instead of raw stars (desktop/index.html).
- **PUBLISH-TO-GITHUB.bat** (+ tools/publish_github.ps1): uploads an allow-list of code only, replaces personal names
  in the uploaded copy, scans for API keys and for every real value in .env / the GitHub token and STOPS if found,
  creates the repo private first, then asks before making it public. Tested against a fake GitHub: 59 files, no
  secrets, no personal names. LICENSE (MIT) added.
- Backups of the changed files: _backup-2026-11-02\

## USB edition - real test on the laptop, 3 Nov 2026 (Claude, via computer use + E:\PARKYY-USB\SELF-TEST.bat)
- Stick E: (58.6 GB): llamafile-0.10.6.exe + Hermes-2-Pro-Llama-3-8B-Q4_K_M.gguf. Files updated to the newest version.
- Run 1: 9/11 - Groq and Gemini answered 404 (the stick used retired model names) and the pet crashed on start
  (XAML missing xmlns:x). Both fixed: Pick-Model uses laptop data\models.json, and on a 404 PARKYY asks the
  provider for its model list and switches by itself; pet.ps1 XAML fixed.
- Run 2: 10/11 (pet still failed only because the old pet.ps1 was still on the stick); pet then tested on its own
  with PET-TEST.bat: appeared, greeted, walked along the bottom of the screen, left by itself after ~45 s, no errors.
- Final: offline brain PASS (725 s incl. ~250 s load; RAM 90% with desktop PARKYY + LM Studio open), online [Groq]
  PASS, /web PASS, cloud-fail -> offline fallback PASS, memory sync PASS, pet PASS.
- Not tested: physically turning Wi-Fi off (offline was forced / cloud made to fail instead), another PC.
- Tip: close LM Studio and desktop PARKYY before using the stick on this laptop - the offline brain will be much faster.
