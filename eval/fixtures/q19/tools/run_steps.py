#!/usr/bin/env python3
"""Type an answer's shell commands, unchanged and in order, into one terminal session (stdlib only).

This is how the graders run "the install steps verbatim": like a person pasting
each command into the same terminal and waiting for it to finish.

  python3 run_steps.py --steps steps.txt --out RUN/install [--accept '(?i)\\[Y/n\\]'] [--step-timeout 600] [--total-timeout 1200]

steps.txt holds the answer's commands copied character for character, in order:
  - one command per line; a line ending in a backslash continues on the next
    line, and a heredoc (<<WORD ... WORD) stays together, as in a terminal;
  - blank lines and lines starting with "# " are skipped (the grader's notes);
  - a line that is exactly "#NEW_SHELL" closes the session and opens a new
    login shell (only where the answer says to open a new terminal or re-login).

The session is `bash --login -i` in a pseudo-terminal. After it starts, the
prompt is set to a marker that carries the last exit code, and each command is
typed only after the previous prompt came back. Installer questions that match
--accept get --accept-keys (default: Enter, i.e. take the installer's default).
The run stops at the first command that exits non-zero or times out.

Outputs: OUT.raw / OUT.txt (whole transcript), OUT.json (per command: text,
exit code, seconds, timed_out; plus overall "all_ok"). Exit 0 when all_ok.
"""

import argparse
import codecs
import json
import os
import re
import select
import signal
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pty_drive import clean  # noqa: E402

MARK = re.compile(r"__STEP_RC_(\d+)__")
SET_PROMPT = "PROMPT_COMMAND=; PS2=; PS1='__STEP_RC_$?__$ '"


def parse_steps(text):
    steps, buf, heredoc = [], [], None
    for line in text.splitlines():
        if heredoc is not None:
            buf.append(line)
            if line.strip() == heredoc:
                heredoc = None
                steps.append("\n".join(buf))
                buf = []
            continue
        if not buf and (not line.strip() or line.startswith("# ")):
            continue
        if not buf and line.strip() == "#NEW_SHELL":
            steps.append("#NEW_SHELL")
            continue
        buf.append(line)
        m = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if m:
            heredoc = m.group(1)
            continue
        if line.endswith("\\"):
            continue
        steps.append("\n".join(buf))
        buf = []
    if buf:
        steps.append("\n".join(buf))
    return steps


class Session(object):
    def __init__(self, a, raw):
        import pty
        import fcntl
        import termios
        self.a = a
        self.raw = raw
        self.text = ""
        pid, fd = pty.fork()
        if pid == 0:
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 160, 0, 0))
            except OSError:
                pass
            env = dict(os.environ)
            env.setdefault("TERM", "xterm-256color")
            os.execvpe(a.shell, [a.shell, "--login", "-i"], env)
        self.pid, self.fd = pid, fd
        self.accept = [re.compile(r) for r in a.accept]

    def read_for(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.1)
            if not r:
                continue
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                return False
            if not chunk:
                return False
            self.raw.write(chunk)
            self.raw.flush()
            self.text += clean(chunk.decode("utf-8", "replace"))
        return True

    def write(self, s):
        os.write(self.fd, s.encode("utf-8") if isinstance(s, str) else s)

    def wait_mark(self, start_pos, timeout):
        end = time.time() + timeout
        accepted_to = start_pos
        last_accept = 0.0
        while time.time() < end:
            if not self.read_for(0.3):
                return None, "shell exited"
            m = MARK.search(self.text, start_pos)
            if m:
                return int(m.group(1)), m.end()
            if self.accept and time.time() - last_accept > 1.0:
                tail = self.text[accepted_to:]
                for rx in self.accept:
                    mm = rx.search(tail)
                    if mm:
                        accepted_to += mm.end()
                        last_accept = time.time()
                        self.write(codecs.decode(self.a.accept_keys, "unicode_escape"))
                        break
        return None, "timeout"

    def start(self):
        self.read_for(1.0)
        pos = len(self.text)
        self.write(SET_PROMPT + "\r")
        rc, end = self.wait_mark(pos, 30)
        if rc is None:
            raise SystemExit("could not set the marker prompt: %s" % end)
        return end

    def close(self):
        try:
            self.write("exit\r")
            self.read_for(1.0)
        except OSError:
            pass
        try:
            os.killpg(self.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            os.waitpid(self.pid, 0)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shell", default="bash")
    ap.add_argument("--accept", action="append", default=[])
    ap.add_argument("--accept-keys", default="\\r")
    ap.add_argument("--step-timeout", type=float, default=600.0)
    ap.add_argument("--total-timeout", type=float, default=1200.0)
    ap.add_argument("--keep-going", action="store_true", help="do not stop at the first failing command")
    a = ap.parse_args()
    with open(a.steps, encoding="utf-8") as f:
        steps = parse_steps(f.read())
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    rec = {"steps_file": os.path.abspath(a.steps), "start": time.time(), "steps": []}
    t0 = time.time()
    with open(a.out + ".raw", "wb") as raw:
        s = Session(a, raw)
        pos = s.start()
        for cmd in steps:
            if cmd == "#NEW_SHELL":
                s.close()
                s = Session(a, raw)
                pos = s.start()
                rec["steps"].append({"cmd": cmd, "exit_code": 0, "seconds": 0})
                continue
            left = a.total_timeout - (time.time() - t0)
            if left <= 0:
                rec["steps"].append({"cmd": cmd, "skipped": "total timeout"})
                break
            ts = time.time()
            s.write(cmd.replace("\n", "\r") + "\r")
            rc, end = s.wait_mark(pos, min(a.step_timeout, left))
            step = {"cmd": cmd, "seconds": round(time.time() - ts, 2)}
            if rc is None:
                step.update({"exit_code": None, "timed_out": end == "timeout", "problem": end})
                rec["steps"].append(step)
                try:
                    s.write("\x03")
                except OSError:
                    pass
                break
            step["exit_code"] = rc
            step["output"] = s.text[pos:end][-4000:]
            pos = end
            rec["steps"].append(step)
            if rc != 0 and not a.keep_going:
                break
        s.close()
    rec["end"] = time.time()
    rec["elapsed"] = round(rec["end"] - rec["start"], 2)
    ran = [x for x in rec["steps"] if "skipped" not in x]
    rec["all_ok"] = len(ran) == len(steps) and all(x.get("exit_code") == 0 for x in ran)
    with open(a.out + ".raw", "rb") as f:
        txt = clean(f.read().decode("utf-8", "replace"))
    with open(a.out + ".txt", "w", encoding="utf-8") as f:
        f.write(txt)
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    print(json.dumps({"all_ok": rec["all_ok"], "steps": len(steps), "ran": len(ran), "elapsed": rec["elapsed"]}))
    return 0 if rec["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
