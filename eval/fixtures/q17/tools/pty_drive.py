#!/usr/bin/env python3
"""Run one command under a pseudo-terminal, type into it, approve prompts, record everything.

Python stdlib only (Linux and macOS). Used by the graders to run a command-line
program exactly as a person would at a terminal, with a time limit:

  python3 pty_drive.py --out RUN/q1 --timeout 180 -- some-cli ask "question"
  python3 pty_drive.py --out RUN/r1 --timeout 600 --send "frozen request" \
      --approve '(?i)\\b(allow|approve|run this|proceed)\\b.*\\?' --approve-keys 'y\\r' \
      --done 'TOKEN-1234' --idle 20 --exit-keys '\\x04' -- some-tui

Outputs (PREFIX = --out):
  PREFIX.raw   every byte the program wrote to the terminal
  PREFIX.txt   the same with ANSI escape sequences removed and CR turned into LF
  PREFIX.json  summary: command, start/end epoch, elapsed, exit code, timed_out,
               what was typed and when, every approval sent, last_output_t
               (seconds from start to the last output; when the run ended by
               --done this, not elapsed, is the answer time: it leaves out the
               idle wait and the exit keys)

Typing rules:
  --send TEXT     typed once, followed by --send-enter (default CR), after
                  --send-after REGEX appears, or after --send-delay seconds
  --approve REGEX may be repeated; each time new output matches, --approve-keys
                  are typed (not more often than every --approve-cooldown s)
  --done REGEX    once it matches output that came after --send (or any output
                  when nothing is sent), wait for --idle s of silence, type
                  --exit-keys, wait --grace s, then end the process group
  --done-file F   the same, triggered when file F exists (e.g. a file the
                  program was asked to create)
  --no-pty        use plain pipes instead of a terminal (stdin gets --send or
                  --stdin-file, then EOF)
Keys accept Python escapes: \\r \\n \\t \\x04 (Ctrl-D) \\x03 (Ctrl-C) \\x1b (Esc).
"""

import argparse
import codecs
import json
import os
import re
import select
import signal
import struct
import subprocess
import sys
import time

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[PX^_][^\x1b]*\x1b\\|\x1b[@-Z\\-_]|\x1b[()][0-9A-Za-z]")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text):
    text = ANSI.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return CTRL.sub("", text)


def keys(s):
    return codecs.decode(s, "unicode_escape").encode("utf-8") if s else b""


def kill_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except OSError:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def wait_exit(pid, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return None
        if wpid == pid:
            return status
        time.sleep(0.05)
    return False


def decode_status(status):
    if status is None or status is False:
        return None, None
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status), None
    if os.WIFSIGNALED(status):
        return None, os.WTERMSIG(status)
    return None, None


def run_pty(a, cmd, summary, raw_out):
    import pty
    import fcntl
    import termios

    pid, fd = pty.fork()
    if pid == 0:
        try:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", a.rows, a.cols, 0, 0))
        except OSError:
            pass
        env = dict(os.environ)
        env.setdefault("TERM", "xterm-256color")
        env["COLUMNS"] = str(a.cols)
        env["LINES"] = str(a.rows)
        try:
            os.execvpe(cmd[0], cmd, env)
        except OSError as e:
            os.write(2, ("exec failed: %s\n" % e).encode())
            os._exit(127)

    start = summary["start"]
    text = ""
    approve_from = 0
    last_approve = 0.0
    sent = a.send is None
    send_pos = 0
    done_at = None
    last_output = time.time()
    exit_sent = None
    status = None
    approve_rx = [re.compile(r) for r in a.approve]
    send_after = re.compile(a.send_after) if a.send_after else None
    done_rx = re.compile(a.done) if a.done else None
    done_file = a.done_file

    def type_(data, what):
        try:
            os.write(fd, data)
        except OSError:
            return
        summary["typed"].append({"t": round(time.time() - start, 3), "what": what})

    while True:
        now = time.time()
        if now - start > a.timeout:
            summary["timed_out"] = True
            break
        try:
            r, _, _ = select.select([fd], [], [], 0.2)
        except (OSError, ValueError):
            break
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            raw_out.write(chunk)
            raw_out.flush()
            text += clean(chunk.decode("utf-8", "replace"))
            last_output = time.time()
            summary["last_output_t"] = round(last_output - start, 3)
        else:
            wpid, st = os.waitpid(pid, os.WNOHANG)
            if wpid == pid:
                status = st
                break

        if not sent:
            ready = False
            if send_after is not None:
                ready = bool(send_after.search(text))
            elif time.time() - start >= a.send_delay:
                ready = True
            if ready:
                send_pos = len(text)
                type_(a.send.encode("utf-8"), "send")
                time.sleep(0.1)
                type_(keys(a.send_enter), "send-enter")
                sent = True

        if approve_rx and time.time() - last_approve >= a.approve_cooldown:
            tail = text[approve_from:]
            for rx in approve_rx:
                m = rx.search(tail)
                if m:
                    approve_from += m.end()
                    last_approve = time.time()
                    summary["approvals"].append({"t": round(last_approve - start, 3),
                                                 "matched": m.group(0)[-200:]})
                    type_(keys(a.approve_keys), "approve")
                    break

        if done_rx is not None and sent and done_at is None:
            if done_rx.search(text[send_pos:]):
                done_at = time.time()
                summary["done_matched_t"] = round(done_at - start, 3)
        if done_file and sent and done_at is None and os.path.exists(done_file):
            done_at = time.time()
            summary["done_matched_t"] = round(done_at - start, 3)
        if done_at is not None and exit_sent is None and time.time() - last_output >= a.idle:
            type_(keys(a.exit_keys), "exit-keys")
            exit_sent = time.time()
        if exit_sent is not None and time.time() - exit_sent >= a.grace:
            summary["ended_by"] = "done"
            break

    if status is None:
        st = wait_exit(pid, 0.5)
        if st is False:
            kill_group(pid, signal.SIGTERM)
            st = wait_exit(pid, 3)
            if st is False:
                kill_group(pid, signal.SIGKILL)
                st = wait_exit(pid, 3)
        status = st if st is not False else None
    # drain what is left
    try:
        while True:
            r, _, _ = select.select([fd], [], [], 0.1)
            if not r:
                break
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            raw_out.write(chunk)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    return status


def run_pipes(a, cmd, summary, raw_out):
    data = b""
    if a.stdin_file:
        with open(a.stdin_file, "rb") as f:
            data = f.read()
    elif a.send is not None:
        data = a.send.encode("utf-8") + b"\n"
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True)
    try:
        out, _ = p.communicate(data, timeout=a.timeout)
    except subprocess.TimeoutExpired:
        summary["timed_out"] = True
        kill_group(p.pid, signal.SIGTERM)
        try:
            out, _ = p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            kill_group(p.pid, signal.SIGKILL)
            out, _ = p.communicate()
    raw_out.write(out or b"")
    if data:
        summary["typed"].append({"t": 0.0, "what": "stdin"})
    rc = p.returncode
    if rc is None:
        return None
    if rc < 0:
        return ("signal", -rc)
    return ("exit", rc)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output prefix")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--send")
    ap.add_argument("--send-file", help="read the text to --send from this file (trailing newline removed)")
    ap.add_argument("--send-after")
    ap.add_argument("--send-delay", type=float, default=2.0)
    ap.add_argument("--send-enter", default="\\r")
    ap.add_argument("--approve", action="append", default=[])
    ap.add_argument("--approve-keys", default="y\\r")
    ap.add_argument("--approve-cooldown", type=float, default=1.5)
    ap.add_argument("--done")
    ap.add_argument("--done-file")
    ap.add_argument("--idle", type=float, default=15.0)
    ap.add_argument("--exit-keys", default="\\x04")
    ap.add_argument("--grace", type=float, default=5.0)
    ap.add_argument("--no-pty", action="store_true")
    ap.add_argument("--stdin-file")
    ap.add_argument("--cols", type=int, default=120)
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        ap.error("give the command after --")
    if a.send_file:
        with open(a.send_file, encoding="utf-8") as f:
            a.send = f.read().rstrip("\n")

    d = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(d, exist_ok=True)
    summary = {"cmd": cmd, "start": time.time(), "timeout": a.timeout, "pty": not a.no_pty,
               "timed_out": False, "typed": [], "approvals": [], "ended_by": "exit"}
    with open(a.out + ".raw", "wb") as raw_out:
        if a.no_pty:
            res = run_pipes(a, cmd, summary, raw_out)
            code = res[1] if res and res[0] == "exit" else None
            sig = res[1] if res and res[0] == "signal" else None
        else:
            code, sig = decode_status(run_pty(a, cmd, summary, raw_out))
    summary["end"] = time.time()
    summary["elapsed"] = round(summary["end"] - summary["start"], 3)
    summary["exit_code"] = code
    summary["signal"] = sig
    if summary["timed_out"]:
        summary["ended_by"] = "timeout"
    with open(a.out + ".raw", "rb") as f:
        raw = f.read()
    with open(a.out + ".txt", "w", encoding="utf-8") as f:
        f.write(clean(raw.decode("utf-8", "replace")))
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: summary[k] for k in ("elapsed", "exit_code", "signal", "timed_out", "ended_by")}))
    return 0 if (code == 0 and not summary["timed_out"]) else 1


if __name__ == "__main__":
    sys.exit(main())
