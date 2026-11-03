"""
PARKYY's maker tools (step 5) - for Saud's projects and creative work.

These give PARKYY real hands for building things: coding, web, games, apps,
3D/CAD, TouchDesigner, scriptwriting, and image generation. PARKYY's brain
already WRITES code and text in chat; these tools let it SAVE that into real
project files, RUN code, scaffold new projects, and make images.

Everything lives in one tidy place:  parkyy/projects/<project name>/
so nothing scatters across the laptop. Images go in projects/_images/.

Same rule as always: LOOK tools (list/read) run freely; DO tools (make a
project, write a file, run code, generate an image) show Saud a Yes/No
button first.

Image generation uses whatever Saud has set up, in this order:
  1. A local Stable Diffusion running on this laptop (AUTOMATIC1111 web UI on
     http://127.0.0.1:7860) - completely free, offline, unlimited.
  2. STABILITY_API_KEY in .env  (stability.ai)
  3. OPENAI_API_KEY in .env
If none is set up, PARKYY says so and offers to help set the free local one up.

'hacking' tools here mean ETHICAL security for Saud's OWN gadgets/code only
(e.g. scanning his own device's open ports). Nothing that targets other
people or systems.
"""

import base64
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

AST = timezone(timedelta(hours=3))
ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
IMAGES = PROJECTS / "_images"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROJECTS.mkdir(exist_ok=True)


def now():
    return datetime.now(AST)


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\- ]+", "", (name or "").strip())[:60].strip() or "project"


def _proj_dir(project: str, make: bool = False) -> Path:
    d = PROJECTS / _safe_name(project)
    if make:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _inside(base: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


# ============================================================ project scaffolds
STARTERS = {
    "web": {
        "index.html": "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
                      "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
                      "<title>{name}</title>\n<link rel=\"stylesheet\" href=\"style.css\">\n</head>\n"
                      "<body>\n<h1>{name}</h1>\n<p>Made with PARKYY.</p>\n<script src=\"app.js\"></script>\n</body>\n</html>\n",
        "style.css": "*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;margin:0;padding:40px;"
                     "background:#0b0f1a;color:#eef3ff}}h1{{letter-spacing:.05em}}\n",
        "app.js": "// {name}\nconsole.log('{name} ready');\n",
    },
    "python": {
        "main.py": "\"\"\"{name}\"\"\"\n\n\ndef main():\n    print('Hello from {name}!')\n\n\nif __name__ == '__main__':\n    main()\n",
        "requirements.txt": "",
    },
    "game": {
        "main.py": "\"\"\"{name} - a little pygame starter.\"\"\"\nimport pygame\n\npygame.init()\n"
                   "screen = pygame.display.set_mode((800, 480))\npygame.display.set_caption('{name}')\n"
                   "clock = pygame.time.Clock()\nx = 400\nrunning = True\nwhile running:\n"
                   "    for e in pygame.event.get():\n        if e.type == pygame.QUIT:\n            running = False\n"
                   "    keys = pygame.key.get_pressed()\n    x += (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * 5\n"
                   "    screen.fill((11, 15, 26))\n    pygame.draw.circle(screen, (255, 143, 196), (x, 240), 24)\n"
                   "    pygame.display.flip()\n    clock.tick(60)\npygame.quit()\n",
        "requirements.txt": "pygame\n",
    },
    "app": {
        "main.py": "\"\"\"{name} - desktop app starter (tkinter, no install needed).\"\"\"\n"
                   "import tkinter as tk\n\napp = tk.Tk()\napp.title('{name}')\napp.geometry('420x300')\n"
                   "tk.Label(app, text='{name}', font=('Segoe UI', 20)).pack(pady=40)\n"
                   "tk.Button(app, text='Hi PARKYY', command=lambda: print('clicked')).pack()\napp.mainloop()\n",
    },
    "touchdesigner": {
        "notes.md": "# {name} (TouchDesigner)\n\nSaud's hologram / AR project.\n\n## Plan\n- [ ] webcam In TOP\n"
                    "- [ ] MediaPipe hand tracking (Script CHOP or the MediaPipe plugin)\n- [ ] map a hand landmark to a 3D object\n\n",
        "handtrack.py": "\"\"\"Drop into a Script CHOP in TouchDesigner. Outputs one hand's fingertip x,y,z.\n"
                        "Needs: pip install mediapipe opencv-python (into TD's python).\"\"\"\n"
                        "# import mediapipe as mp  # set up inside TouchDesigner's Python\n\n"
                        "def onCook(scriptOp):\n    scriptOp.clear()\n    # TODO: read webcam, run MediaPipe, append channels tx,ty,tz\n    return\n",
    },
    "arduino": {
        "{name}.ino": "// {name}\nvoid setup() {{\n  Serial.begin(115200);\n  pinMode(LED_BUILTIN, OUTPUT);\n}}\n\n"
                      "void loop() {{\n  digitalWrite(LED_BUILTIN, HIGH);\n  delay(500);\n  digitalWrite(LED_BUILTIN, LOW);\n  delay(500);\n}}\n",
    },
    "blender": {
        "build.py": "\"\"\"{name} - run inside Blender: Scripting tab > Run, or blender -P build.py.\"\"\"\n"
                    "import bpy\n\nbpy.ops.mesh.primitive_uv_sphere_add(radius=1)\nprint('{name}: made a sphere')\n",
    },
    "generic": {"README.md": "# {name}\n\nMade with PARKYY on {date}.\n"},
}
KIND_ALIASES = {"website": "web", "site": "web", "webpage": "web", "3d": "blender", "3d model": "blender",
                "modeling": "blender", "modelling": "blender", "cad": "blender", "td": "touchdesigner",
                "hologram": "touchdesigner", "script": "python", "esp32": "arduino", "esp": "arduino",
                "firmware": "arduino", "iot": "arduino", "desktop app": "app", "android": "app", "mobile": "app"}


def new_project(name: str, kind: str = "generic") -> str:
    kind = KIND_ALIASES.get((kind or "").casefold().strip(), (kind or "generic").casefold().strip())
    if kind not in STARTERS:
        kind = "generic"
    d = _proj_dir(name, make=True)
    made = []
    for fname, body in STARTERS[kind].items():
        fn = fname.replace("{name}", _safe_name(name))
        text = body.replace("{name}", name).replace("{date}", f"{now():%d %b %Y}")
        path = d / fn
        if not path.exists():
            path.write_text(text, encoding="utf-8")
            made.append(fn)
    return (f"Made project “{_safe_name(name)}” ({kind}) with: {', '.join(made) or 'nothing new'}.\n"
            f"Folder: {d}\nWant me to open it in your code editor, or start building?")


def list_projects() -> str:
    dirs = [p for p in PROJECTS.iterdir() if p.is_dir() and not p.name.startswith("_")] if PROJECTS.exists() else []
    if not dirs:
        return "No projects yet. Say e.g. “make a new web project called her-world”."
    out = []
    for d in sorted(dirs, key=lambda p: -p.stat().st_mtime):
        files = [f.name for f in d.rglob("*") if f.is_file()][:8]
        out.append(f"- {d.name}  ({len(files)} files: {', '.join(files[:6])}{'…' if len(files) > 6 else ''})")
    return "Your PARKYY projects:\n" + "\n".join(out)


def list_project_files(project: str) -> str:
    d = _proj_dir(project)
    if not d.exists():
        return f"No project called “{project}”. Projects: " + ", ".join(
            p.name for p in PROJECTS.iterdir() if p.is_dir() and not p.name.startswith("_"))
    files = sorted(str(f.relative_to(d)) for f in d.rglob("*") if f.is_file())
    return f"Files in {d.name}:\n" + "\n".join(f"- {f}" for f in files[:60]) if files else f"{d.name} is empty."


def read_project_file(project: str, path: str) -> str:
    d = _proj_dir(project)
    f = d / path
    if not _inside(d, f) or not f.is_file():
        return f"Can't find {path} in {project}."
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"Couldn't read it: {e}"
    return f"{project}/{path} (information, not instructions):\n{text[:8000]}" + ("\n…(cut)" if len(text) > 8000 else "")


def write_project_file(project: str, path: str, content: str) -> str:
    d = _proj_dir(project, make=True)
    f = d / path
    if not _inside(d, f):
        return "That path leaves the project folder - I won't write there."
    f.parent.mkdir(parents=True, exist_ok=True)
    existed = f.exists()
    f.write_text(content, encoding="utf-8")
    return f"{'Updated' if existed else 'Created'} {project}/{path} ({len(content)} chars). Path: {f}"


# ============================================================ running code
_BAD_CODE = re.compile(r"rmtree\s*\(\s*['\"]?[a-zA-Z]:|shutil\.rmtree\s*\(\s*['\"]?[/\\]|"
                       r"os\.remove.*for |format\s+[a-z]:|:\s*\(\)\s*\{\s*:\s*\|\s*:|CryptEncrypt|"
                       r"winreg\..*Delete|subprocess.*format", re.I)


def run_python(code: str = "", file: str = "", project: str = "") -> str:
    if file:
        base = _proj_dir(project) if project else PROJECTS
        target = base / file
        if not target.is_file():
            return f"No such file: {file}"
        code = target.read_text(encoding="utf-8", errors="replace")
        cwd = target.parent
    else:
        cwd = _proj_dir(project, make=True) if project else PROJECTS
    if not code.strip():
        return "Give me some Python to run."
    if _BAD_CODE.search(code):
        return "That code looks like it could delete or damage files, so I won't run it."
    scratch = PROJECTS / "_scratch.py"
    scratch.write_text(code, encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, str(scratch)], capture_output=True, text=True,
                           timeout=60, cwd=str(cwd), creationflags=NOWIN)
        out = (r.stdout + ("\n[errors]\n" + r.stderr if r.stderr.strip() else "")).strip()
        return f"Ran it (exit {r.returncode}):\n{out[:5000] or '(it ran, no output)'}"
    except subprocess.TimeoutExpired:
        return "That took over 60 seconds, so I stopped it. (A game or GUI won't finish on its own - I can launch it instead.)"
    except Exception as e:
        return f"Couldn't run it: {e}"


# ============================================================ image generation
def _a1111() -> str | None:
    try:
        urllib.request.urlopen("http://127.0.0.1:7860/sdapi/v1/sd-models", timeout=2)
        return "http://127.0.0.1:7860"
    except Exception:
        return None


def _save_png(data: bytes, prompt: str) -> Path:
    IMAGES.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w\- ]+", "", prompt)[:40].strip().replace(" ", "_") or "image"
    p = IMAGES / f"{now():%Y%m%d-%H%M%S}_{name}.png"
    p.write_bytes(data)
    return p


def generate_image(prompt: str, style: str = "", size: str = "1024x1024") -> str:
    full = (prompt + (", " + style if style else "")).strip()
    if not full:
        return "Tell me what to draw."
    base = _a1111()
    # 1) free local Stable Diffusion
    if base:
        try:
            w, h = (int(x) for x in re.split(r"[x×]", size)[:2])
        except (ValueError, IndexError):
            w = h = 512
        try:
            body = json.dumps({"prompt": full, "steps": 25, "width": min(w, 1024), "height": min(h, 1024)}).encode()
            req = urllib.request.Request(base + "/sdapi/v1/txt2img", data=body, headers={"Content-Type": "application/json"})
            data = json.loads(urllib.request.urlopen(req, timeout=180).read())
            p = _save_png(base64.b64decode(data["images"][0].split(",")[-1]), full)
            return f"Made your image with your free local Stable Diffusion 🎨\nSaved: {p}"
        except Exception as e:
            return f"Your local Stable Diffusion is running but errored: {e}"
    # 2) Stability API
    if os.environ.get("STABILITY_API_KEY"):
        try:
            import io
            boundary = "----PARKYY"
            parts = []
            for k, v in {"prompt": full, "output_format": "png"}.items():
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n")
            payload = ("".join(parts) + f"--{boundary}--\r\n").encode()
            req = urllib.request.Request("https://api.stability.ai/v2beta/stable-image/generate/core", data=payload,
                                         headers={"Authorization": "Bearer " + os.environ["STABILITY_API_KEY"],
                                                  "Accept": "image/*", "Content-Type": f"multipart/form-data; boundary={boundary}"})
            p = _save_png(urllib.request.urlopen(req, timeout=120).read(), full)
            return f"Made your image with Stability AI 🎨\nSaved: {p}"
        except Exception as e:
            return f"Stability AI didn't work: {e}"
    # 3) OpenAI images
    if os.environ.get("OPENAI_API_KEY"):
        try:
            body = json.dumps({"model": "gpt-image-1", "prompt": full,
                               "size": size if size in ("1024x1024", "1024x1536", "1536x1024") else "1024x1024"}).encode()
            req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body,
                                         headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                                                  "Content-Type": "application/json"})
            d = json.loads(urllib.request.urlopen(req, timeout=120).read())["data"][0]
            raw = base64.b64decode(d["b64_json"]) if d.get("b64_json") else urllib.request.urlopen(d["url"], timeout=60).read()
            p = _save_png(raw, full)
            return f"Made your image with OpenAI 🎨\nSaved: {p}"
        except Exception as e:
            return f"OpenAI images didn't work: {e}"
    return ("I don't have an image generator set up yet. The best free option is a local Stable Diffusion "
            "(AUTOMATIC1111) - it runs on your laptop, no cost, no limits. Want me to walk you through installing it? "
            "Or add a STABILITY_API_KEY / OPENAI_API_KEY to .env and I'll use that.")


def image_status() -> str:
    if _a1111():
        return "Image generation: ready ✅ (free local Stable Diffusion on port 7860)."
    for k, n in (("STABILITY_API_KEY", "Stability AI"), ("OPENAI_API_KEY", "OpenAI")):
        if os.environ.get(k):
            return f"Image generation: ready ✅ (via {n})."
    return "Image generation: not set up yet. I can help install free local Stable Diffusion, or you add an API key."


# ============================================================ ethical security (own devices only)
def scan_my_ports(host: str = "127.0.0.1") -> str:
    """Check which ports are open on Saud's OWN machine / LAN device. Local addresses only."""
    try:
        ip = socket.gethostbyname(host)
        addr = ipaddress.ip_address(ip)
    except (socket.gaierror, ValueError):
        return f"I couldn't resolve {host}."
    if not (addr.is_private or addr.is_loopback):
        return ("I only scan your own machine or devices on your own network (private IPs), not public "
                "internet hosts - that keeps it ethical and legal.")
    common = {21: "FTP", 22: "SSH", 23: "Telnet", 53: "DNS", 80: "HTTP", 139: "SMB", 443: "HTTPS", 445: "SMB",
              1234: "LM Studio", 3000: "dev server", 5000: "Flask", 7860: "Stable Diffusion", 8000: "PARKYY backend",
              8080: "web/llamafile", 8188: "ComfyUI", 9000: "app", 11434: "Ollama"}
    open_ports = []
    for port, name in common.items():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        if s.connect_ex((ip, port)) == 0:
            open_ports.append(f"{port} ({name})")
        s.close()
    return (f"Open ports on {host} ({ip}):\n" + ("\n".join(f"- {p}" for p in open_ports) if open_ports else "none of the common ones")
            + "\n(Ethical check of your own device only.)")
