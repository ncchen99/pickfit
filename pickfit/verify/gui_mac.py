"""Launch a GUI app on a macOS VM's desktop and record how far it got (tart, seen over VNC).

gui.py's check for a TartBox made with display=True: the same tiers, report and evidence rules.

- The app runs as sbx, the console user, in its own desktop session; nothing that produces evidence does.
  Root starts the model's command in that session (`launchctl asuser`, then `sudo -u sbx`), and root's
  watcher, in the same session so WindowServer answers it, lists the windows on screen. A window's owner
  PID comes from WindowServer and the owner's executable from the kernel (proc_pidpath): nothing the app
  says about itself decides.
- A window is the app's own when it is a normal window (layer 0), at least MIN_WIDTH x MIN_HEIGHT of it is
  on screen, and its owner is an sbx process that was not running before the launch and whose executable is
  not part of macOS (SYSTEM_PREFIXES; sbx can write none of them). A Gatekeeper prompt, an open panel or a
  stand-in such as TextEdit is not the app.
- pickfit takes the screenshot itself, on the host, from the VM's framebuffer over VNC (vnc.py).
- Before each launch pickfit answers macOS's first-launch prompt ("... is an app downloaded from the
  Internet. Are you sure you want to open it?") for the app bundles Gatekeeper accepts as notarized, as a
  user clicking Open does: it sets the user-approved flag on the bundle's quarantine, which is what that
  click records. A bundle Gatekeeper rejects is left alone, so macOS blocks it as it would for a user.
- Afterwards root stops every sbx process that was not part of its login session (the app, its helpers,
  run_background servers), in rounds until none is left, and closes Gatekeeper's prompts. Apple's own agents that launchd restarts on demand
  may come back; anything else that survives makes the launch count for nothing.

A launch reaches at most tier `window`; the screen judge gives ui_rendered (judge.judge_gui), and a GUI launch
supports level install only. VncDisplay is the display an operating loop drives: screenshot -> PNG bytes,
click(x, y), type_text(s), key(name).
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shlex
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pickfit.verify import gui
from pickfit.verify.box import BoxError, ExecResult
from pickfit.verify.gui import GuiLaunch, GuiWindow
from pickfit.verify.tart_box import DETACH_CMD, GUEST_PYTHON, HELPER_DIR, MAC_ENV, MAC_HOME, MAC_UID, MAC_USER, \
    MAC_WORKDIR
from pickfit.verify.vnc import VncClient, VncError

if TYPE_CHECKING:
    from pickfit.verify.tart_box import TartBox

APP_LOG_DIR = f"{MAC_HOME}/.pickfit-gui"
HELPER_PATH = f"{HELPER_DIR}/gui"
EARLY_EXIT_S = 10  # `open` hands the app to launchd: no app process for a moment is not yet "it exited"
SYSTEM_PREFIXES = ("/System/", "/usr/", "/bin/", "/sbin/", "/Library/Apple/", "/Applications/")
# Apple's agents launchd restarts on demand: they may be running again after the stop without surviving it.
RESPAWNED_PREFIXES = ("/System/", "/usr/libexec/", "/usr/sbin/")
QTN_USER_APPROVED = 0x40  # the quarantine flag the first-launch prompt's Open button sets
# The session process that shows Gatekeeper's prompts; the stop closes them with it, so a refusal left from one
# launch does not cover the next (measured 11/1: Quill's "Not Opened" over inlaut's window).
PROMPT_AGENTS = ("/System/Library/CoreServices/CoreServicesUIAgent.app/Contents/MacOS/CoreServicesUIAgent",)
MENU_WAIT_S, MENU_SETTLE_S = 8, 2  # after pickfit clicks a menu bar app's item
SETTLE_GAP_S, SETTLE_MAX_S = 0.4, 4.0  # a screenshot waits until two frames this far apart agree
DISPLAY_NOTE = "macOS desktop 1280x800 in a tart VM; pickfit's screenshot over VNC from the host"


@dataclass
class MacGuiLaunch(GuiLaunch):
    """gui.GuiLaunch that names its display, so the run records the macOS desktop and not Xvfb."""

    display: str = DISPLAY_NOTE


def _mac(launch: GuiLaunch) -> MacGuiLaunch:
    return MacGuiLaunch(**{k: getattr(launch, k) for k in GuiLaunch.__dataclass_fields__})

# Root, in the guest (the Command Line Tools' Python 3.9): `<cmd>` with a JSON payload on stdin. Placeholders
# are pickfit's constants, filled in when the helper is written; nothing in it comes from the app.
HELPER = r'''
import ctypes, json, os, re, signal, subprocess, sys, time
BOX_UID = "@UID@"
ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"}
SYSTEM, RESPAWNED, APPROVED, PROMPTS = @SYSTEM@, @RESPAWNED@, @APPROVED@, @PROMPTS@
libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
libc = ctypes.CDLL(None, use_errno=True)
libc.getxattr.restype = ctypes.c_ssize_t
libc.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32,
                          ctypes.c_int]
libc.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32,
                          ctypes.c_int]
NOFOLLOW = 1
QTN = b"com.apple.quarantine"

def exe(pid):
    buf = ctypes.create_string_buffer(4096)
    n = libproc.proc_pidpath(int(pid), buf, 4096)
    return buf.value.decode("utf-8", "replace") if n > 0 else ""

def procs():
    # The box user's live processes, {pid: [start time, executable]}: uid and start time from the kernel via ps,
    # the executable from proc_pidpath (argv and the process name are the app's to choose).
    out = {}
    text = subprocess.run(["/bin/ps", "-axo", "pid=,uid=,ruid=,stat=,lstart="], capture_output=True, text=True,
                          env=ENV).stdout
    for line in text.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5 or BOX_UID not in parts[1:3] or parts[3].startswith("Z"):
            continue
        out[parts[0]] = [parts[4].strip(), exe(parts[0])]
    return out

def apple(path):
    return not path or path.startswith(SYSTEM)

JXA = ('ObjC.import("CoreGraphics"); var b = $.CGDisplayBounds($.CGMainDisplayID()); '
       'JSON.stringify({screen: [b.size.width, b.size.height], '
       'windows: ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo(17, 0))) || []})')

def windows():
    # On-screen windows from WindowServer (needs this process in the desktop session: launchctl asuser).
    try:
        done = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", JXA], capture_output=True,
                              text=True, timeout=20, env=ENV)
        data = json.loads(done.stdout)
        return [int(v) for v in data["screen"]], list(data["windows"])
    except Exception:
        return None, []

STATUS, MENU_BAR = 25, 24  # window layers: menu bar items (hosted by Control Center on macOS 26), the bar

def items(found):
    # Menu bar items: on macOS 26 Control Center hosts every app's, so only their window number is the app's tell.
    out = []
    for w in found:
        b = w.get("kCGWindowBounds") or {}
        if w.get("kCGWindowLayer") == STATUS:
            out.append({"id": str(w.get("kCGWindowNumber", "")), "x": int(b.get("X", 0)), "y": int(b.get("Y", 0)),
                        "width": int(b.get("Width", 0)), "height": int(b.get("Height", 0))})
    return out

def look(before, min_w, min_h, any_layer=False):
    # any_layer: after pickfit clicked the app's menu bar item, its menu or popover (layer 101 and the like) counts.
    now = procs()
    mine = {p: v for p, v in now.items() if before.get(p, [None])[0] != v[0] and not apple(v[1])}
    screen, found = windows()
    own, other = [], []
    if screen is None:
        return mine, own, other, screen, []
    sw, sh = screen
    for w in found:
        layer = w.get("kCGWindowLayer")
        if (layer in (STATUS, MENU_BAR)) if any_layer else layer != 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        try:
            x, y, wd, ht = (int(b.get(k, 0)) for k in ("X", "Y", "Width", "Height"))
            pid = int(w.get("kCGWindowOwnerPID"))
            alpha = float(w.get("kCGWindowAlpha", 1))
        except (TypeError, ValueError):
            continue
        vw, vh = min(x + wd, sw) - max(x, 0), min(y + ht, sh) - max(y, 0)
        info = {"id": str(w.get("kCGWindowNumber", "")), "title": str(w.get("kCGWindowName") or "")[:200],
                "width": wd, "height": ht, "x": x, "y": y, "pid": pid,
                "client": str(w.get("kCGWindowOwnerName") or "")[:80]}
        mine_now = str(pid) in mine
        (own if mine_now and alpha > 0 and vw >= min_w and vh >= min_h else other).append(info)
    return mine, own, other, screen, items(found)

def console():
    return subprocess.run(["/usr/bin/stat", "-f", "%Su", "/dev/console"], capture_output=True, text=True,
                          env=ENV).stdout.strip()

def watch(cfg):
    before, wait_s, settle_s, any_layer = cfg["before"], cfg["wait_s"], cfg["settle_s"], cfg.get("any_layer", False)
    items_before = set(cfg.get("items_before") or [])
    problems = [] if console() == cfg["user"] else ["the box user's desktop session was not on screen"]
    began, first, first_item = time.time(), None, None
    while not problems:
        mine, own, other, screen, bar = look(before, cfg["min_w"], cfg["min_h"], any_layer)
        if screen is None:
            problems.append("pickfit could not list the windows on screen")
            break
        elapsed = time.time() - began
        if own and first is None:
            first = elapsed
        if first_item is None and mine and any(i["id"] not in items_before for i in bar):
            first_item = elapsed
        if first is not None and elapsed >= first + settle_s:
            break
        if first is None and first_item is not None and elapsed >= first_item + settle_s:
            break  # a menu bar item and no window: pickfit clicks it next
        if (not mine and elapsed >= cfg["early_exit_s"]) or elapsed >= wait_s + (settle_s if first is not None else 0):
            break
        time.sleep(1)
    mine, own, other, screen, bar = (look(before, cfg["min_w"], cfg["min_h"], any_layer) if not problems
                                     else ({}, [], [], None, []))
    if not problems and console() != cfg["user"]:
        problems.append("the box user's desktop session was gone when the watch ended")
        own = []
    print(cfg["mark"] + cfg["nonce"] + " " + json.dumps({
        "seconds_to_window": None if first is None else round(first, 1), "alive": len(mine),
        "processes": sorted({os.path.basename(v[1]) for v in mine.values()})[:12], "windows": own,
        "other_windows": other[:5], "shot_bytes": None, "shot_sha256": None, "problems": problems,
        "screen": screen, "new_items": [i for i in bar if i["id"] not in items_before] if mine else [],
        "watched_s": round(time.time() - began, 1)}))

def bar_items():
    screen, found = windows()
    print(json.dumps(None if screen is None else [i["id"] for i in items(found)]))

def quarantine(path):
    buf = ctypes.create_string_buffer(1024)
    n = libc.getxattr(path.encode(), QTN, buf, 1024, 0, NOFOLLOW)
    return buf.raw[:n].decode("utf-8", "replace") if n > 0 else None

def bundles(roots, depth=5):
    found = []
    for root in roots:
        base = root.rstrip("/").count("/")
        for here, dirs, _ in os.walk(root):
            keep = []
            for d in dirs:
                path = os.path.join(here, d)
                if os.path.islink(path) or d.startswith(".") or (here == root and d == "Library"):
                    continue
                if d.endswith(".app"):
                    found.append(path)
                elif path.count("/") - base < depth:
                    keep.append(d)
            dirs[:] = keep
    return found

def approve(cfg):
    out = []
    for path in bundles(cfg["roots"]):
        q = quarantine(path)
        if q is None:
            continue
        try:
            flags = int(q.split(";", 1)[0], 16)
        except ValueError:
            continue
        if flags & APPROVED:
            continue
        done = subprocess.run(["/usr/sbin/spctl", "-a", "-t", "exec", "-vv", path], capture_output=True,
                              text=True, timeout=120, env=ENV)
        text = (done.stdout + done.stderr).strip()
        source = re.search(r"^source=(.*)$", text, re.M)
        verdict = "accepted" if done.returncode == 0 else "rejected"
        ok = verdict == "accepted" and source is not None and source.group(1).strip() == "Notarized Developer ID"
        if ok:
            value = ("%04x;%s" % (flags | APPROVED, q.split(";", 1)[1] if ";" in q else "")).encode()
            ok = libc.setxattr(path.encode(), QTN, value, len(value), 0, NOFOLLOW) == 0
        out.append({"bundle": path, "gatekeeper": verdict, "source": source.group(1).strip() if source else None,
                    "approved": ok})
    print(json.dumps(out))

def sparkle(cfg):
    # App bundles that update themselves with Sparkle, and their bundle ids (the app's own Info.plist: data).
    import plistlib
    out = []
    for path in bundles(cfg["roots"]):
        if not os.path.isdir(os.path.join(path, "Contents", "Frameworks", "Sparkle.framework")):
            continue
        try:
            with open(os.path.join(path, "Contents", "Info.plist"), "rb") as fh:
                ident = plistlib.load(fh).get("CFBundleIdentifier")
        except Exception:
            continue
        if isinstance(ident, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,200}", ident):
            out.append({"bundle": path, "id": ident})
    print(json.dumps(out))

def stop(cfg):
    # bundles_only: just the running apps (an executable inside a .app that is not macOS's), not servers.
    baseline, bundles_only = cfg["baseline"], cfg.get("bundles_only", False)
    def left():
        return {p: v for p, v in procs().items() if baseline.get(p, [None])[0] != v[0]
                and (not bundles_only or (".app/Contents/" in v[1] and not apple(v[1])))}
    found = len(left())
    for pid, v in procs().items():  # its prompts (a Gatekeeper refusal) outlive the app; launchd restarts it
        if v[1] in PROMPTS:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except Exception:
                pass
    for round_ in range(60):
        now = left()
        if not now:
            print("PICKFIT_KILLED", round_, "found", found)
            return
        for sig in (signal.SIGSTOP, signal.SIGKILL):
            for pid in now:
                try:
                    os.kill(int(pid), sig)
                except Exception:
                    pass
        time.sleep(0.1)
    time.sleep(1)
    survivors = sorted({v[1] or "?" for v in left().values() if not v[1].startswith(RESPAWNED)})
    if survivors:
        print("PICKFIT_KILL_FAILED", json.dumps(survivors[:20]))
        sys.exit(1)
    print("PICKFIT_KILLED respawned")

if __name__ == "__main__":
    cfg = json.loads(sys.stdin.read() or "{}")
    cmd = sys.argv[1]
    if cmd == "procs":
        print(json.dumps(procs()))
    elif cmd == "watch":
        watch(cfg)
    elif cmd == "items":
        bar_items()
    elif cmd == "approve":
        approve(cfg)
    elif cmd == "sparkle":
        sparkle(cfg)
    elif cmd == "stop":
        stop(cfg)
'''.replace("@UID@", str(MAC_UID)).replace("@SYSTEM@", repr(SYSTEM_PREFIXES)).replace(
    "@RESPAWNED@", repr(RESPAWNED_PREFIXES)).replace("@APPROVED@", str(QTN_USER_APPROVED)).replace(
    "@PROMPTS@", repr(PROMPT_AGENTS))


def _helper(box: TartBox, cmd: str, payload: dict[str, Any] | None = None, timeout_s: int = 60, *,
            session: bool = False) -> ExecResult:
    """The helper as root; with session, inside sbx's desktop session (window listing needs WindowServer)."""
    argv = [GUEST_PYTHON, "-I", HELPER_PATH, cmd]
    if session:
        argv = ["/bin/launchctl", "asuser", str(MAC_UID), *argv]
    return box.harness_exec(argv, timeout_s, stdin=json.dumps(payload or {}).encode())


def _json_line(result: ExecResult) -> Any:
    try:
        return json.loads(result.stdout.strip().splitlines()[-1]) if result.exit_code == 0 else None
    except (json.JSONDecodeError, IndexError):
        return None


def procs(box: TartBox) -> dict[str, list[str]] | None:
    """sbx's live processes: {pid: [start time, executable]}; None if the list could not be made."""
    data = _json_line(_helper(box, "procs", timeout_s=30))
    return data if isinstance(data, dict) else None


def session_procs(box: TartBox) -> dict[str, list[str]]:
    """sbx's login session (Dock, Finder, its agents): what a launch's stop leaves running."""
    found = procs(box)
    if found is None:
        raise BoxError("could not list the box user's desktop session")
    return found


def approve_first_launch(box: TartBox) -> list[dict[str, Any]]:
    """Answer the first-launch prompt for quarantined bundles Gatekeeper accepts as notarized (see module doc)."""
    data = _json_line(_helper(box, "approve", {"roots": [MAC_HOME, "/opt/homebrew/Caskroom"]}, 300))
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def answer_update_prompts(box: TartBox) -> list[str]:
    """Answer Sparkle's first-launch question ("Check for updates automatically?") with Don't Check, for each app
    bundle that embeds Sparkle, as a user does: it stores SUEnableAutomaticChecks = false in the app's defaults,
    which pickfit writes as sbx before the launch. The sheet covered Neon Vision Editor's window and the operator
    never got past it (11/2). Returns the bundle ids answered."""
    data = _json_line(_helper(box, "sparkle", {"roots": [MAC_HOME, "/opt/homebrew/Caskroom"]}, 120))
    answered = []
    for item in data if isinstance(data, list) else []:
        ident = item.get("id") if isinstance(item, dict) else None
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,200}", ident):
            continue
        done = box.harness_exec(["/bin/launchctl", "asuser", str(MAC_UID), "/usr/bin/sudo", "-n", "-u", MAC_USER,
                                 "/usr/bin/defaults", "write", ident, "SUEnableAutomaticChecks", "-bool", "false"], 30)
        if done.exit_code == 0:
            answered.append(ident)
    return answered


def start_argv(command: str, tag: str | int) -> list[str]:
    """Root's argv that starts `command` as sbx in sbx's desktop session, detached, its output to its own log."""
    wrapped = f"{command}\necho \"exit_code $?\""
    script = (f"/bin/mkdir -p {APP_LOG_DIR} && cd {shlex.quote(MAC_WORKDIR)} || exit 1; {DETACH_CMD} /bin/bash -c "
              f"{shlex.quote(wrapped)} > {APP_LOG_DIR}/{tag}.log 2>&1 < /dev/null & echo started")
    env = [f"{key}={value}" for key, value in MAC_ENV.items()]
    return ["/bin/launchctl", "asuser", str(MAC_UID), "/usr/bin/sudo", "-n", "-u", MAC_USER, "-H", "/usr/bin/env",
            "-i", *env, "/bin/bash", "-c", script]


def _report(stdout: str, nonce: str) -> dict[str, Any]:
    """The watcher's whole report line (parse_report keeps only what gui.GuiLaunch holds)."""
    tag = f"{gui.MARK}{nonce} "
    lines = [line[len(tag):] for line in stdout.splitlines() if line.startswith(tag)]
    try:
        data = json.loads(lines[0]) if len(lines) == 1 else {}
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _watch(box: TartBox, cfg: dict[str, Any], timeout_s: int) -> tuple[GuiLaunch, dict[str, Any], ExecResult]:
    watch = _helper(box, "watch", cfg, timeout_s, session=True)
    shown = gui.parse_report(watch.stdout, cfg["nonce"])
    if watch.exit_code != 0 and not shown.error:
        shown.error = f"the watcher exited {watch.exit_code}: {watch.stderr.strip()[-300:]}"
    return shown, _report(watch.stdout, cfg["nonce"]), watch


def _factor(box: TartBox, report: dict[str, Any]) -> float:
    """Framebuffer pixels per point: window bounds are in points, VNC in pixels (1 on the GUI base)."""
    points = report.get("screen") or [0, 0]
    width = box.screen().size[0]
    return width / points[0] if points and points[0] and width else 1.0


def _scale(windows: list[GuiWindow], factor: float) -> None:
    for w in windows:
        w.x, w.y, w.width, w.height = (round(v * factor) for v in (w.x, w.y, w.width, w.height))


def observation(launch: GuiLaunch, approved: list[dict[str, Any]], *, kept: bool = False,
                clicked: tuple[int, int] | None = None, restarted: int = 0, updates: int = 0) -> str:
    """pickfit's own lines (stdout): what the agent cites and the replay checks. Nothing the app chooses."""
    meaning = {"window": "a window of the app's own process is shown",
               "process_alive": "the app is still running but showed no window of its own",
               "none": "the app showed no window and is not running"}[launch.tier]
    lines = [f"gui tier: {launch.tier} ({meaning})"]
    if restarted:
        lines.append(f"pickfit first stopped {restarted} app process(es) already running, so the launch starts the "
                     "app instead of bringing a running copy forward")
    if clicked:
        lines.append(f"the app showed no window but a menu bar item: pickfit clicked it at {clicked[0]},{clicked[1]}, "
                     "as a user opens a menu bar app; windows below are what opened, and only the app's count")
    for i, w in enumerate(launch.windows, start=1):
        lines.append(f"window {i}: {w.width}x{w.height} at {w.x},{w.y} (pid {w.pid})")
    if launch.other_windows:
        lines.append(f"{len(launch.other_windows)} other window(s) not counted (macOS's, from before the launch, "
                     "or too small)")
    if launch.seconds_to_window is not None:
        lines.append(f"first window after {launch.seconds_to_window}s")
    opened = [a for a in approved if a.get("approved")]
    blocked = [a for a in approved if not a.get("approved")]
    if opened:
        lines.append(f"pickfit answered macOS's first-launch prompt with Open for {len(opened)} app bundle(s) "
                     "Gatekeeper accepts (Notarized Developer ID), as a user does")
    if blocked:
        lines.append(f"{len(blocked)} quarantined app bundle(s) Gatekeeper does not accept as notarized were left "
                     "blocked, as macOS blocks them for a user")
    if updates:
        lines.append(f"pickfit answered the update prompt (\"Check for updates automatically?\") with Don't Check for "
                     f"{updates} app bundle(s) that use Sparkle, as a user does")
    if launch.error:
        lines.append(f"note: {launch.error}")
    if kept:
        lines.append("pickfit took a screenshot of the VM's display over VNC and left the app running, to operate it.")
    else:
        lines.append("pickfit took a screenshot of the VM's display over VNC, then stopped every process of the box "
                     "user outside its desktop session.")
    return "\n".join(lines)


def stop(box: TartBox, *, bundles_only: bool = False) -> tuple[bool, str]:
    """Stop every sbx process outside its login session (bundles_only: only running apps); (whether none
    survived, the helper's line)."""
    stopped = _helper(box, "stop", {"baseline": box.session, "bundles_only": bundles_only}, 90)
    return "PICKFIT_KILLED" in stopped.stdout, stopped.stdout.strip()[-200:]


def _stopped_count(line: str) -> int:
    m = re.search(r"found (\d+)", line)
    return int(m.group(1)) if m else 0


def app_facts(launch: GuiLaunch, approved: list[dict[str, Any]]) -> str:
    """What the app set (stderr, as data): window titles, app and process names, bundle paths, its output."""
    lines = [gui.app_facts(launch)]
    if launch.windows:
        lines.append("--- window owners, as the app names itself ---")
        lines += [f"window {i} owner: {w.client!r}" for i, w in enumerate(launch.windows, start=1)]
    if approved:
        lines.append("--- quarantined app bundles at launch (paths are the app's) ---")
        lines += [f"{a.get('bundle')!r}: Gatekeeper {a.get('gatekeeper')} ({a.get('source')}); "
                  f"{'opened' if a.get('approved') else 'left blocked'}" for a in approved]
    return "\n".join(lines).rstrip()


@dataclass
class MacOpened:
    """An app started on the desktop and watched until its window showed (or the wait ran out); still running.

    Field for field what gui.Opened is to the Linux loop (gui_operate), plus the screenshot pickfit already took
    over VNC and what pickfit did for the launch (prompts answered, a menu bar item clicked, copies stopped)."""

    shown: MacGuiLaunch
    png: bytes | None
    seconds: float
    timed_out: bool
    approved: list[dict[str, Any]]
    clicked: tuple[int, int] | None = None
    restarted: int = 0
    updates: list[str] = field(default_factory=list)  # bundle ids whose update prompt pickfit answered


def open_app(box: TartBox, command: str, tag: str | int, wait_s: int, *, timeout_s: int | None = None
             ) -> MacOpened:
    """Start the app as sbx on its desktop, watch for a window of its own (a menu bar app: click its new item) and
    take the screenshot. The app keeps running: close_app stops it.

    The screenshot is taken at any tier once the watcher has reported, so a failed launch shows what was on
    screen (a crash dialog, a Gatekeeper refusal). On macOS 26 Control Center hosts every app's menu bar item, so
    the item is told by being new since the launch; whatever opens counts only if the app's own process owns it.
    """
    wait_s = max(1, min(int(wait_s), gui.WAIT_MAX_S))
    if not box.display or box.session is None:
        raise ValueError("a macOS GUI launch needs a TartBox made with display=True")
    # A running copy takes the launch: macOS brings it forward instead of starting the app, so nothing new shows
    # (local-transcriber's installer starts the app itself, 11/1). Servers outside a .app keep running.
    ok, line = stop(box, bundles_only=True)
    restarted = _stopped_count(line) if ok else 0
    approved = approve_first_launch(box)
    updates = answer_update_prompts(box)
    before = procs(box)
    items_before = _json_line(_helper(box, "items", timeout_s=30, session=True))
    started = box.harness_exec(start_argv(command, tag), 30)
    seconds, timed_out = started.seconds, started.timed_out
    report: dict[str, Any] = {}
    clicked: tuple[int, int] | None = None
    if before is None or started.exit_code != 0 or "started" not in started.stdout:
        why = "no process snapshot" if before is None else (started.stderr or started.stdout).strip()[-300:]
        shown: GuiLaunch = GuiLaunch(tier="none", error=f"the launch could not start: {why}")
    else:
        cfg = {"before": before, "nonce": secrets.token_hex(12), "mark": gui.MARK, "wait_s": wait_s,
               "settle_s": gui.SETTLE_S, "min_w": gui.MIN_WIDTH, "min_h": gui.MIN_HEIGHT,
               "early_exit_s": EARLY_EXIT_S, "user": MAC_USER, "items_before": items_before or []}
        shown, report, watch = _watch(box, cfg, timeout_s or wait_s + gui.SETTLE_S + 90)
        seconds, timed_out = round(seconds + watch.seconds, 2), watch.timed_out
        items = report.get("new_items") or []
        if shown.tier == "process_alive" and items and not shown.error and isinstance(items_before, list):
            factor = _factor(box, report)
            for item in items[:2]:
                clicked = (round((item["x"] + item["width"] / 2) * factor), round((item["y"] + item["height"] / 2)
                                                                                   * factor))
                box.screen().click(*clicked)
                menu_cfg = {**cfg, "nonce": secrets.token_hex(12), "wait_s": MENU_WAIT_S, "settle_s": MENU_SETTLE_S,
                            "any_layer": True}
                opened, menu_report, menu_watch = _watch(box, menu_cfg, MENU_WAIT_S + 60)
                seconds, timed_out = round(seconds + menu_watch.seconds, 2), timed_out or menu_watch.timed_out
                if opened.tier == "window":
                    shown, report = opened, menu_report
                    break
                box.screen().key("Escape")  # close whatever opened that was not the app's
            else:
                shown.error = "; ".join(filter(None, [shown.error, "clicking its menu bar item opened no window of "
                                                      "the app's own"]))
    png: bytes | None = None
    if report:  # whatever the tier: a launch that showed nothing of the app's leaves a picture of what it showed
        try:
            png = box.screen().screenshot()
        except VncError as err:
            shown.error = "; ".join(filter(None, [shown.error, f"the VNC screenshot failed: {err}"]))
        if png is not None:
            shown.shot_bytes, shown.shot_sha256 = len(png), hashlib.sha256(png).hexdigest()
            factor = _factor(box, report)
            if factor != 1.0:  # a HiDPI mode: bounds are in points
                _scale(shown.windows + shown.other_windows, factor)
    return MacOpened(shown=_mac(shown), png=png, seconds=seconds, timed_out=timed_out, approved=approved,
                     clicked=clicked, restarted=restarted, updates=updates)


def close_app(box: TartBox, opened: MacOpened, tag: str | int) -> tuple[bytes | None, bool]:
    """Stop every sbx process outside its login session and read the app's log; (the launch's screenshot,
    whether something of the box user's survived the stop). Updates opened.shown in place."""
    shown = opened.shown
    ok, line = stop(box)
    if not ok:  # something the box user started outlived the launch: nothing about it counts
        shown.error = "; ".join(filter(None, [shown.error, f"box-user processes survived the stop: {line}"]))
    log = box.exec(f"/usr/bin/tail -c 3000 -- {APP_LOG_DIR}/{tag}.log", 20)
    shown.log_tail = log.stdout if log.exit_code == 0 else ""
    return (opened.png if ok else None), not ok


def stop_box_user(box: TartBox) -> ExecResult:
    """gui.stop_box_user for a macOS box: everything of sbx's outside its login session (PICKFIT_KILLED if so)."""
    ok, line = stop(box)
    return ExecResult(command="stop", exit_code=0 if ok else 1, stdout=line, stderr="", seconds=0.0,
                      timed_out=False)


def launch(box: TartBox, command: str, tag: str | int, wait_s: int, *, timeout_s: int | None = None,
           keep_running: bool = False) -> tuple[ExecResult, GuiLaunch, bytes | None]:
    """Launch on the box's desktop; (the record to keep, what it showed, the screenshot PNG).

    open_app, then close_app (unless keep_running: an operating loop drives the app and calls stop() itself).
    Only a launch at tier window passes (exit 0); a failed one still keeps its screenshot.
    """
    opened = open_app(box, command, tag, wait_s, timeout_s=timeout_s)
    shown, png, survived = opened.shown, opened.png, False
    if not keep_running:
        png, survived = close_app(box, opened, tag)
    else:
        log = box.exec(f"/usr/bin/tail -c 3000 -- {APP_LOG_DIR}/{tag}.log", 20)
        shown.log_tail = log.stdout if log.exit_code == 0 else ""
    code = 0 if shown.tier == "window" and png is not None and not opened.timed_out and not survived else 1
    result = ExecResult(command=command, exit_code=code,
                        stdout=observation(shown, opened.approved, kept=keep_running, clicked=opened.clicked,
                                           restarted=opened.restarted, updates=len(opened.updates)),
                        stderr=app_facts(shown, opened.approved), seconds=opened.seconds, timed_out=opened.timed_out)
    return result, shown, png


# A scroll: wheel buttons sent over Virtualization.framework's VNC never reach the guest (11/3: a Finder window did
# not move), so pickfit posts the wheel event in sbx's session. Posted from anything tart-guest-agent starts, TCC
# asks whether tart-guest-agent may "control this computer" (PostEvent) and drops it; osascript started by launchd
# is its own responsible process and holds PostEvent on the GUI base, so the event lands, with no prompt.
SCROLL_PX = 300  # pixels per scroll: about a third of an ordinary window
SCROLL_RAN_S = 10  # launchd starts a submitted job at once; a KeepAlive restart waits 10 s, and the job is gone by then
_SCROLL_JXA = ('ObjC.import("CoreGraphics"); var e = $.CGEventCreateScrollWheelEvent2(null, 0, 1, @DY@, 0, 0); '
               '$.CGEventSetLocation(e, {x: @X@, y: @Y@}); $.CGEventPost(0, e);')


def post_scroll(box: TartBox, x: int, y: int, direction: str, *, sleep: Any = time.sleep) -> None:
    """One wheel scroll at (x, y) of the screen, up or down, as a one-off launchd job in sbx's session."""
    dy = {"up": SCROLL_PX, "down": -SCROLL_PX}.get(direction)  # positive moves the content down: a scroll up
    if dy is None:
        raise ValueError(f"unknown scroll direction {direction!r}")
    script = _SCROLL_JXA.replace("@DY@", str(dy)).replace("@X@", str(int(x))).replace("@Y@", str(int(y)))
    label = f"pickfit.scroll.{secrets.token_hex(4)}"
    session = ["/bin/launchctl", "asuser", str(MAC_UID), "/bin/launchctl"]
    done = box.harness_exec([*session, "submit", "-l", label, "--", "/usr/bin/osascript", "-l", "JavaScript", "-e",
                             script], 30)
    if done.exit_code != 0:
        raise BoxError(f"launchctl submit exited {done.exit_code}: {done.stderr.strip()[-200:]}")
    try:
        deadline = time.monotonic() + SCROLL_RAN_S
        while True:
            listed = box.harness_exec([*session, "list", label], 15).stdout
            if '"LastExitStatus"' in listed and '"PID"' not in listed:
                break
            if time.monotonic() > deadline:
                raise BoxError("the scroll did not run")
            sleep(0.2)
        if not re.search(r'"LastExitStatus" = 0;', listed):
            raise BoxError("the scroll did not post: " + " ".join(listed.split())[-200:])
    finally:
        box.harness_exec([*session, "remove", label], 15)


class VncDisplay:
    """The VM's display as pickfit drives it from the host: the operating loop's Display (gui_operate.Display).

    screenshot -> PNG bytes once the screen has settled, click(x, y, count), type_text, key, scroll, and with a
    box, clipboard. Coordinates are pixels of the screenshot (1280x800 on the GUI base). Key names are X
    keysyms and `+` combinations (Return, BackSpace, ctrl+slash) with the Mac's own modifiers (cmd+s,
    option+left); see vnc.parse_key. Nothing runs in the guest for it but the clipboard read and, with a box, a
    scroll (post_scroll). A VNC failure is the loop's DisplayError.
    """

    os = "macos"  # the operating loop speaks of a Mac's desktop and keeps cmd apart from ctrl

    def __init__(self, url: str, box: TartBox | None = None) -> None:
        self._client = VncClient.from_url(url)
        self._box = box

    def _connected(self) -> VncClient:
        if self._client.sock is None:
            self._client.connect()
        return self._client

    def _do(self, what: str, fn: Any, *args: Any) -> Any:
        from pickfit.verify.gui_operate import DisplayError

        try:
            return fn(*args)
        except (VncError, OSError, ValueError, BoxError) as err:
            raise DisplayError(f"{what} over VNC failed: {err}") from err

    @property
    def size(self) -> tuple[int, int]:
        client = self._client if self._client.width else self._connected()
        return client.width, client.height

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    def _frame(self) -> bytes:
        try:
            return self._client.screenshot()
        except VncError:  # a dropped connection: one more try (a screenshot changes nothing)
            return self._client.screenshot()

    def screenshot(self) -> bytes:
        """The whole screen as PNG once two frames SETTLE_GAP_S apart agree (at most SETTLE_MAX_S)."""
        return self._do("screenshot", self._settled)

    def _settled(self) -> bytes:
        frame = self._frame()
        deadline = time.monotonic() + SETTLE_MAX_S
        while time.monotonic() < deadline:
            time.sleep(SETTLE_GAP_S)
            later = self._frame()
            if later == frame:
                break
            frame = later
        return frame

    def click(self, x: int, y: int, count: int = 1) -> None:
        self._do("click", lambda: self._connected().click(x, y, count=max(1, min(int(count), 3))))

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y, 2)

    def right_click(self, x: int, y: int) -> None:
        self._do("right-click", lambda: self._connected().click(x, y, button="right"))

    def type_text(self, text: str) -> None:
        self._do("typing", lambda: self._connected().type_text(text))

    def key(self, name: str) -> None:
        self._do(f"key {name}", lambda: self._connected().key(name))

    def scroll(self, x: int, y: int, direction: str) -> None:
        if self._box is None:
            self._do("scroll", lambda: self._connected().scroll(x, y, direction))
        else:
            self._do("scroll", lambda: post_scroll(self._box, x, y, direction))

    def clipboard(self) -> bytes | None:
        """The box user's pasteboard as text, read in its desktop session (None when it holds no text)."""
        if self._box is None:
            return None
        got = self._box.harness_exec(["/bin/launchctl", "asuser", str(MAC_UID), "/usr/bin/sudo", "-n", "-u",
                                      MAC_USER, "/usr/bin/pbpaste", "-Prefer", "txt"], 30)
        return got.stdout.encode() if got.exit_code == 0 and got.stdout else None

    def close(self) -> None:
        self._client.close()
