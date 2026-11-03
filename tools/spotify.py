"""
PARKYY x Spotify (needs Spotify Premium for playback control).

One-time: CONNECT-SPOTIFY.bat -> browser -> log in to Spotify -> Agree.
PARKYY keeps its login in data\\spotify.json (never share it).

Music control (play / pause / skip / volume) runs straight away - it's harmless
and you can undo it instantly. Changing your library (liking a song, adding
to a playlist) asks Yes/No first.
"""

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "data" / "spotify.json"
REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
          "playlist-read-private playlist-modify-private playlist-modify-public user-library-read user-library-modify")
NOT_SET = "Spotify isn't connected yet - double-click CONNECT-SPOTIFY.bat on the laptop (one time)."
API = "https://api.spotify.com/v1"


def _load() -> dict:
    try:
        return json.loads(CONF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d: dict):
    CONF.parent.mkdir(exist_ok=True)
    CONF.write_text(json.dumps(d, indent=2), encoding="utf-8")


# ============================================================ login (PKCE - no secret needed)
def connect(client_id: str = "") -> str:
    d = _load()
    cid = client_id or d.get("client_id")
    if not cid:
        return "Missing the Spotify Client ID (data\\spotify.json)."
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state:
                got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2 style='font-family:sans-serif'>PARKYY is connected to Spotify 🎀 - you can close this tab.</h2>"
                             .encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8888), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": cid, "response_type": "code", "redirect_uri": REDIRECT, "scope": SCOPES, "state": state,
        "code_challenge_method": "S256", "code_challenge": challenge})
    webbrowser.open(url)
    t0 = time.time()
    while "code" not in got and "error" not in got and time.time() - t0 < 300:
        time.sleep(0.3)
    srv.server_close()
    if "code" not in got:
        return "Spotify login didn't finish (" + got.get("error", "timed out") + ")."
    tok = _token_request({"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT,
                          "client_id": cid, "code_verifier": verifier})
    d.update(client_id=cid, **tok)
    _save(d)
    return "Connected! PARKYY can now play your Spotify 🎵"


def _token_request(form: dict) -> dict:
    req = urllib.request.Request("https://accounts.spotify.com/api/token",
                                 data=urllib.parse.urlencode(form).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read())
    out = {"access_token": j["access_token"], "expires_at": time.time() + int(j.get("expires_in", 3600)) - 60}
    if j.get("refresh_token"):
        out["refresh_token"] = j["refresh_token"]
    return out


def _access() -> str | None:
    d = _load()
    if not d.get("refresh_token"):
        return None
    if time.time() > d.get("expires_at", 0):
        try:
            d.update(_token_request({"grant_type": "refresh_token", "refresh_token": d["refresh_token"],
                                     "client_id": d["client_id"]}))
            _save(d)
        except Exception:
            return None
    return d["access_token"]


class _Err(Exception):
    pass


def _api(method: str, path: str, params: dict | None = None, body=None):
    tok = _access()
    if not tok:
        raise _Err(NOT_SET)
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else (b"" if method in ("PUT", "POST") else None)
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        if e.code == 404 and "NO_ACTIVE_DEVICE" in msg:
            raise _Err("NO_DEVICE")
        if e.code == 403 and "PREMIUM" in msg.upper():
            raise _Err("Spotify says this needs Premium.")
        raise _Err(f"Spotify said {e.code}: {msg[:200]}")


def _safe(fn):
    def wrap(*a, **kw):
        try:
            return fn(*a, **kw)
        except _Err as e:
            if str(e) == "NO_DEVICE":
                return ("No Spotify is open right now. Open Spotify on your laptop or phone (or say 'open Spotify'), "
                        "then ask me again.")
            return str(e)
        except Exception as e:
            return f"Spotify problem: {type(e).__name__}: {e}"
    wrap.__name__ = fn.__name__
    return wrap


def _device(name: str = "") -> str | None:
    devs = _api("GET", "/me/player/devices").get("devices", [])
    if not devs:
        return None
    if name:
        for d in devs:
            if name.lower() in d["name"].lower():
                return d["id"]
    act = [d for d in devs if d.get("is_active")]
    return (act or devs)[0]["id"]


# ============================================================ LOOK
@_safe
def spotify_now() -> str:
    p = _api("GET", "/me/player")
    if not p or not p.get("item"):
        return "Nothing is playing on Spotify right now."
    it = p["item"]
    artists = ", ".join(a["name"] for a in it.get("artists", []))
    return (f"{'▶️ Playing' if p.get('is_playing') else '⏸ Paused'}: {it['name']} — {artists} "
            f"on {p.get('device', {}).get('name', '?')} (volume {p.get('device', {}).get('volume_percent', '?')}%)")


@_safe
def spotify_search(query: str, kind: str = "track") -> str:
    kind = kind if kind in ("track", "album", "artist", "playlist") else "track"
    r = _api("GET", "/search", {"q": query, "type": kind, "limit": 8})
    items = [i for i in r.get(kind + "s", {}).get("items", []) if i]
    if not items:
        return "Nothing found on Spotify."
    out = []
    for i in items:
        by = ", ".join(a["name"] for a in i.get("artists", [])) if i.get("artists") else i.get("owner", {}).get("display_name", "")
        out.append(f"• {i['name']}" + (f" — {by}" if by else "") + f"  [{i['uri']}]")
    return "\n".join(out)


@_safe
def spotify_mine(what: str = "playlists") -> str:
    if what.startswith("like") or what.startswith("saved"):
        r = _api("GET", "/me/tracks", {"limit": 20})
        return "Your liked songs (newest):\n" + "\n".join(
            f"• {x['track']['name']} — {', '.join(a['name'] for a in x['track']['artists'])}" for x in r.get("items", []))
    if what.startswith("dev"):
        devs = _api("GET", "/me/player/devices").get("devices", [])
        return "Spotify devices:\n" + "\n".join(f"• {d['name']} ({d['type']}){' ← active' if d.get('is_active') else ''}"
                                                for d in devs) if devs else "No Spotify devices are open."
    r = _api("GET", "/me/playlists", {"limit": 50})
    return "Your playlists:\n" + "\n".join(f"• {p['name']} ({p['tracks']['total']} songs)  [{p['uri']}]"
                                           for p in r.get("items", []) if p)


# ============================================================ playback (no question - harmless)
@_safe
def spotify_play(query: str = "", kind: str = "track", device: str = "") -> str:
    dev = _device(device)
    if not dev:
        raise _Err("NO_DEVICE")
    q = (query or "").strip()
    if not q:
        _api("PUT", "/me/player/play", {"device_id": dev})
        return "Resumed ▶️"
    if q.lower() in ("liked songs", "my liked songs", "liked", "my likes", "favourites", "favorites"):
        uris = [x["track"]["uri"] for x in _api("GET", "/me/tracks", {"limit": 50}).get("items", [])]
        _api("PUT", "/me/player/play", {"device_id": dev}, {"uris": uris})
        return "Playing your liked songs 💖"
    if q.startswith("spotify:"):
        body = {"uris": [q]} if ":track:" in q else {"context_uri": q}
        _api("PUT", "/me/player/play", {"device_id": dev}, body)
        return "Playing ▶️"
    # "my <playlist name>" -> one of his playlists first
    mine = [p for p in _api("GET", "/me/playlists", {"limit": 50}).get("items", []) if p]
    for p in mine:
        if p["name"].lower() == q.lower() or (kind == "playlist" and q.lower() in p["name"].lower()):
            _api("PUT", "/me/player/play", {"device_id": dev}, {"context_uri": p["uri"]})
            return f"Playing your playlist “{p['name']}” 🎶"
    kind = kind if kind in ("track", "album", "artist", "playlist") else "track"
    items = [i for i in _api("GET", "/search", {"q": q, "type": kind, "limit": 1}).get(kind + "s", {}).get("items", []) if i]
    if not items:
        return f"Couldn't find “{q}” on Spotify."
    it = items[0]
    body = {"uris": [it["uri"]]} if kind == "track" else {"context_uri": it["uri"]}
    _api("PUT", "/me/player/play", {"device_id": dev}, body)
    by = ", ".join(a["name"] for a in it.get("artists", []))
    return f"Playing {it['name']}" + (f" — {by}" if by else "") + " 🎵"


@_safe
def spotify_control(action: str, value: int = 0) -> str:
    a = (action or "").lower().replace(" ", "_")
    if a in ("pause", "stop"):
        _api("PUT", "/me/player/pause")
        return "Paused ⏸"
    if a in ("resume", "play"):
        _api("PUT", "/me/player/play")
        return "Resumed ▶️"
    if a in ("next", "skip"):
        _api("POST", "/me/player/next")
        return "Skipped ⏭"
    if a in ("previous", "back"):
        _api("POST", "/me/player/previous")
        return "Previous track ⏮"
    if a == "volume":
        v = max(0, min(int(value or 50), 100))
        _api("PUT", "/me/player/volume", {"volume_percent": v})
        return f"Spotify volume {v}% 🔊"
    if a in ("shuffle_on", "shuffle_off"):
        _api("PUT", "/me/player/shuffle", {"state": "true" if a == "shuffle_on" else "false"})
        return "Shuffle " + ("on 🔀" if a == "shuffle_on" else "off")
    if a in ("repeat_on", "repeat_one", "repeat_off"):
        st = {"repeat_on": "context", "repeat_one": "track", "repeat_off": "off"}[a]
        _api("PUT", "/me/player/repeat", {"state": st})
        return f"Repeat: {st}"
    return "Actions: pause, resume, next, previous, volume (value 0-100), shuffle_on/off, repeat_on/one/off."


@_safe
def spotify_transfer(device: str) -> str:
    dev = _device(device)
    if not dev:
        return "Can't find that Spotify device - is Spotify open on it?"
    _api("PUT", "/me/player", body={"device_ids": [dev], "play": True})
    return f"Music moved to {device} ✅"


# ============================================================ library changes (asks first)
@_safe
def spotify_like_current() -> str:
    p = _api("GET", "/me/player/currently-playing")
    if not p or not p.get("item"):
        return "Nothing is playing."
    _api("PUT", "/me/tracks", {"ids": p["item"]["id"]})
    return f"Added “{p['item']['name']}” to your Liked Songs 💖"


@_safe
def spotify_add_to_playlist(playlist: str, song: str = "") -> str:
    mine = [p for p in _api("GET", "/me/playlists", {"limit": 50}).get("items", []) if p]
    pl = next((p for p in mine if playlist.lower() in p["name"].lower()), None)
    if not pl:
        return f"No playlist called “{playlist}”."
    if song:
        items = _api("GET", "/search", {"q": song, "type": "track", "limit": 1}).get("tracks", {}).get("items", [])
        if not items:
            return f"Couldn't find “{song}”."
        uri, name = items[0]["uri"], items[0]["name"]
    else:
        cur = _api("GET", "/me/player/currently-playing")
        if not cur or not cur.get("item"):
            return "Nothing is playing - tell me which song."
        uri, name = cur["item"]["uri"], cur["item"]["name"]
    _api("POST", f"/playlists/{pl['id']}/tracks", body={"uris": [uri]})
    return f"Added “{name}” to {pl['name']} ✅"


def status() -> str:
    d = _load()
    if not d.get("client_id"):
        return "Spotify: not set up."
    return "Spotify: connected ✅" if _access() else "Spotify: not signed in (CONNECT-SPOTIFY.bat)."


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "connect":
        print(connect())
        print(spotify_now())
    else:
        print(status())
