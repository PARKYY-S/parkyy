"""
PARKYY watchdog - a tiny always-on helper on the laptop.

It starts with Windows (see INSTALL-WATCHDOG.bat) and does two small things:
  1. Lets your phone START laptop PARKYY when it isn't running:
       GET /wake    -> starts PARKYY if it's down, says "running" or "starting"
       GET /status  -> is PARKYY's backend up?
     It's only reachable from your own devices (through Tailscale), never the internet.
  2. Keeps the laptop from idle-sleeping while it's PLUGGED IN, so the phone can
     always reach it. On battery, normal sleep is allowed.
     (A shut-down laptop, or one asleep with the lid closed, can't be woken remotely.)

Turn off the keep-awake part with PARKYY_WATCHDOG_AWAKE=0 in .env.
"""

import http.server
import ipaddress
import json
import os
import socketserver
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PARKYY_WATCHDOG_PORT", "8001"))
BACKEND = "http://127.0.0.1:8000/health"
LOG = HERE / "desktop" / "watchdog.log"
WIN = os.name == "nt"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TS = r"C:\Program Files\Tailscale\tailscale.exe"

_last_launch = 0.0
_lock = threading.Lock()


def log(*a):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def backend_up() -> bool:
    try:
        with urllib.request.urlopen(BACKEND, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def launch_parkyy() -> str:
    """Start PARKYY (desktop app + backend + brain) unless it's already up or just launched."""
    global _last_launch
    if backend_up():
        return "running"
    with _lock:
        if time.time() - _last_launch < 90:        # already starting - don't launch twice
            return "starting"
        _last_launch = time.time()
    bat = HERE / "START-PARKYY-LAN.bat"
    log("wake request -> launching", bat)
    if WIN and bat.exists():
        subprocess.Popen(["cmd", "/c", "start", "", "/min", str(bat)], cwd=str(HERE), creationflags=NOWIN)
    return "starting"


def trusted(host: str) -> bool:
    try:
        a = ipaddress.ip_address(host)
    except ValueError:
        return False
    return a.is_loopback or a.is_private or a in ipaddress.ip_network("100.64.0.0/10")


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        if not trusted(self.client_address[0]):
            return self._send(403, {"ok": False, "error": "not a trusted device"})
        path = self.path.split("?")[0].rstrip("/")
        if path == "/wake":
            return self._send(200, {"ok": True, "state": launch_parkyy()})
        if path in ("/status", ""):
            return self._send(200, {"ok": True, "backend": backend_up()})
        return self._send(404, {"ok": False})

    do_POST = do_GET

    def log_message(self, *a):
        pass


def keep_awake_when_plugged_in():
    if not WIN or os.environ.get("PARKYY_WATCHDOG_AWAKE", "1") == "0":
        return
    import ctypes

    class PS(ctypes.Structure):
        _fields_ = [("AC", ctypes.c_byte), ("Flag", ctypes.c_byte), ("Pct", ctypes.c_byte),
                    ("Sys", ctypes.c_byte), ("Life", ctypes.c_ulong), ("Full", ctypes.c_ulong)]
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    while True:
        ps = PS()
        plugged = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(ps)) and ps.AC == 1
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED if plugged else ES_CONTINUOUS)
        time.sleep(60)


def publish_on_tailscale():
    """Expose the watchdog privately at https://<laptop>.ts.net:8443 (your devices only)."""
    if not WIN or not Path(TS).exists():
        return
    try:
        r = subprocess.run([TS, "serve", "--bg", "--https=8443", f"http://127.0.0.1:{PORT}"],
                           capture_output=True, text=True, timeout=30, creationflags=NOWIN)
        log("tailscale serve 8443:", r.returncode, (r.stdout + r.stderr).strip()[:200])
    except Exception as e:
        log("tailscale serve failed:", e)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    log("watchdog starting on port", PORT)
    threading.Thread(target=keep_awake_when_plugged_in, daemon=True).start()
    threading.Thread(target=publish_on_tailscale, daemon=True).start()
    try:
        Server(("0.0.0.0", PORT), Handler).serve_forever()
    except OSError as e:
        log("could not start (already running?):", e)


if __name__ == "__main__":
    main()
