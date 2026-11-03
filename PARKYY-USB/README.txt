PARKYY - USB EDITION (offline + online)
=======================================

WHAT GOES ON THE STICK
  PARKYY-USB\
    start.bat            <- double-click this to run PARKYY
    parkyy.ps1           <- PARKYY himself
    llamafile-X.Y.Z.exe  <- you download this (see step 2)  [offline brain]
    models\Hermes-2-Pro-Llama-3-8B-Q4_K_M.gguf   (4.92 GB)  [offline brain]
    pet.ps1, pet\assets\   <- the little PARKYY pet (walks on your windows)
    keys.env             <- optional: your free Groq / Gemini keys (see ONLINE below)
    memory\, logs\      <- created automatically; they travel with the stick

HOW PARKYY CHOOSES HIS BRAIN (automatic)
  Internet + keys.env  -> free cloud brains: Groq first, then Gemini. Starts in seconds,
                          the 5 GB offline brain stays asleep.
  No internet          -> the offline Hermes on the stick (30-90 s to load, then it just works).
  Wi-Fi drops or a free limit runs out in the middle of a chat -> he switches to the
                          offline brain by himself and tells you. Nothing to press.
  Every reply shows which brain answered, e.g. [Groq] or [Offline Hermes].

ONLINE SETUP (one time)
  On Saud's laptop, with the stick plugged in, start PARKYY and type:  /setup-online
  It asks first, then copies ONLY the free Groq + Gemini keys (and their model names)
  into keys.env on the stick. Claude / OpenAI / GitHub keys are never copied.
  On any other PC you can also write them by hand into keys.env:
      GROQ_API_KEY=...
      GEMINI_API_KEY=...
  Keep in mind: anyone holding the stick can read keys.env. They are free-tier keys and you
  can revoke them on console.groq.com / aistudio.google.com if the stick is ever lost.
  (If you'd rather never put keys on the stick, skip this - it simply stays offline-only.)

ONE-TIME SETUP FOR THE OFFLINE BRAIN
  1. USB stick: 8 GB minimum (16 GB+ recommended), formatted as exFAT.
     FAT32 CANNOT hold the 4.92 GB model file. Formatting erases the stick.
  2. Download the latest llamafile .exe from
     github.com/mozilla-ai/llamafile/releases  (the plain "llamafile-X.Y.Z"
     file, not "-thin"). If it has no .exe ending, rename it to add .exe.
     Put it in the PARKYY-USB folder.
  3. Copy the model from
     D:\Downloads\parkyy\parkyy\models\NousResearch\Hermes-2-Pro-Llama-3-8B-GGUF\
     into PARKYY-USB\models\
  4. Copy the whole PARKYY-USB folder onto the stick.

USING IT ON ANY WINDOWS PC
  Plug in -> open the stick -> double-click start.bat.
  No installs. If Windows SmartScreen warns about llamafile: "More info" -> "Run anyway".
  Commands inside PARKYY:
    /remember <fact>   save something permanently (also: "remember that ...")
                       Saved in memory\memory.txt - editable by hand
    /memory            list saved facts        /forget <n>   delete fact n
    /web <question>    look it up on the internet, then answer with sources [1] [2]
    /status            internet? which brains are ready?
    /online            re-check the internet and go back to the cloud brains
    /offline           force the offline brain (e.g. to save your free limits)
    /setup-online      copy the free keys from laptop PARKYY (laptop only, asks first)
    /sync              sync memory with laptop PARKYY now
    /voice             toggle spoken replies (Windows' built-in offline voice)
    /clear             new conversation        /exit         quit
  Backup UI: while the offline brain is running you can also open http://127.0.0.1:8080
  in a browser for llamafile's own chat page (no PARKYY memory there).

THE PET
  start.bat also starts the original PARKYY as a small desktop pet. He walks on the top edge of
  your windows, flies around, reads with glasses when a document is open, sleeps when you're idle, shows a
  'Thinking...' bubble while PARKYY works and speaks the replies in a bubble.
  Click him = he's happy. Right-click = Say hi / Hide pet. He leaves when PARKYY closes.
  No pet? run  set PARKYY_PET=0  in the command window before start.bat.
  Needs Windows 10/11 (built-in PowerShell + WPF). Log: logs\pet.log

MEMORY SYNC WITH LAPTOP PARKYY
  Both share the same memory. It syncs automatically whenever PARKYY starts,
  saves/forgets something, or exits - on Saud's laptop (either edition), as
  long as the stick is plugged in. On other PCs the stick keeps its own copy
  and syncs next time it meets the laptop.

GOOD TO KNOW
  - Offline brain runs on the CPU: a few words per second on an average laptop.
    16 GB RAM is comfortable, 8 GB works but is slow. Online brains are much faster.
  - What the stick can do ONLINE today: chat, write, plan, code, /web research.
    It still can NOT send email or edit the Google Calendar - those need your Google
    sign-in, which lives only on the laptop. PARKYY drafts, you send.
  - Work/school PCs that block running programs from USB won't run it.
