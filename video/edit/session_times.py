"""Print a time line of a Claude Code session log (user turns, tool calls, results) in local time.

    python3 edit/session_times.py ~/.claude/projects/-Users-ncchen-pickfit-demo/<id>.jsonl
"""
import json, sys
from datetime import datetime

for path in sys.argv[1:]:
    print("==", path.split("/")[-1])
    for line in open(path):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        ts = e.get("timestamp")
        if not ts or e.get("type") not in ("user", "assistant"):
            continue
        t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
        msg = e.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            print(t, "USER", content[:90].replace("\n", " "))
            continue
        for c in content or []:
            k = c.get("type")
            if k == "text" and c.get("text", "").strip():
                print(t, e["type"].upper()[:4], c["text"][:90].replace("\n", " "))
            elif k == "tool_use":
                inp = c.get("input") or {}
                print(t, "CALL", c.get("name"), json.dumps(inp)[:110])
            elif k == "tool_result":
                r = c.get("content")
                r = r if isinstance(r, str) else json.dumps(r)
                print(t, "RSLT", ("ERR " if c.get("is_error") else "") + r[:80].replace("\n", " "))
