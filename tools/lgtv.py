"""
PARKYY x LG TV (webOS), over your home Wi-Fi.

One-time: CONNECT-TV.bat -> PARKYY finds the TV -> press "Allow" on the TV screen.
PARKYY saves the TV's key in data\\lgtv.json.
For "turn the TV on": on the TV turn on  Settings > General > Devices > "Turn on via Wi-Fi"
(older models: "Mobile TV On" / "LG Connect Apps").

TV control runs straight away (like music) - it's harmless and easy to undo.
Only works while the laptop is on the same Wi-Fi as the TV.
"""

import asyncio
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "data" / "lgtv.json"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NOT_SET = "The LG TV isn't connected yet - double-click CONNECT-TV.bat on the laptop (TV on, same Wi-Fi)."
NEED_LIB = "TV control isn't installed - double-click CONNECT-TV.bat on the laptop."

APP_ALIASES = {"youtube": "youtube.leanback.v4", "netflix": "netflix", "prime": "amazon", "prime video": "amazon",
               "amazon": "amazon", "disney": "com.disney.disneyplus-prod", "hotstar": "com.disney.disneyplus-prod",
               "spotify": "spotify-beehive", "browser": "com.webos.app.browser", "live tv": "com.webos.app.livetv",
               "settings": "com.palm.app.settings", "apple tv": "com.apple.appletv", "shahid": "shahid"}
BUTTONS = {"home", "back", "up", "down", "left", "right", "enter", "ok", "exit", "menu", "info", "play", "pause",
           "stop", "rewind", "fastforward", "red", "green", "yellow", "blue", "channelup", "channeldown",
           "volumeup", "volumedown", "mute", "asterisk", "cc", "dash", "guide", "0", "1", "2", "3", "4", "5", "6",
           "7", "8", "9"}


def _load() -> dict:
    try:
        return json.loads(CONF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d: dict):
    CONF.parent.mkdir(exist_ok=True)
    CONF.write_text(json.dumps(d, indent=2), encoding="utf-8")


# ============================================================ finding + pairing
def discover(timeout: float = 4) -> list[str]:
    """Find LG webOS TVs on the Wi-Fi (SSDP)."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
           "ST: urn:lge-com:service:webos-second-screen:1\r\n\r\n").encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.settimeout(1)
    s.sendto(msg, ("239.255.255.250", 1900))
    found, t0 = [], time.time()
    while time.time() - t0 < timeout:
        try:
            data, addr = s.recvfrom(2048)
            if b"webos" in data.lower() or b"lge" in data.lower():
                if addr[0] not in found:
                    found.append(addr[0])
        except socket.timeout:
            continue
    s.close()
    return found


def _mac_for(ip: str) -> str:
    try:
        out = subprocess.run(["arp", "-a", ip], capture_output=True, text=True, timeout=10, creationflags=NOWIN).stdout
        m = re.search(r"([0-9a-f]{2}[-:]){5}[0-9a-f]{2}", out, re.I)
        return m.group(0).replace("-", ":") if m else ""
    except Exception:
        return ""


def _client(host, key):
    from aiowebostv import WebOsClient
    return WebOsClient(host, client_key=key)


def setup(host: str = "") -> str:
    try:
        import aiowebostv  # noqa: F401
    except ImportError:
        return NEED_LIB
    host = host or (discover() or [""])[0]
    if not host:
        return "Couldn't find an LG TV. Is it on, and on the same Wi-Fi as the laptop? (Or type its IP address.)"
    print(f"Found TV at {host} - look at the TV and press ALLOW...")

    async def go():
        c = _client(host, _load().get("client_key"))
        await c.connect()
        key = c.client_key
        name = ""
        try:
            name = (c.tv_info.system or {}).get("modelName", "")
        except Exception:
            pass
        await c.disconnect()
        return key, name
    key, name = asyncio.run(go())
    d = _load()
    d.update(host=host, client_key=key, mac=_mac_for(host) or d.get("mac", ""), model=name)
    _save(d)
    return f"Connected to your LG TV {name} at {host} ✅" + ("" if d["mac"] else " (couldn't read its MAC - 'TV on' may not work)")


# ============================================================ running commands
def _run(fn):
    """Connect, do something, disconnect. fn(client) is an async function."""
    d = _load()
    if not d.get("client_key"):
        return NOT_SET
    try:
        import aiowebostv  # noqa: F401
    except ImportError:
        return NEED_LIB

    async def go():
        c = _client(d["host"], d["client_key"])
        try:
            await asyncio.wait_for(c.connect(), 8)
        except Exception:
            return "OFF"
        try:
            return await fn(c)
        finally:
            try:
                await c.disconnect()
            except Exception:
                pass
    try:
        r = asyncio.run(go())
    except Exception as e:
        return f"TV problem: {type(e).__name__}: {e}"
    if r == "OFF":
        return "I can't reach the TV - it's off or not on the Wi-Fi. Say 'turn on the TV' first."
    return r


def _wol(mac: str):
    mac_b = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    pkt = b"\xff" * 6 + mac_b * 16
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for port in (9, 7):
        s.sendto(pkt, ("255.255.255.255", port))
    s.close()


# ============================================================ tools
def tv_power(state: str = "off") -> str:
    d = _load()
    if not d.get("client_key"):
        return NOT_SET
    if str(state).lower() in ("on", "wake", "true", "1"):
        if not d.get("mac"):
            return "I don't know the TV's MAC address - run CONNECT-TV.bat again while the TV is on."
        _wol(d["mac"])
        return "Turning the TV on 📺 (needs 'Turn on via Wi-Fi' switched on in the TV settings)."

    async def off(c):
        await c.power_off()
        return "TV off 📴"
    return _run(off)


def tv_status() -> str:
    async def st(c):
        vol = await c.get_volume()
        app = await c.get_current_app()
        return (f"TV is on 📺 · app: {app or '?'} · volume {vol.get('volume', '?') if isinstance(vol, dict) else vol}"
                f"{' (muted)' if isinstance(vol, dict) and vol.get('muted') else ''}")
    return _run(st)


def tv_volume(action: str, level: int = 0) -> str:
    a = (action or "").lower()

    async def v(c):
        if a in ("set", "level") or (a.isdigit()):
            n = max(0, min(int(level or a or 10), 100))
            await c.set_volume(n)
            return f"TV volume {n} 🔊"
        if a == "up":
            for _ in range(max(1, int(level or 2))):
                await c.volume_up()
            return "Louder 🔊"
        if a == "down":
            for _ in range(max(1, int(level or 2))):
                await c.volume_down()
            return "Quieter 🔉"
        if a in ("mute", "unmute"):
            await c.set_mute(a == "mute")
            return "Muted 🔇" if a == "mute" else "Unmuted 🔊"
        return "Volume actions: set (level 0-100), up, down, mute, unmute."
    return _run(v)


def tv_open(app: str) -> str:
    want = (app or "").strip().lower()

    async def o(c):
        app_id = APP_ALIASES.get(want)
        if not app_id:
            apps = await c.get_apps_all() or []
            items = apps if isinstance(apps, list) else apps.get("launchPoints", apps.get("apps", []))
            hit = next((a for a in items if want in str(a.get("title", "")).lower()), None)
            if not hit:
                return f"No app called “{app}” on the TV."
            app_id = hit.get("id") or hit.get("appId")
        await c.launch_app(app_id)
        return f"Opened {app} on the TV 📺"
    return _run(o)


def tv_youtube(query: str) -> str:
    """Play a YouTube video on the TV (finds it with PARKYY's YouTube search)."""
    vid = None
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", query or "")
    if m:
        vid = m.group(1)
    else:
        try:
            from tools import gsuite
            found = gsuite.youtube_search(query, 1)
            m = re.search(r"youtu\.be/([\w-]{11})", found)
            vid = m.group(1) if m else None
        except Exception:
            vid = None
    if not vid:
        return f"Couldn't find a YouTube video for “{query}”."

    async def y(c):
        await c.launch_app_with_content_id("youtube.leanback.v4", vid)
        return f"Playing on the TV ▶️ https://youtu.be/{vid}"
    return _run(y)


def tv_input(source: str) -> str:
    s = (source or "").upper().replace(" ", "_")
    if re.fullmatch(r"HDMI_?\d", s):
        s = "HDMI_" + s[-1]

    async def i(c):
        await c.set_input(s)
        return f"Switched the TV to {s} 🔌"
    return _run(i)


def tv_button(name: str, times: int = 1) -> str:
    b = (name or "").lower().replace(" ", "").replace("_", "")
    if b not in BUTTONS:
        return "Buttons: " + ", ".join(sorted(BUTTONS))
    b = {"ok": "enter", "channelup": "CHANNELUP", "channeldown": "CHANNELDOWN"}.get(b, b)

    async def p(c):
        for _ in range(max(1, min(int(times or 1), 20))):
            await c.button(b.upper())
            await asyncio.sleep(0.25)
        return f"Pressed {name} on the TV remote"
    return _run(p)


def tv_notify(message: str) -> str:
    async def n(c):
        await c.send_message(message[:200])
        return "Shown on the TV 💬"
    return _run(n)


def status() -> str:
    d = _load()
    return f"LG TV: paired at {d['host']} ✅" if d.get("client_key") else "LG TV: not connected."


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        print(setup(sys.argv[2] if len(sys.argv) > 2 else ""))
    else:
        print(status())
