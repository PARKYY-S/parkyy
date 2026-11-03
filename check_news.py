"""Test PARKYY's news reading right now (no brain needed). Shows which sources work."""
from world import World, STATUS
w = World(None, "", None)
new = w.refresh()
print(STATUS.read_text(encoding="utf-8"))
print(f"{len(new)} new headlines saved. A few of them:")
for i in new[:8]:
    print(f"  - [{i['topic']}] {i['title']}")
