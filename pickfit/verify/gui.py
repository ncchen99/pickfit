"""Launch a GUI app on the box's virtual display and record how far it got (Linux).

A box with a display runs Xvfb as the box user (no window manager, no GPU).
`launch_gui` starts the app detached in its own session with DISPLAY set,
waits for a window of its own, lets it settle, takes a screenshot of the whole
display and stops the app. A window counts as the app's only if the X server
says the client that made it is one of the app's processes (the XRes extension
reports client PIDs from the server side; _NET_WM_PID is set by the app and is
not used).

Evidence tiers, weakest to strongest (see docs/brief.md; app stores stop at
install, signing and malware checks):

  none           the app exited before showing anything
  process_alive  still running after the wait, but no window of its own
  window         a mapped window of its own (title and size recorded)
  ui_rendered    the screen judge read the screenshot and saw the app's own UI
  accessibility  the accessibility tree shows its controls       (not checked yet)
  action_state   one action changed checkable state              (not checked yet)

The launch itself reaches at most `window`; ui_rendered comes from the screen
judge on the replay's screenshot. A GUI check supports level install at most:
a GUI app is never labelled function unless one action changed checkable state.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from pickfit.verify.box import ExecResult

if TYPE_CHECKING:
    from pickfit.verify.box import Box

DISPLAY = ":99"
SCREEN = "1280x800x24"
DISPLAY_NOTE = f"Xvfb {SCREEN}, no window manager, no GPU"
# What the display needs, and the shared libraries Electron and Tauri apps load
# (chromium brings GTK, NSS, GBM and ALSA). Installed on top of sandbox.Dockerfile.
GUI_PACKAGES = ("xvfb", "x11-utils", "x11-apps", "xrestop", "imagemagick", "chromium",
                "libwebkit2gtk-4.1-0", "fonts-dejavu-core")
TIERS = ("none", "process_alive", "window", "ui_rendered", "accessibility", "action_state")
WAIT_MAX_S = 60
SETTLE_S = 6  # after the first window, so a page that loads after the window shows still renders
MIN_WINDOW_PX = 2500  # 50x50: Electron and GTK make 1x1 and 10x10 helper windows
SHOT_MAX_BYTES = 4_000_000
GUI_DIR = "/tmp/pickfit-gui"
MARK = "PICKFIT_GUI_JSON "


def xvfb_script(detach: str = "setsid nohup") -> str:
    """Start Xvfb as the box user unless it already answers; exits 0 once it does."""
    return (f"export DISPLAY={DISPLAY}; xdpyinfo >/dev/null 2>&1 && exit 0; "
            f"{detach} Xvfb {DISPLAY} -screen 0 {SCREEN} -nolisten tcp > /tmp/xvfb.log 2>&1 < /dev/null & "
            "for i in $(seq 1 40); do xdpyinfo >/dev/null 2>&1 && exit 0; sleep 0.25; done; "
            "cat /tmp/xvfb.log; exit 1")


# Runs in the box with the image's own python (-I: nothing imported from the work dir). argv: the app's
# session leader pid, seconds to wait for a window, seconds to settle, the screenshot path.
_WATCH = r"""
import json, os, re, subprocess, sys, time
pid, wait_s, settle_s, shot = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
def run(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""
def procs():
    out = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                stat = open(f"/proc/{d}/stat").read()
                comm = stat[stat.index("(") + 1:stat.rindex(")")]
                rest = stat[stat.rindex(")") + 2:].split()
                out[int(d)] = (int(rest[1]), int(rest[3]), rest[0], comm)
            except (OSError, ValueError, IndexError):
                pass
    return out
def app_pids():
    table = procs()
    pids = {p for p, (_, sid, state, _) in table.items() if sid == pid and state != "Z"}
    kids = {pid} if pid in table and table[pid][2] != "Z" else set()
    while True:
        more = {p for p, (pp, _, state, _) in table.items() if pp in kids and p not in kids and state != "Z"}
        if not more:
            break
        kids |= more
    return pids | kids, {p: table[p][3] for p in pids | kids}
def clients():
    found, cur = [], None
    for line in run("xrestop -b -m 1").splitlines():
        head = re.match(r"^\d+ - (.*) \(\s*PID:\s*(\d*)\s*\):", line)
        if head:
            cur = {"name": head.group(1), "pid": int(head.group(2)) if head.group(2) else None}
            found.append(cur)
            continue
        kv = re.match(r"^\s*(res[_-]base|res[_-]mask)\s*:\s*(0x[0-9a-fA-F]+)", line)
        if kv and cur is not None:
            cur[kv.group(1).replace("-", "_")] = int(kv.group(2), 16)
    return found
def windows():
    found = []
    for line in run("xwininfo -root -children").splitlines():
        m = re.match(r'^\s+(0x[0-9a-f]+) (?:"([^"]*)"|\(has no name\)).*?\s(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', line)
        if not m:
            continue
        info = run(f"xwininfo -id {m.group(1)}")
        if "IsViewable" not in info:
            continue
        found.append({"id": m.group(1), "title": m.group(2) or "", "width": int(m.group(3)),
                      "height": int(m.group(4))})
    return found
def owner(win, cls):
    wid = int(win["id"], 16)
    for c in cls:
        if "res_base" in c and "res_mask" in c and (wid & ~c["res_mask"]) == c["res_base"]:
            return c
    return None
def look():
    pids, names = app_pids()
    cls, own, other = clients(), [], []
    for w in windows():
        c = owner(w, cls)
        w["pid"] = c["pid"] if c else None
        w["client"] = c["name"] if c else None
        mine = c is not None and c["pid"] in pids and w["width"] * w["height"] >= MIN_PX
        (own if mine else other).append(w)
    return pids, names, own, other
MIN_PX = int(os.environ.get("PICKFIT_MIN_WINDOW_PX", "2500"))
began = time.time()
first = None
while True:
    pids, names, own, other = look()
    if own and first is None:
        first = time.time() - began
    if first is not None and time.time() - began >= first + settle_s:
        break
    if not pids or time.time() - began >= wait_s + (settle_s if first is not None else 0):
        break
    time.sleep(1)
pids, names, own, other = look()
shot_ok = subprocess.run(f"xwd -root -silent | convert xwd:- png:{shot}", shell=True,
                         capture_output=True, timeout=30).returncode == 0
print("PICKFIT_GUI_JSON " + json.dumps({
    "seconds_to_window": None if first is None else round(first, 1), "alive": sorted(pids),
    "processes": sorted(set(names.values()))[:12], "windows": own, "other_windows": other,
    "screenshot": shot_ok, "watched_s": round(time.time() - began, 1)}))
for p in pids:
    try:
        os.kill(p, 15)
    except OSError:
        pass
time.sleep(2)
for p in app_pids()[0]:
    try:
        os.kill(p, 9)
    except OSError:
        pass
"""


def launch_script(command: str, tag: str | int, wait_s: int, *, workdir: str, detach: str = "setsid nohup",
                  settle_s: int = SETTLE_S) -> str:
    """Bash that starts `command` on the display, watches it and prints one JSON line (MARK)."""
    wait_s = max(1, min(int(wait_s), WAIT_MAX_S))
    base = f"{GUI_DIR}/{tag}"
    # The app's exit code lands in .exit; `bash -c` stays as the session leader, so its pid is the session id.
    wrapped = f"{command}\necho $? > {base}.exit"
    return (f"mkdir -p {GUI_DIR} && cd {shlex.quote(workdir)} || exit 1; export DISPLAY={DISPLAY}; "
            f"rm -f {base}.exit {base}.png; "
            f"{detach} bash -c {shlex.quote(wrapped)} > {base}.log 2>&1 < /dev/null & P=$!; "
            f"PICKFIT_MIN_WINDOW_PX={MIN_WINDOW_PX} /usr/local/bin/python3 -I - $P {wait_s} {settle_s} "
            f"{base}.png <<'PICKFIT_GUI_PY'\n{_WATCH}\nPICKFIT_GUI_PY\n"
            f"echo \"exit_code $(cat {base}.exit 2>/dev/null)\"; echo '--- app log tail ---'; tail -n 30 {base}.log")


@dataclass
class GuiWindow:
    id: str
    title: str
    width: int
    height: int
    pid: int | None = None
    client: str | None = None


@dataclass
class GuiLaunch:
    """What one launch showed. tier is the strongest tier the launch itself reached (at most window)."""

    tier: str
    windows: list[GuiWindow] = field(default_factory=list)
    other_windows: list[GuiWindow] = field(default_factory=list)  # mapped, but not the app's
    processes: list[str] = field(default_factory=list)
    alive: bool = False
    exit_code: int | None = None  # when the app exited before the watch ended
    seconds_to_window: float | None = None
    screenshot: str | None = None  # where pickfit saved the PNG (on the host)
    log_tail: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def title(self) -> str:
        """The largest window's title."""
        if not self.windows:
            return ""
        return max(self.windows, key=lambda w: w.width * w.height).title


def parse_launch(stdout: str) -> GuiLaunch:
    data: dict[str, Any] | None = None
    exit_code: int | None = None
    lines = stdout.splitlines()
    for line in lines:
        if line.startswith(MARK):
            try:
                data = json.loads(line[len(MARK):])
            except json.JSONDecodeError:
                data = None
        elif line.startswith("exit_code "):
            value = line[len("exit_code "):].strip()
            exit_code = int(value) if value.lstrip("-").isdigit() else None
    tail = stdout.split("--- app log tail ---\n", 1)[1] if "--- app log tail ---\n" in stdout else ""
    if data is None:
        return GuiLaunch(tier="none", exit_code=exit_code, log_tail=tail,
                         error="pickfit's window watcher printed nothing (the display or the watcher failed)")
    own = [GuiWindow(**w) for w in data.get("windows") or []]
    other = [GuiWindow(**w) for w in data.get("other_windows") or []]
    alive = bool(data.get("alive"))
    tier = "window" if own else "process_alive" if alive else "none"
    return GuiLaunch(tier=tier, windows=own, other_windows=other, processes=list(data.get("processes") or []),
                     alive=alive, exit_code=None if alive else exit_code,
                     seconds_to_window=data.get("seconds_to_window"), log_tail=tail,
                     error=None if data.get("screenshot") else "the screenshot failed")


def observation(launch: GuiLaunch) -> str:
    """The text the agent and the replay record as the launch's output."""
    meaning = {"window": "a window of the app's own process is shown",
               "process_alive": "the app is still running but showed no window of its own",
               "none": "the app exited without showing a window"}[launch.tier]
    lines = [f"gui tier: {launch.tier} ({meaning})"]
    for w in launch.windows:
        lines.append(f"window: \"{w.title}\" {w.width}x{w.height} (pid {w.pid})")
    for w in launch.other_windows[:3]:
        lines.append(f"other window, not the app's: \"{w.title}\" {w.width}x{w.height} ({w.client or 'unknown'})")
    if launch.seconds_to_window is not None:
        lines.append(f"first window after {launch.seconds_to_window}s")
    if launch.tier == "none" and launch.exit_code is not None:
        lines.append(f"the app exited with code {launch.exit_code}")
    if launch.processes:
        lines.append(f"processes: {', '.join(launch.processes)}")
    if launch.error:
        lines.append(f"note: {launch.error}")
    lines.append("pickfit took a screenshot of the display and stopped the app.")
    if launch.log_tail.strip():
        lines += ["--- app log tail ---", launch.log_tail.rstrip()]
    return "\n".join(lines)


def launch(box: Box, command: str, tag: str | int, wait_s: int, *, timeout_s: int | None = None
           ) -> tuple[ExecResult, GuiLaunch, bytes | None]:
    """Launch on the box's display; (the record to keep, what it showed, the screenshot PNG)."""
    wait_s = max(1, min(int(wait_s), WAIT_MAX_S))
    script = launch_script(command, tag, wait_s, workdir=box.workdir, detach=box.detach)
    raw = box.exec(script, timeout_s or wait_s + SETTLE_S + 60)
    shown = parse_launch(raw.stdout)
    png: bytes | None = None
    if raw.exit_code == 0 and not shown.error:
        try:
            png = box.read_file(f"{GUI_DIR}/{tag}.png", SHOT_MAX_BYTES)
        except Exception as err:  # BoxError: the box or the file is gone
            shown.error = f"screenshot unreadable: {err}"
    if raw.timed_out:
        shown.error = "the launch watcher timed out"
    text = observation(shown)
    code = 0 if shown.tier == "window" and not raw.timed_out else 1
    result = ExecResult(command=command, exit_code=code, stdout=text, stderr=raw.stderr.strip()[-2000:],
                        seconds=raw.seconds, timed_out=raw.timed_out, truncated=raw.truncated)
    return result, shown, png
