# Before PARKYY goes on GitHub (5 minutes, do it once)

1. **Make the safety net first.** Put the new `.gitignore` in the project folder *before* `git init`.
2. `git init`, then `git add .`, then **`git status`**. Read the list. None of these may appear:
   `.env`, `voice.env`, `google-credentials.json`, anything in `data/` except `bench_history.json`,
   `memory/`, `about-saud.md`, `keys.env`, `*.wav`, `models/`, `venv/`, `node_modules/`.
   If one is there: `git rm --cached <file>` and check `.gitignore`.
3. **Rotate anything that ever left your machine.** Never pushed it? Nothing to do. If a key *was*
   committed even once, delete the repo history, revoke that key (Groq / Gemini / OpenRouter / Google /
   GitHub token) and make a new one - git remembers old commits.
4. `data/github-token.txt` and `data/google-token.json` are plain-text logins on your disk. They are
   ignored by the new `.gitignore`, but treat them like passwords.
5. Add `.env.example` (a copy of your template with the key *values* removed). The old `.env - Copy.example`
   already looks right - rename it to `.env.example`.
6. Record the demo (docs/DEMO-SCRIPT.md), save it as `docs/demo.gif` (and the full video on YouTube/Drive),
   then un-comment the image line at the top of README.md.
7. Make the repo **private first**, look at it on github.com as a stranger would, then switch to public.
