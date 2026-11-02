"""Launch a GUI app on the box's virtual display and record how far it got (Linux).

The app runs as the box user; everything that produces evidence does not.
Root starts Xvfb as DISPLAY_UID (no window manager, no GPU, no TCP): the box
user can draw on it but cannot kill or replace it. A launch is five steps,
each its own command:

1. DISPLAY_UID lists the box user's processes (the "before" set).
2. The box user starts the app, detached, with DISPLAY set; its output goes to
   a log in the box user's home (the app's own data, never parsed as a result).
3. DISPLAY_UID runs the watcher (stdin, image python, absolute paths, empty
   environment): it waits for a window whose X client the X server says is a
   box-user process that was not in the "before" set (XRes client PIDs, not
   _NET_WM_PID), lets it settle, checks that pickfit's own Xvfb is still the
   server, screenshots the display into EVIDENCE_DIR (mode 0700) and prints
   one report line tagged with a nonce only pickfit knows, on its own stdout.
4. Root stops every box-user process (SIGSTOP, then SIGKILL, until none is
   left): the app cannot survive by double-forking or leaving its session.
5. Root copies the screenshot out and checks it against the size and hash
   the watcher reported.

Evidence tiers, weakest to strongest (see docs/brief.md; app stores stop at
install, signing and malware checks):

  none           the app exited before showing anything
  process_alive  still running after the wait, but no window of its own
  window         a mapped window of its own, at least MIN_WIDTH x MIN_HEIGHT on screen
  ui_rendered    the screen judge read a crop of the app's windows and saw its own UI
  action_checked actions pickfit performed made a result pickfit checked itself (gui_operate.py)

A launch reaches at most `window`; ui_rendered comes from the screen judge on
the replay's screenshot. A launch alone supports level install only; operate
(gui_operate.py) keeps the app running after its window shows, performs the
actions a model picks from screenshots and checks the result: a run with such
a check of a listed feature supports function (action_checked).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shlex
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from pickfit.env import get_env
from pickfit.verify.box import BOX_HOME, ExecResult

if TYPE_CHECKING:
    from pickfit.verify.box import Box

DISPLAY = ":99"


def full_desktop(value: str | None) -> bool:
    """PICKFIT_GUI_DESKTOP: unset (pickfit's usual display) or full; any other value is refused when read."""
    if value not in (None, "", "full"):
        raise ValueError(f"PICKFIT_GUI_DESKTOP must be unset or full, got {value!r}")
    return value == "full"


# A comparison only (scripts/gui_compare.py, arm A), off unless PICKFIT_GUI_DESKTOP=full: what desktop features'
# notes said the display lacked. A 1920x1080 screen; the app started on its own session bus with the desktop
# portal's GTK backend (the file chooser a Flatpak app asks for, and OpenURI); a default app for text files.
FULL_DESKTOP = full_desktop(get_env("PICKFIT_GUI_DESKTOP"))
SCREEN = "1920x1080x24" if FULL_DESKTOP else "1280x800x24"
SCREEN_W, SCREEN_H = (1920, 1080) if FULL_DESKTOP else (1280, 800)
DISPLAY_NOTE = f"Xvfb {SCREEN}, no window manager, no GPU" + (", session bus and portal" if FULL_DESKTOP else "")
DISPLAY_UID = 1001  # Xvfb and the watcher: not the box user (1000), not root
EVIDENCE_DIR = "/var/lib/pickfit-gui"  # DISPLAY_UID's, mode 0700: the box user cannot list, read or write it
HARNESS_PATH = "/usr/bin:/bin"  # root-owned directories only
PYTHON = "/usr/local/bin/python3"
APP_LOG_DIR = f"{BOX_HOME}/.pickfit-gui"
# What the display needs, and the shared libraries Electron and Tauri apps load
# (chromium brings GTK, NSS, GBM and ALSA). Installed on top of sandbox.Dockerfile.
# python3-tk brings Debian's own /usr/bin/python3 with tkinter: the image's python3.12 has none.
# xdotool and xclip: the display uid's hands (XTEST input) and its reading of the clipboard (gui_operate.py).
# ffmpeg: the display uid's screen recording of an operation (record.py).
GUI_PACKAGES = ("xvfb", "x11-utils", "x11-apps", "xrestop", "imagemagick", "chromium",
                "libwebkit2gtk-4.1-0", "fonts-dejavu-core", "python3-tk", "python3-venv", "xdotool", "xclip", "ffmpeg")
DESKTOP_PACKAGES = ("dbus", "dbus-x11", "xdg-desktop-portal", "xdg-desktop-portal-gtk", "xdg-utils", "mousepad")
if FULL_DESKTOP:
    GUI_PACKAGES = (*GUI_PACKAGES, *DESKTOP_PACKAGES)
TIERS = ("none", "process_alive", "window", "ui_rendered", "action_checked")
WAIT_MAX_S = 60
SETTLE_S = 6  # after the first window, so a page that loads after the window shows still renders
BLANK_WAIT_S = 20  # then, while the app's largest window is one flat color (not painted yet), at most this long
MIN_WIDTH, MIN_HEIGHT = 150, 100  # on-screen size of a window that counts (helper and offscreen ones do not)
SHOT_MAX_BYTES = 4_000_000
SHOT_READS = 3  # a long read can come back short when the box's output stream is slow (2026-10-31)
MARK = "PICKFIT_GUI_"


def xvfb_script(filter_argv: tuple[str, ...] = (), enter_argv: tuple[str, ...] = ()) -> str:
    """Root: the evidence directory, then Xvfb as DISPLAY_UID (under the box's seccomp filter, if any: it
    parses what the app sends; in the display's own network namespace, if root gives one: a box-user X
    request can make it resolve and reach a font server); prints `xvfb_pid N` once it answers. The box
    user's apps reach it by its socket file in /tmp/.X11-unix, which a network namespace does not hide."""
    drop = (f"{' '.join(enter_argv)} /usr/bin/setpriv --reuid={DISPLAY_UID} --regid={DISPLAY_UID} --clear-groups "
            f"--inh-caps=-all --no-new-privs -- {' '.join(filter_argv)} /usr/bin/env -i PATH={HARNESS_PATH} "
            f"HOME={EVIDENCE_DIR}")
    return (f"/usr/bin/install -d -m 0700 -o {DISPLAY_UID} -g {DISPLAY_UID} {EVIDENCE_DIR} && "
            "/usr/bin/install -d -m 1777 -o root -g root /tmp/.X11-unix && "
            f"{{ /usr/bin/setsid {drop} /usr/bin/Xvfb {DISPLAY} -screen 0 {SCREEN} -nolisten tcp "
            f"< /dev/null > {EVIDENCE_DIR}/xvfb.log 2>&1 & }}; "
            f"for i in $(/usr/bin/seq 1 40); do {drop} DISPLAY={DISPLAY} /usr/bin/xdpyinfo > /dev/null 2>&1 && "
            f"{{ echo \"xvfb_pid $(/usr/bin/pgrep -u {DISPLAY_UID} -x Xvfb)\"; exit 0; }}; /usr/bin/sleep 0.25; done; "
            f"/usr/bin/tail -5 {EVIDENCE_DIR}/xvfb.log; exit 1")


# Shared by the snapshot, the watcher and the stop: the box user's live processes as {pid: [starttime, comm]}.
# Read as bytes, one pid at a time: a process name is the app's (PR_SET_NAME can make it any bytes), and one
# odd process must not stop the list. Its real or effective uid decides, from /proc/<pid>/status.
_PROCS = r"""
import json, os, re, subprocess, sys, time, hashlib
BOX_UID = b"1000"
def procs():
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            status = open(f"/proc/{d}/status", "rb").read()
        except Exception:
            continue
        uid = re.search(rb"^Uid:\s+(\d+)\s+(\d+)", status, re.M)
        state = re.search(rb"^State:\s+(\S)", status, re.M)
        if not uid or BOX_UID not in uid.groups() or (state and state.group(1) == b"Z"):
            continue
        start, name = "?", "?"
        try:
            stat = open(f"/proc/{d}/stat", "rb").read()
            start = stat[stat.rindex(b")") + 2:].split()[19].decode("ascii")
            name = stat[stat.index(b"(") + 1:stat.rindex(b")")].decode("utf-8", "replace")
        except Exception:
            pass
        out[d] = [start, name]
    return out
"""

SNAPSHOT_PY = _PROCS + "\nprint(json.dumps(procs()))\n"

# Root: stop every box-user process until none is left (zombies are already dead).
KILL_PY = _PROCS + r"""
import signal
for round_ in range(200):
    left = procs()
    if not left:
        print("PICKFIT_KILLED", round_)
        break
    for sig in (signal.SIGSTOP, signal.SIGKILL):
        for pid in left:
            try:
                os.kill(int(pid), sig)
            except Exception:
                pass
    time.sleep(0.05)
else:
    print("PICKFIT_KILL_FAILED", sorted(procs()))
    sys.exit(1)
"""

# DISPLAY_UID: the watcher. Placeholders are filled in per launch (never from the app).
_WATCH = r"""
ENV = {"PATH": "/usr/bin:/bin", "DISPLAY": "@DISPLAY@", "LANG": "C.UTF-8"}
BEFORE, XVFB, NONCE, SHOT = @BEFORE@, @XVFB@, "@NONCE@", "@SHOT@"
WAIT_S, SETTLE_S, MIN_W, MIN_H, SW, SH, BLANK_S = @WAIT@, @SETTLE@, @MIN_W@, @MIN_H@, @SW@, @SH@, @BLANK@
def run(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=20, env=ENV).stdout
    except Exception:
        return ""
def our_server():
    try:
        status = open(f"/proc/{XVFB}/status").read()
    except OSError:
        return False
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    return fields.get("Name", "").strip() == "Xvfb" and fields.get("Uid", "").split()[:1] == ["@UID@"]
def app():
    now = procs()
    return {p: v for p, v in now.items() if BEFORE.get(p, [None])[0] != v[0]}
def clients():
    found, cur = [], None
    for line in run(["/usr/bin/xrestop", "-b", "-m", "1"]).splitlines():
        head = re.match(r"^\d+ - (.*) \(\s*PID:\s*(\d*)\s*\):", line)
        if head:
            cur = {"name": head.group(1), "pid": head.group(2)}
            found.append(cur)
            continue
        kv = re.match(r"^\s*(res[_-]base|res[_-]mask)\s*:\s*(0x[0-9a-fA-F]+)", line)
        if kv and cur is not None:
            cur[kv.group(1).replace("-", "_")] = int(kv.group(2), 16)
    return found
def windows():
    # Ids only from the root's children (each line starts with one); every other fact comes from the window's
    # own xwininfo, by label. Its first line holds the title, which the app sets to anything (newlines too):
    # a label seen twice means the title forged lines, and the window does not count.
    found = []
    ids = [m.group(1) for m in (re.match(r"^\s+(0x[0-9a-f]+)\s", line) for line in
                                run(["/usr/bin/xwininfo", "-root", "-children"]).splitlines()) if m]
    for wid in dict.fromkeys(ids):
        lines = run(["/usr/bin/xwininfo", "-id", wid]).splitlines()
        def field(label):
            values = [l.split(":", 1)[1].strip() for l in lines if l.strip().startswith(label + ":")]
            return values[0] if len(values) == 1 else None
        geo = [field(k) for k in ("Absolute upper-left X", "Absolute upper-left Y", "Width", "Height")]
        if field("Map State") != "IsViewable" or not all(v and re.fullmatch(r"-?\d+", v) for v in geo):
            continue
        x, y, w, h = (int(v) for v in geo)
        head = next((m for m in (re.match(r'^xwininfo: Window id: 0x[0-9a-f]+ "(.*)"$', l) for l in lines) if m),
                    None)
        vw, vh = min(x + w, SW) - max(x, 0), min(y + h, SH) - max(y, 0)
        found.append({"id": wid, "title": (head.group(1) if head else "")[:200], "width": w, "height": h, "x": x,
                      "y": y, "visible": vw >= MIN_W and vh >= MIN_H})
    return found
def look():
    mine = app()
    cls, own, other = clients(), [], []
    for w in windows():
        wid = int(w["id"], 16)
        c = next((c for c in cls if "res_base" in c and "res_mask" in c and (wid & ~c["res_mask"]) == c["res_base"]),
                 None)
        w["pid"] = int(c["pid"]) if c and c["pid"] else None
        w["client"] = c["name"][:80] if c else None
        (own if c and c["pid"] in mine and w.pop("visible") else other).append(w)
        w.pop("visible", None)
    return mine, own, other
def blank(own):
    # The largest own window drawn in one flat color (a Tauri or Electron window before it paints): keep waiting.
    if not own:
        return False
    w = max(own, key=lambda w: w["width"] * w["height"])
    x, y = max(0, w["x"]), max(0, w["y"])
    cw, ch = min(w["width"], SW - x), min(w["height"], SH - y)
    try:
        frame = subprocess.run(["/usr/bin/xwd", "-root", "-silent"], capture_output=True, timeout=30, env=ENV).stdout
        stat = subprocess.run(["/usr/bin/convert", "xwd:-", "-crop", f"{cw}x{ch}+{x}+{y}", "-format",
                               "%[fx:standard_deviation]", "info:"], input=frame, capture_output=True, timeout=30,
                              env=ENV).stdout.decode().strip()
        return float(stat) < 0.004
    except Exception:
        return False
def main():
    problems = [] if our_server() else ["pickfit's X server was not running when the watch began"]
    began, first = time.time(), None
    while not problems:
        mine, own, other = look()
        if own and first is None:
            first = time.time() - began
        if first is not None and time.time() - began >= first + SETTLE_S:
            if time.time() - began >= first + SETTLE_S + BLANK_S or not blank(own):
                break
        if not mine or time.time() - began >= WAIT_S + (SETTLE_S if first is not None else 0):
            break
        time.sleep(1)
    mine, own, other = look() if not problems else ({}, [], [])
    data = b""
    if not problems:
        xwd = subprocess.Popen(["/usr/bin/xwd", "-root", "-silent"], stdout=subprocess.PIPE, env=ENV)
        conv = subprocess.run(["/usr/bin/convert", "xwd:-", "png:" + SHOT], stdin=xwd.stdout, capture_output=True,
                              timeout=60, env=ENV)
        xwd.wait(timeout=60)
        if conv.returncode == 0 and xwd.returncode == 0:
            data = open(SHOT, "rb").read()
        else:
            why = (conv.stderr or b"").decode("utf-8", "replace").strip()[-200:]
            problems.append(f"the screenshot failed (xwd {xwd.returncode}, convert {conv.returncode}: {why})")
        if not our_server():  # a server the app started after killing or crashing ours could have lied
            problems.append("pickfit's X server was gone when the watch ended")
            own, data = [], b""
    print(MARK + NONCE + " " + json.dumps({
        "seconds_to_window": None if first is None else round(first, 1), "alive": len(mine),
        "processes": sorted({v[1] for v in mine.values()})[:12], "windows": own, "other_windows": other[:5],
        "shot_bytes": len(data), "shot_sha256": hashlib.sha256(data).hexdigest() if data else None,
        "problems": problems, "watched_s": round(time.time() - began, 1)}))
if __name__ == "__main__":
    main()
"""


def watcher_source(*, before: dict[str, Any], xvfb_pid: int, nonce: str, shot: str, wait_s: int,
                   settle_s: int = SETTLE_S) -> str:
    fill = {"@DISPLAY@": DISPLAY, "@BEFORE@": json.dumps(before), "@XVFB@": str(int(xvfb_pid)), "@NONCE@": nonce,
            "@SHOT@": shot, "@WAIT@": str(int(wait_s)), "@SETTLE@": str(int(settle_s)), "@MIN_W@": str(MIN_WIDTH),
            "@MIN_H@": str(MIN_HEIGHT), "@SW@": str(SCREEN_W), "@SH@": str(SCREEN_H), "@UID@": str(DISPLAY_UID),
            "@BLANK@": str(BLANK_WAIT_S)}
    body = _WATCH
    for key, value in fill.items():
        body = body.replace(key, value)
    return _PROCS + f"\nMARK = {MARK!r}\n" + body


DESKTOP_SETUP = (
    "export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_TYPE=x11 GTK_USE_PORTAL=1; "
    "mkdir -p ~/.config/xdg-desktop-portal; printf '[preferred]\\ndefault=gtk\\n' "
    "> ~/.config/xdg-desktop-portal/portals.conf; "
    "xdg-mime default org.xfce.mousepad.desktop text/plain 2>/dev/null || true")


def start_script(command: str, tag: str | int, *, workdir: str, detach: str = "setsid nohup") -> str:
    """Box user: start the app detached on the display; its output and exit code go to its own log."""
    log = f"{APP_LOG_DIR}/{tag}"
    if FULL_DESKTOP:
        command = (f"{DESKTOP_SETUP}\n/usr/bin/dbus-run-session -- /usr/bin/bash -c "
                   f"{shlex.quote(command)}")
    wrapped = f"{command}\necho \"exit_code $?\""
    return (f"/usr/bin/mkdir -p {APP_LOG_DIR} && cd {shlex.quote(workdir)} || exit 1; export DISPLAY={DISPLAY}; "
            f"{detach} /usr/bin/bash -c {shlex.quote(wrapped)} > {log}.log 2>&1 < /dev/null & echo started")


@dataclass
class GuiWindow:
    id: str
    title: str
    width: int
    height: int
    x: int = 0
    y: int = 0
    pid: int | None = None
    client: str | None = None


@dataclass
class GuiLaunch:
    """What one launch showed. tier is the strongest tier the launch itself reached (at most window)."""

    tier: str
    windows: list[GuiWindow] = field(default_factory=list)
    other_windows: list[GuiWindow] = field(default_factory=list)  # mapped, but not the app's (or too small)
    processes: list[str] = field(default_factory=list)
    alive: bool = False
    seconds_to_window: float | None = None
    screenshot: str | None = None  # where pickfit saved the PNG (on the host)
    shot_bytes: int | None = None  # the PNG's size and hash as the watcher wrote it
    shot_sha256: str | None = None
    log_tail: str = ""  # the app's own output: data, never a result
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def title(self) -> str:
        """The largest window's title."""
        if not self.windows:
            return ""
        return max(self.windows, key=lambda w: w.width * w.height).title


def parse_report(stdout: str, nonce: str) -> GuiLaunch:
    """The watcher's report: exactly one line tagged with this launch's nonce, or tier none."""
    tag = f"{MARK}{nonce} "
    lines = [line[len(tag):] for line in stdout.splitlines() if line.startswith(tag)]
    data: dict[str, Any] | None = None
    if len(lines) == 1:
        try:
            data = json.loads(lines[0])
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict):
        why = "no report" if not lines else f"{len(lines)} report lines" if len(lines) > 1 else "an unreadable report"
        return GuiLaunch(tier="none", error=f"pickfit's window watcher gave {why}")
    problems = [str(p) for p in data.get("problems") or []]
    own = [] if problems else [GuiWindow(**w) for w in data.get("windows") or []]
    other = [GuiWindow(**w) for w in data.get("other_windows") or []]
    alive = bool(data.get("alive"))
    tier = "window" if own else "process_alive" if alive and not problems else "none"
    return GuiLaunch(tier=tier, windows=own, other_windows=other, processes=list(data.get("processes") or []),
                     alive=alive, seconds_to_window=data.get("seconds_to_window"),
                     shot_bytes=data.get("shot_bytes"), shot_sha256=data.get("shot_sha256"),
                     error="; ".join(problems) or None)


def observation(launch: GuiLaunch) -> str:
    """pickfit's own lines about the launch (stdout): what the agent cites and the replay checks. Nothing the app
    chooses is here: window titles and process names go to app_facts()."""
    meaning = {"window": "a window of the app's own process is shown",
               "process_alive": "the app is still running but showed no window of its own",
               "none": "the app showed no window and is not running"}[launch.tier]
    lines = [f"gui tier: {launch.tier} ({meaning})"]
    for i, w in enumerate(launch.windows, start=1):
        lines.append(f"window {i}: {w.width}x{w.height} at {w.x},{w.y} (pid {w.pid})")
    if launch.other_windows:
        lines.append(f"{len(launch.other_windows)} other window(s) not counted (not the app's, or too small)")
    if launch.seconds_to_window is not None:
        lines.append(f"first window after {launch.seconds_to_window}s")
    if launch.error:
        lines.append(f"note: {launch.error}")
    lines.append("pickfit took a screenshot and then stopped every process of the box user.")
    return "\n".join(lines)


def app_facts(launch: GuiLaunch) -> str:
    """What the app itself set (stderr, as data): window titles, process names, then its output."""
    lines = ["--- set by the app: window titles and process names ---"]
    lines += [f"window {i} title: {w.title!r}" for i, w in enumerate(launch.windows, start=1)]
    if launch.processes:
        lines.append(f"processes: {', '.join(map(repr, launch.processes))}")
    lines += ["--- app output (the app's own, not pickfit's) ---", launch.log_tail.rstrip()]
    return "\n".join(lines).rstrip()


def read_evidence(box: Box, path: str, size: int | None, sha256: str | None) -> tuple[bytes | None, str | None]:
    """A file of pickfit's evidence, as root reads it, checked against the size and hash its maker printed;
    (None, why) if no read matches."""
    if not size or not sha256 or size > SHOT_MAX_BYTES:
        return None, f"no usable screenshot ({size} bytes)"
    got = 0
    for _ in range(SHOT_READS):
        try:
            data = box.harness_read(path, SHOT_MAX_BYTES)
        except Exception as err:  # BoxError: the box or the file is gone
            return None, f"screenshot unreadable: {err}"
        got = len(data)
        if got == size and hashlib.sha256(data).hexdigest() == sha256:
            return data, None
    return None, f"screenshot copy incomplete after {SHOT_READS} reads ({got} of {size} bytes)"


def read_shot(box: Box, path: str, shown: GuiLaunch) -> tuple[bytes | None, str | None]:
    """The launch's screenshot, checked against the size and hash the watcher printed."""
    return read_evidence(box, path, shown.shot_bytes, shown.shot_sha256)


def stop_box_user(box: Box) -> ExecResult:
    """Root: stop every process of the box user (the app, whatever it forked, and anything else of that uid)."""
    return box.harness_exec([PYTHON, "-I", "-S", "-"], 60, stdin=KILL_PY.encode())


@dataclass
class Opened:
    """An app started on the display and watched until its window showed (or the wait ran out); still running."""

    shown: GuiLaunch
    shot: str  # the watcher's screenshot, in EVIDENCE_DIR
    seconds: float
    timed_out: bool


def open_app(box: Box, command: str, tag: str | int, wait_s: int, *, timeout_s: int | None = None) -> Opened:
    """Snapshot the box user's processes, start the app as the box user and watch for its window (steps 1-3).
    The app keeps running: close_app stops it."""
    wait_s = max(1, min(int(wait_s), WAIT_MAX_S))
    xvfb_pid = getattr(box, "xvfb_pid", None)
    if not box.display or not xvfb_pid:
        raise ValueError("a GUI launch needs a box with pickfit's display")
    nonce = secrets.token_hex(12)
    shot = f"{EVIDENCE_DIR}/{tag}.png"
    snap = box.harness_exec([PYTHON, "-I", "-S", "-"], 30, as_uid=DISPLAY_UID, stdin=SNAPSHOT_PY.encode())
    try:
        before = json.loads(snap.stdout.strip().splitlines()[-1]) if snap.exit_code == 0 else None
    except (json.JSONDecodeError, IndexError):
        before = None
    started = box.exec(start_script(command, tag, workdir=box.workdir, detach=box.detach), 30)
    seconds, timed_out = started.seconds, started.timed_out
    if before is None or started.exit_code != 0:
        shown = GuiLaunch(tier="none", error="the launch could not start: " +
                          (started.stderr.strip()[-300:] if before is not None else "no process snapshot"))
    else:
        source = watcher_source(before=before, xvfb_pid=xvfb_pid, nonce=nonce, shot=shot, wait_s=wait_s)
        watch = box.harness_exec([PYTHON, "-I", "-S", "-"], timeout_s or wait_s + SETTLE_S + BLANK_WAIT_S + 90,
                                 as_uid=DISPLAY_UID, stdin=source.encode())
        seconds, timed_out = round(seconds + watch.seconds, 2), watch.timed_out
        shown = parse_report(watch.stdout, nonce)
        if watch.exit_code != 0 and not shown.error:
            shown.error = f"the watcher exited {watch.exit_code}: {watch.stderr.strip()[-300:]}"
    return Opened(shown=shown, shot=shot, seconds=seconds, timed_out=timed_out)


def close_app(box: Box, opened: Opened, tag: str | int) -> tuple[bytes | None, bool]:
    """Root stops every box-user process, copies the window screenshot out and reads the app's log (steps 4-5);
    (the screenshot PNG, whether something of the box user's survived the stop)."""
    shown = opened.shown
    stopped = stop_box_user(box)
    survived = "PICKFIT_KILLED" not in stopped.stdout
    if survived:  # something of the box user's outlived the launch: nothing about it counts
        shown.error = "; ".join(filter(None, [shown.error, "box-user processes survived the stop"]))
    png: bytes | None = None
    if shown.tier == "window":
        png, why = read_shot(box, opened.shot, shown)
        if why:
            shown.error = "; ".join(filter(None, [shown.error, why]))
    log = box.exec(f"/usr/bin/tail -c 3000 -- {APP_LOG_DIR}/{tag}.log", 20)
    shown.log_tail = log.stdout if log.exit_code == 0 else ""
    return (None if survived else png), survived


def launch(box: Box, command: str, tag: str | int, wait_s: int, *, timeout_s: int | None = None
           ) -> tuple[ExecResult, GuiLaunch, bytes | None]:
    """Launch on the box's display; (the record to keep, what it showed, the screenshot PNG)."""
    opened = open_app(box, command, tag, wait_s, timeout_s=timeout_s)
    png, survived = close_app(box, opened, tag)
    shown = opened.shown
    code = 0 if shown.tier == "window" and png is not None and not opened.timed_out and not survived else 1
    result = ExecResult(command=command, exit_code=code, stdout=observation(shown), stderr=app_facts(shown),
                        seconds=opened.seconds, timed_out=opened.timed_out)
    return result, shown, png
