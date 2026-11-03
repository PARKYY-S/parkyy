"""
PARKYY v1.2 challenge suite - harder, HIDDEN tests on top of the 13 core (regression) tests.

Every run picks a fresh random set from a pool, and most questions are generated with random numbers/names,
so the exact questions are never the same twice - PARKYY can't get good at "the benchmark", only at the skill.

  reasoning  multi-step logic / arithmetic puzzles (answer checked exactly)
  coding     read code / spot what a buggy function really returns (answer computed by Python itself)
  planning   scheduling under constraints (answer computed)
  research   facts that must be looked up on the web (must use a web tool AND get it right)
  mission    real file task in a fresh test folder: EXECUTION (did it act?) and CORRECTNESS (was it right?)
             are scored separately - "moved the file" isn't success if it moved the wrong one.
"""
import random
import re
import string
import time
from pathlib import Path

WIN = __import__("os").name == "nt"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NAMES = ["Aisha", "Bilal", "Chen", "Dina", "Eli", "Farah", "Gopal", "Hana", "Ivan", "Jaya", "Karim", "Lena"]


def _num(r: str, want) -> bool:
    """Does the reply contain exactly this number (not as part of a longer number)?"""
    w = re.escape(str(want))
    return bool(re.search(rf"(?<![\d.]){w}(?![\d]|\.\d)", r.replace(",", "")))


# ------------------------------------------------------------------ reasoning
def r_order(rng):
    a, b, c, d = rng.sample(NAMES, 4)
    facts = [f"{a} is older than {b}", f"{c} is younger than {b}", f"{d} is older than {a}"]
    rng.shuffle(facts)
    q = ". ".join(facts) + ". Who is the second oldest? Reply with just the name."
    return q, a, lambda r: bool(re.search(rf"\b{a}\b", r)) and not re.search(rf"\b({b}|{c}|{d})\b", r.split("\n")[0])


def r_days(rng):
    start, n = rng.randrange(7), rng.randint(40, 400)
    ans = DAYS[(start + n) % 7]
    return (f"Today is {DAYS[start]}. What day of the week will it be {n} days from today? Reply with just the day.",
            ans, lambda r: ans.lower() in r.lower() and sum(d.lower() in r.lower() for d in DAYS) == 1)


def r_pipes(rng):
    a, b, ans = rng.choice([(3, 6, 2), (4, 12, 3), (6, 12, 4), (10, 15, 6), (12, 24, 8), (20, 30, 12)])
    return (f"Pipe A fills a tank in {a} hours, pipe B fills it in {b} hours. Both run together from empty. "
            f"How many hours to fill it? Reply with just the number.", ans, lambda r: _num(r, ans))


def r_train(rng):
    h, m = rng.randint(19, 23), rng.choice([5, 15, 20, 35, 40, 50])
    dh, dm = rng.randint(2, 7), rng.choice([10, 25, 45, 55])
    t = (h * 60 + m + dh * 60 + dm) % (24 * 60)
    ans = f"{t // 60:02d}:{t % 60:02d}"
    return (f"A train leaves at {h:02d}:{m:02d} and the journey takes {dh} hours {dm} minutes. "
            f"At what time does it arrive (24-hour clock, HH:MM)? Reply with just the time.",
            ans, lambda r: ans in r.replace(".", ":"))


def r_boxes(rng):
    k, red, blue = rng.choice([4, 6, 8, 10]), rng.randint(2, 9), rng.randint(2, 9)
    ans = k * red + (k // 2) * blue
    return (f"There are {k} boxes, each with {red} red and {blue} blue balls. I take ALL the blue balls out of half "
            f"of the boxes and throw them away. How many balls are left in total? Reply with just the number.",
            ans, lambda r: _num(r, ans))


# ------------------------------------------------------------------ coding (answers computed by running the code)
def _run(code: str):
    out = []
    exec(code, {"print": lambda *a: out.append(" ".join(map(str, a)))})
    return out[-1]


def c_slice(rng):
    a, b, c = rng.randint(1, 9), rng.randint(20, 40), rng.randint(2, 5)
    code = f"print(list(range({a}, {b}, {c}))[::-1][:3])"
    ans = _run(code)
    nums = re.findall(r"\d+", ans)
    return (f"Without running it, what does this Python print?\n{code}\nReply with just the output.",
            ans, lambda r: re.findall(r"\d+", r)[:3] == nums)


def c_lambda(rng):
    k = rng.randint(3, 9)
    code = f"fs = [lambda: i for i in range({k})]\nprint(fs[0]() + fs[1]())"
    ans = _run(code)
    return (f"Without running it, what does this Python print?\n{code}\nReply with just the number.",
            ans, lambda r: _num(r, ans))


def c_bug(rng):
    xs = rng.sample(range(2, 30), rng.randint(4, 6))
    code = f"def avg(xs):\n    return sum(xs) // (len(xs) - 1)\nprint(avg({xs}))"
    ans = _run(code)
    return (f"This function is meant to return the average but has a bug. Without running it, what does it ACTUALLY "
            f"print?\n{code}\nReply with the number first, then one line saying what the bug is.",
            ans, lambda r: _num(r.split("\n")[0], ans) or (_num(r, ans) and "len" in r))


def c_fib(rng):
    n = rng.randint(11, 19)
    code = f"def f(n):\n    return n if n < 2 else f(n - 1) + f(n - 2)\nprint(f({n}))"
    ans = _run(code)
    return (f"Without running it, what does this Python print?\n{code}\nReply with just the number.",
            ans, lambda r: _num(r, ans))


def c_dict(rng):
    w = "".join(rng.choice("parkyybrain") for _ in range(9))
    code = f"d = {{}}\nfor ch in '{w}':\n    d[ch] = d.get(ch, 0) + 1\nprint(max(d.values()))"
    ans = _run(code)
    return (f"Without running it, what does this Python print?\n{code}\nReply with just the number.",
            ans, lambda r: _num(r, ans))


# ------------------------------------------------------------------ planning
def p_chain(rng):
    s = rng.choice([8, 9, 10, 13])
    x, y, z = rng.randint(20, 70), rng.randint(15, 50), rng.randint(25, 80)
    t = s * 60 + x + y + z
    ans = f"{t // 60:02d}:{t % 60:02d}"
    return (f"Three tasks: A takes {x} min, B takes {y} min, C takes {z} min. B can only start after A finishes, "
            f"C only after B finishes. A starts at {s:02d}:00. At what time does C finish (HH:MM)? Reply with just the time.",
            ans, lambda r: ans in r.replace(".", ":"))


def p_fit(rng):
    slot = rng.choice([90, 120, 150])
    ms = [rng.choice([20, 30, 45]) for _ in range(3)]
    need = sum(ms) + 2 * 15
    fits = need <= slot
    return (f"I have a free slot of {slot} minutes and three meetings of {ms[0]}, {ms[1]} and {ms[2]} minutes. "
            f"I need a 15-minute break between meetings (none before the first or after the last). Can all three fit? "
            f"Start your reply with yes or no.", "yes" if fits else "no",
            lambda r: r.strip().lower().lstrip("*# ").startswith("yes" if fits else "no"))


# ------------------------------------------------------------------ research (needs the web)
FACTS = [
    ("In what year was Python 3.0 released?", "2008"),
    ("What is the height of the Burj Khalifa in metres (rounded to the nearest metre)?", "828"),
    ("In what year was the Linux kernel first released?", "1991"),
    ("In what year was Wikipedia launched?", "2001"),
    ("What is the atomic number of tungsten?", "74"),
    ("In what year did the first iPhone go on sale?", "2007"),
    ("How many bones are in the adult human body?", "206"),
]


def s_fact(rng):
    q, ans = rng.choice(FACTS)
    return (f"Look this up on the web (use your web search tool, don't answer from memory): {q} "
            f"Reply with just the answer.", ans, lambda r: _num(r, ans))


POOL = {"reasoning": [r_order, r_days, r_pipes, r_train, r_boxes],
        "coding": [c_slice, c_lambda, c_bug, c_fib, c_dict],
        "planning": [p_chain, p_fit],
        "research": [s_fact]}
PICK = {"reasoning": 2, "coding": 2, "planning": 1, "research": 1}


def draw(seed=None) -> list[dict]:
    """A fresh hidden set for this run."""
    rng = random.Random(seed if seed is not None else time.time_ns())
    out = []
    for cat, n in PICK.items():
        for gen in rng.sample(POOL[cat], min(n, len(POOL[cat]))):
            q, ans, check = gen(rng)
            out.append({"cat": cat, "id": gen.__name__, "q": q, "expect": str(ans), "check": check})
    return out


# ------------------------------------------------------------------ the real-file mission
def make_mission_folder(root: Path, rng=None) -> tuple[Path, str, str]:
    """Fresh folder with 5 files of random sizes. Returns (folder, largest file name, note tag)."""
    rng = rng or random.Random(time.time_ns())
    tag = "".join(rng.choice(string.ascii_lowercase) for _ in range(5))
    folder = root / f"challenge-{tag}"
    folder.mkdir(parents=True, exist_ok=True)
    sizes = rng.sample(range(20, 400), 5)
    names = [f"{rng.choice(['report', 'photo', 'backup', 'notes', 'video', 'draft', 'export'])}-{rng.randint(100, 999)}"
             f".{rng.choice(['bin', 'dat', 'tmp', 'log'])}" for _ in range(5)]
    for nm, kb in zip(names, sizes):
        (folder / nm).write_bytes(b"0" * kb * 1024)
    largest = names[sizes.index(max(sizes))]
    return folder, largest, tag
