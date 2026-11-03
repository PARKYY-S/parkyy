"""
Keep the laptop awake while PARKYY is running, so your phone can always
reach it (a sleeping laptop can't answer).

Uses Windows' own "please don't sleep" flag (SetThreadExecutionState) - the
same thing media players use so the PC doesn't sleep mid-movie. It only lasts
while PARKYY runs; close PARKYY and normal sleep behaviour returns. The screen
is still allowed to turn off (that saves power and doesn't affect the phone).

Note: this stops *idle* sleep. If you physically CLOSE the laptop lid, Windows
may still sleep unless you set "When I close the lid: Do nothing" in
Control Panel > Power Options (one-time, optional - good for travel).

Turn it off with PARKYY_STAY_AWAKE=0 in .env.
"""

import os
import threading
import time

# Windows flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

_on = False
_thread = None


def _keep():
    import ctypes
    while _on:
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        except Exception:
            return
        time.sleep(50)
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # release
    except Exception:
        pass


def start():
    global _on, _thread
    if os.name != "nt" or _on:
        return
    if os.environ.get("PARKYY_STAY_AWAKE", "1") == "0":
        return
    _on = True
    _thread = threading.Thread(target=_keep, daemon=True)
    _thread.start()


def stop():
    global _on
    _on = False


def set_on(value: bool) -> str:
    if value:
        start()
        return "Stay-awake on: I'll keep the laptop from sleeping so you can reach me while you're away."
    stop()
    return "Stay-awake off: the laptop can sleep normally now."


def status() -> bool:
    return _on
