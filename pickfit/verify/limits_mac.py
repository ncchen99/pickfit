"""`pickfit verify --runner tart --display --limits-test`: the macOS GUI box's own checks (loop/issues.md H-014).

This module plays limits.py's role for a TartBox made with display=True. limits.py's display checks are Xvfb's
(xdpyinfo, pgrep Xvfb, the X socket) and can only fail in a macOS guest, so run_gui_limits_test runs
limits.run_limits_test on a view of the box whose display is None: every macOS check limits.py has (non_admin, su,
kcpassword, the root containment controls, the network cut, the caps) runs unchanged, in sbx's desktop session as a
GUI box's commands do. Then it adds the GUI box's own. No model is called.

Functional:
- desktop_screenshot: sbx is the console user with its Dock and Finder running, and pickfit's VNC screenshot (taken
  on the host) is the whole 1280x800 screen with something on it.
- app_window_seen: TextEdit, opened as sbx in its session, shows up in pickfit's window list (from WindowServer, the
  owner's executable from the kernel, through pickfit's own helper) and inside those bounds in the screenshot.
- report_unforgeable: a launch that prints a forged report line and leaves a detached child behind reaches no window
  and leaves nothing running: what pickfit reports comes from its root helper's output, keyed by a fresh nonce, while
  the app's own output goes to the app's log (mirrors limits.py's display_report_unforgeable).

Configuration, read-only where it can be. Each has a `_control`: the same check on something set the other way, which
it must flag, so a check that cannot see the setting fails instead of passing:
- sbx_standard_user: sbx is not in admin or wheel (control: admin is in admin).
- helper_locked: sbx cannot write pickfit's helpers (control: it can write its own app log directory).
- vnc_log_owner_only: the VNC address and password are in the host's VM log, owned by the host user and mode 600
  (control: /etc/hosts, 644, fails the same check).
- vnc_password_not_in_guest: no copy of the password in the guest's files, logs, command lines or environments
  (control: a decoy of the same shape planted in sbx's work dir is found). The password never enters the guest:
  the guest returns hashes of every string of that shape and the host compares.
- tcc_grants_scoped: the system TCC database grants Screen Recording, Accessibility, Input Monitoring, PostEvent,
  Full Disk Access, AppleEvents, microphone or camera only to programs sbx cannot write or impersonate (control: a
  copy with two such grants planted fails the same check).
- tcc_box_user_none: a program sbx installs and starts as its own launchd job gets none of Screen Recording,
  Accessibility, Input Monitoring or PostEvent, even after sbx writes grants for it into its own TCC database, and
  neither does a command run the way the model's commands run (control: pickfit's scroll helper, osascript as a
  launchd job in sbx's session, holds PostEvent).
- window_server_not_box_user: WindowServer is _windowserver's and sbx's kill -0 of it is refused (control: sbx's
  kill -0 of its own Dock works).
- vnc_port_unreachable: with @host allowed the guest reaches the host's VNC port (control), and with the online and
  offline policies it drops (curl exit 28).

Measured on the real host (11/18, macOS 15 guest): loginwindow runs as the console user, sbx (macOS runs the
console user's loginwindow as that user), so "loginwindow is not sbx's" is not a setting the box can have; the
check records its owner instead. Ending it only logs sbx out, and every launch's watcher fails when sbx's session is
not on screen. Screen Recording is used by nothing of pickfit's in the guest (screenshots come over VNC on the host;
the helper's window list needs no titles), so the box keeps none; tart_box drops the source image's other grants at
start (TCC_SCOPE). /usr/bin/osascript keeps Accessibility and PostEvent for gui_mac.post_scroll. sbx can start that
Apple binary as a launchd job too and then holds Accessibility, Input Monitoring and PostEvent (measured): control of
a desktop session that is sbx's own, where pickfit types no secret. Left open in loop/issues.md H-014.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import secrets
import shlex
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pickfit.ledger import taipei_now
from pickfit.verify import gui
from pickfit.verify.box import BoxError, ExecResult
from pickfit.verify.limits import ProbeResult, _detail, run_limits_test, save_limits
from pickfit.verify.tart_box import (
    CURL_DROP,
    DESKTOP_UP,
    GUEST_PYTHON,
    GUI_DISPLAY,
    HELPER_DIR,
    HOST_REACHED,
    MAC_UID,
    MAC_USER,
    MAC_WORKDIR,
    ROOT_PATH,
    TCC_DB,
    TCC_SERVICES,
)

TEXTEDIT = "/System/Applications/TextEdit.app/Contents/MacOS/TextEdit"
WINDOW_WAIT_S = 25
CHANGED_SHARE = 0.25  # of the window's pixels that must differ from the screenshot before it opened
# tart's VNC password: four lowercase words joined by hyphens (measured 11/18 in the host's VM logs).
SECRET_SHAPE = rb"(?<![a-z0-9-])[a-z]{2,12}(?:-[a-z]{2,12}){3}(?![a-z0-9-])"
SCAN_ROOTS = ("/Users", "/private/tmp", "/private/var/tmp", "/private/var/log", "/private/var/root", "/Library/Logs",
              "/Library/Preferences", "/private/etc", "/usr/local", "/opt/homebrew/var")
SCAN_BUDGET_S = 120
TCC_PREFLIGHT = ('ObjC.import("CoreGraphics"); ObjC.import("ApplicationServices"); '
                 'ObjC.bindFunction("CGPreflightScreenCaptureAccess", ["bool", []]); '
                 'ObjC.bindFunction("CGPreflightPostEventAccess", ["bool", []]); '
                 'ObjC.bindFunction("CGPreflightListenEventAccess", ["bool", []]); '
                 'JSON.stringify({screen: $.CGPreflightScreenCaptureAccess(), ax: $.AXIsProcessTrusted(), '
                 'post: $.CGPreflightPostEventAccess(), listen: $.CGPreflightListenEventAccess()})')
TCC_KINDS = ("screen", "ax", "post", "listen")
JOB_WAIT_S = 20

# Root, in sbx's desktop session: pickfit's installed helper (gui_mac.HELPER) loaded as it is, then its own window
# list and process table: [[pid, layer, x, y, width, height, executable, an sbx process]] and the screen size.
WINDOWS_PY = f"""import json, sys
sys.argv = ["gui", "-"]
exec(compile(open("{HELPER_DIR}/gui").read(), "{HELPER_DIR}/gui", "exec"))
screen, found = windows()
mine = procs()
rows = []
for w in found:
    b = w.get("kCGWindowBounds") or {{}}
    pid = w.get("kCGWindowOwnerPID")
    rows.append([pid, w.get("kCGWindowLayer"), int(b.get("X", 0)), int(b.get("Y", 0)), int(b.get("Width", 0)),
                 int(b.get("Height", 0)), exe(pid), str(pid) in mine])
print(json.dumps({{"screen": screen, "windows": rows}}))
"""

# Root: every string of the secret's shape in the guest's files (SCAN_ROOTS, no symlinks followed, files up to 4 MB),
# the guest agent's logs and every process's command line and environment, as sha256 prefixes. stdin: the roots.
SCAN_PY = r"""import hashlib, json, os, re, subprocess, sys, time
cfg = json.loads(sys.stdin.read())
shape = re.compile(cfg["shape"].encode())
found, files, big, began = set(), 0, 0, time.time()
def take(data):
    for m in shape.finditer(data):
        found.add(hashlib.sha256(m.group(0)).hexdigest()[:16])
timed_out = False
for root in cfg["roots"]:
    for here, dirs, names in os.walk(root):
        if time.time() - began > cfg["budget_s"]:
            timed_out = True
            break
        for name in names:
            path = os.path.join(here, name)
            try:
                if os.path.islink(path) or not os.path.isfile(path):
                    continue
                if os.path.getsize(path) > 4_000_000:
                    big += 1
                    continue
                with open(path, "rb") as fh:
                    take(fh.read())
                files += 1
            except OSError:
                pass
ps = subprocess.run(["/bin/ps", "-axeww", "-o", "command="], capture_output=True).stdout if cfg["ps"] else b""
take(ps)
print(json.dumps({"files": files, "too_big": big, "timed_out": timed_out, "hashes": sorted(found),
                  "processes": ps.count(b"\n"), "vnc_urls": ps.count(b"vnc://")}))
"""

# Root: the allowed grants of TCC_SERVICES in each database named on argv, and which a program sbx controls could use.
# A path is safe when it and every directory above it are root's and writable by nobody else; a bundle id only with
# a code requirement anchored to Apple (a grant with none matches any app that claims the id).
TCC_PY = r"""import json, os, sqlite3, subprocess, sys, tempfile
services = json.loads(sys.stdin.read())["services"]
def chain_safe(p):
    while True:
        try:
            st = os.lstat(p)
        except OSError:
            return False
        if st.st_uid != 0 or (st.st_mode & 0o022 and not os.path.islink(p)):
            return False
        if p == "/":
            return True
        p = os.path.dirname(p)
def safe_path(path):  # the path as written and where its links lead
    return path.startswith("/") and chain_safe(path) and chain_safe(os.path.realpath(path))
def apple_req(blob):
    if not blob:
        return False
    with tempfile.NamedTemporaryFile(dir="/var/root") as fh:
        fh.write(blob)
        fh.flush()
        text = subprocess.run(["/usr/bin/csreq", "-r", fh.name, "-t"], capture_output=True, text=True).stdout
    return "anchor apple" in text and "anchor apple generic" not in text
out = {}
for db in sys.argv[1:]:
    rows = sqlite3.connect(f"file:{db}?mode=ro", uri=True).execute(
        "select service, client, client_type, auth_value, csreq from access").fetchall()
    kept, bad = [], []
    for service, client, kind, value, req in rows:
        if service not in services or value != 2:
            continue
        ok = safe_path(client) if kind == 1 else apple_req(req)
        (kept if ok else bad).append(f"{service.removeprefix('kTCCService')} {client}")
    out[db] = {"rows": len(rows), "kept": kept, "bad": bad}
print(json.dumps(out))
"""


class NoDisplay:
    """The box as limits.run_limits_test sees it: the same box, with no display. Its commands still run in sbx's
    desktop session (the box itself still has one); only limits.py's Xvfb checks are left out."""

    display = None

    def __init__(self, box: Any) -> None:
        self.box = box

    def __getattr__(self, name: str) -> Any:
        return getattr(self.box, name)


def _result(name: str, ok: bool, expect: str, r: ExecResult | None, detail: str) -> ProbeResult:
    return ProbeResult(name, bool(ok), expect, r.exit_code if r else None, r.seconds if r else 0.0,
                       " ".join(detail.split())[-300:])


def _root(box: Any, script: str, timeout_s: int = 60, stdin: bytes | None = None) -> ExecResult:
    return box.harness_exec(["/bin/sh", "-c", f"{ROOT_PATH}\n{script}"], timeout_s, stdin=stdin)


def _json(r: ExecResult) -> Any:
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------- functional


def _image(png: bytes) -> Any:
    from PIL import Image

    return Image.open(io.BytesIO(png)).convert("L")


def screen_size() -> tuple[int, int]:
    w, h = re.findall(r"\d+", GUI_DISPLAY)[:2]
    return int(w), int(h)


def changed_share(before: Any, after: Any, box_xywh: tuple[int, int, int, int]) -> float:
    """The share of pixels inside the box that differ by more than 16 levels between two grey screenshots."""
    x, y, w, h = box_xywh
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(before.size[0], x + w), min(before.size[1], y + h)
    if x1 <= x0 or y1 <= y0 or before.size != after.size:
        return 0.0
    a, b = before.crop((x0, y0, x1, y1)).tobytes(), after.crop((x0, y0, x1, y1)).tobytes()
    return sum(abs(p - q) > 16 for p, q in zip(a, b)) / len(a)


def _desktop(box: Any) -> tuple[ProbeResult, Any]:
    """sbx's desktop is on screen and pickfit's VNC screenshot shows it. Waits up to a minute for the session, since
    limits.py's process cap just filled sbx's process table."""
    deadline = time.monotonic() + 60
    while True:
        up = _root(box, DESKTOP_UP, 30)
        if up.exit_code == 0 or time.monotonic() > deadline:
            break
        time.sleep(3)
    img, why = None, ""
    try:
        png = box.screen().screenshot()
        img = _image(png)
        lo, hi = img.getextrema()
        why = f"png {len(png)} bytes {img.size[0]}x{img.size[1]}, grey levels {lo}-{hi}"
        shown = png[:8] == b"\x89PNG\r\n\x1a\n" and img.size == screen_size() and hi - lo > 30
    except Exception as err:  # noqa: BLE001  (a failed screenshot fails the check, it does not end the test)
        shown, why = False, f"screenshot failed: {type(err).__name__}: {err}"
    return _result("desktop_screenshot", up.exit_code == 0 and shown,
                   f"{MAC_USER} is the console user with Dock and Finder running, and pickfit's VNC screenshot is the "
                   "whole {}x{} screen with something on it".format(*screen_size()), up,
                   f"{_detail(up) or 'desktop up'}; {why}"), img


def windows(box: Any) -> dict[str, Any] | None:
    """pickfit's window list in sbx's session (the installed helper's own code): screen size and window rows."""
    got = box.harness_exec(["/bin/launchctl", "asuser", str(MAC_UID), GUEST_PYTHON, "-I", "-c", WINDOWS_PY], 60,
                           stdin=b"{}")
    data = _json(got) if got.exit_code == 0 else None
    return data if isinstance(data, dict) else None


def app_window(listing: dict[str, Any] | None, executable: str = TEXTEDIT) -> list[Any] | None:
    """The first normal window (layer 0) of an sbx process running `executable`, at least gui.MIN_WIDTH x
    gui.MIN_HEIGHT."""
    for row in (listing or {}).get("windows", []):
        _pid, layer, _x, _y, w, h, exe, mine = row
        if layer == 0 and exe == executable and mine and w >= gui.MIN_WIDTH and h >= gui.MIN_HEIGHT:
            return row
    return None


def _app_window(box: Any, before: Any) -> ProbeResult:
    from pickfit.verify import gui_mac

    path = f"{MAC_WORKDIR}/pf-limits.txt"
    box.write_file(path, "\n".join(f"pickfit limits test, line {i}" for i in range(40)) + "\n")
    started = box.harness_exec(gui_mac.start_argv(f"/usr/bin/open -a TextEdit {path}", "limits-textedit"), 30)
    deadline, row, listing = time.monotonic() + WINDOW_WAIT_S, None, None
    while row is None and time.monotonic() < deadline:
        time.sleep(2)
        listing = windows(box)
        row = app_window(listing)
    share, why = 0.0, ""
    if row is not None:
        time.sleep(1)
        try:
            after = _image(box.screen().screenshot())
            share = changed_share(before, after, tuple(row[2:6])) if before is not None else 0.0
        except Exception as err:  # noqa: BLE001
            why = f"screenshot failed: {err}"
    pids = sorted({r[0] for r in (listing or {}).get("windows", []) if r[6] == TEXTEDIT})
    stopped = _root(box, f"kill -9 {' '.join(map(str, pids))} 2>/dev/null; sleep 1; "
                    f"pgrep -u {MAC_UID} -x TextEdit || echo stopped", 30) if pids else None
    ok = ("started" in started.stdout and row is not None and share >= CHANGED_SHARE
          and stopped is not None and "stopped" in stopped.stdout)
    where = f"window {row[4]}x{row[5]} at {row[2]},{row[3]} pid {row[0]}" if row else "no TextEdit window"
    return _result("app_window_seen", ok, "TextEdit opened as sbx shows up in pickfit's window list (WindowServer's "
                   "owner pid, the kernel's executable, an sbx process) and inside those bounds in the VNC screenshot "
                   f"(at least {CHANGED_SHARE:.0%} of its pixels changed); stopped after", started,
                   f"{where}; {share:.0%} of it changed {why}; screen {(listing or {}).get('screen')}")


def _unforgeable(box: Any) -> ProbeResult:
    from pickfit.verify import gui_mac

    sleeper = f"{MAC_WORKDIR}/pf-sleeper"  # not macOS's executable, so the watcher counts it as the app's
    forged = (f"/bin/cp /bin/sleep {sleeper}; printf '{gui.MARK}0 {{\"windows\": [{{\"id\": \"0x1\", \"title\": "
              f"\"forged\", \"width\": 900, \"height\": 700, \"pid\": 1}}]}}\\n'; "
              f"({gui_mac.DETACH_CMD} {sleeper} 60 &); exit 3")
    launched, shown, _png = gui_mac.launch(box, forged, "limits-forged", 8)
    now = gui_mac.procs(box)
    session = box.session or {}
    left = sorted({v[1] for p, v in (now or {}).items() if session.get(p, [None])[0] != v[0]
                   and not v[1].startswith(gui_mac.RESPAWNED_PREFIXES)}) if now is not None else ["?"]
    ran = bool(shown.alive) and "pf-sleeper" in shown.processes  # the control: the detached child was running
    printed = f"{gui.MARK}0 " in (shown.log_tail or "")  # and the forged line was printed, into the app's own log
    ok = (ran and printed and shown.tier != "window" and launched.exit_code != 0 and not left
          and not any(w.title == "forged" for w in shown.windows))
    return _result("report_unforgeable", ok, "a launch that prints a forged report and leaves a detached child (seen "
                   "running) reaches no window and leaves nothing running: the report is the root helper's, keyed by "
                   "a fresh nonce; the app's output goes to its log", launched,
                   f"tier {shown.tier}; child seen {ran}; forged line in the app's log {printed}; left {left}; "
                   f"windows {[w.title for w in shown.windows]}")


# ---------------------------------------------------------------- configuration


def membership(user: str) -> str:
    return (f"dsmemberutil checkmembership -U {user} -G admin; dsmemberutil checkmembership -U {user} -G wheel; "
            "dscl . -read /Groups/admin GroupMembership")


def standard_user(stdout: str, user: str) -> bool:
    """dsmemberutil says not a member of admin and of wheel, and admin's GroupMembership does not list the user."""
    lines = stdout.splitlines()
    listed = next((line.split()[1:] for line in lines if line.startswith("GroupMembership:")), None)
    return (lines[:2] == ["user is not a member of the group"] * 2 and listed is not None and user not in listed)


def _standard_user(box: Any, add: Callable[[ProbeResult], None]) -> None:
    mine = _root(box, membership(MAC_USER), 30)
    add(_result("sbx_standard_user", mine.exit_code == 0 and standard_user(mine.stdout, MAC_USER),
                f"{MAC_USER} is not in admin or wheel (dsmemberutil, admin's GroupMembership)", mine, _detail(mine)))
    admin = _root(box, membership("admin"), 30)
    add(_result("sbx_standard_user_control", admin.exit_code == 0 and "user is a member of the group" in admin.stdout
                and not standard_user(admin.stdout, "admin"), "the same check flags admin, who is in admin", admin,
                _detail(admin)))


def _helper_locked(box: Any, add: Callable[[ProbeResult], None]) -> None:
    from pickfit.verify import gui_mac

    paths = [HELPER_DIR, *(f"{HELPER_DIR}/{n}" for n in ("gui", "timeout", "detach", "mdns"))]
    probe = ("for f in " + " ".join(paths) + "; do test -w $f && echo \"writable $f\"; done; "
             f"mkdir -p {gui_mac.APP_LOG_DIR} && test -w {gui_mac.APP_LOG_DIR} && echo \"own {gui_mac.APP_LOG_DIR}\"; "
             "true")
    r = box.exec(probe, 20)
    add(_result("helper_locked", r.exit_code == 0 and "writable" not in r.stdout,
                "sbx cannot write pickfit's helpers (the window watcher, timeout, detach, mdns) or their directory", r,
                _detail(r) or "none writable"))
    add(_result("helper_locked_control", f"own {gui_mac.APP_LOG_DIR}" in r.stdout,
                "the same test sees a directory sbx can write (its app log directory)", r, _detail(r)))


def owner_only(stdout: str) -> bool:
    """`stat -f '%Su %Lp' FILE; id -un`: the file is the host user's, mode 600."""
    lines = stdout.split("\n")
    return len(lines) >= 2 and lines[0].split() == [lines[1].strip(), "600"]


def _vnc_log(box: Any, add: Callable[[ProbeResult], None]) -> None:
    def stat(path: str) -> ExecResult:
        began = time.monotonic()
        done = box.host.run(["/bin/sh", "-c", 'stat -f "%Su %Lp" "$1" && id -un && grep -c "vnc://" "$1"', "sh", path],
                            timeout=60)
        return ExecResult(f"stat {path}", done.returncode, done.stdout, done.stderr, round(time.monotonic() - began, 2))

    log = stat(str(box.vm_log))
    urls = log.stdout.split("\n")[2:3]
    port = int(box.vnc_host_port or 0)
    listen = box.host.run(["/bin/sh", "-c", f"netstat -an -p tcp | grep -E '[.:]{port} .*LISTEN'"],
                          timeout=60).stdout.split()
    add(_result("vnc_log_owner_only", owner_only(log.stdout) and urls != ["0"] and bool(urls),
                f"the VNC address and password are on the host ({box.host.name}), in the VM's log (it holds the "
                "vnc:// line), owned by the host user, mode 600", log,
                f"{' '.join(log.stdout.split()[:3])} vnc lines {urls}; server listens on {listen[3:4]}"))
    hosts = stat("/etc/hosts")
    add(_result("vnc_log_owner_only_control", hosts.stdout.strip() != "" and not owner_only(hosts.stdout),
                "the same check fails a file that is not owner-only (the host's /etc/hosts)", hosts,
                " ".join(hosts.stdout.split()[:3])))


def decoy() -> str:
    return "-".join("".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(6)) for _ in range(4))


def _short(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _vnc_secret(box: Any, add: Callable[[ProbeResult], None]) -> None:
    from pickfit.verify.vnc import parse_url

    password = parse_url(box.vnc_url)[2] if box.vnc_url else ""
    planted = decoy()
    box.write_file(f"{MAC_WORKDIR}/pf-decoy.txt", f"a string of the same shape: {planted}\n")
    try:
        cfg = {"shape": SECRET_SHAPE.decode(), "roots": list(SCAN_ROOTS), "budget_s": SCAN_BUDGET_S, "ps": True}
        scan = box.harness_exec([GUEST_PYTHON, "-I", "-c", SCAN_PY], SCAN_BUDGET_S + 120,
                                stdin=json.dumps(cfg).encode())
    finally:
        box.exec(f"rm -f {MAC_WORKDIR}/pf-decoy.txt", 20)
    data = _json(scan) if scan.exit_code == 0 else None
    found = set(data.get("hashes", [])) if isinstance(data, dict) else set()
    shaped = re.fullmatch(SECRET_SHAPE, password.encode()) is not None
    ran = isinstance(data, dict) and not data.get("timed_out") and data.get("files", 0) > 0
    summary = (f"{data.get('files')} files, {data.get('too_big')} over 4 MB, {data.get('processes')} processes, "
               f"{len(found)} strings of the shape" if isinstance(data, dict) else _detail(scan))
    add(_result("vnc_password_not_in_guest", ran and shaped and _short(password) not in found,
                "no copy of the VNC password in the guest: files under " + ", ".join(SCAN_ROOTS) + ", every "
                "command line and environment (root's scan; only hashes leave the guest)", scan,
                f"{summary}; the password has the scanned shape: {shaped}"))
    add(_result("vnc_password_not_in_guest_control", ran and _short(planted) in found,
                "the same scan finds a decoy of the same shape planted in sbx's work dir", scan, summary))


def tcc_bad(data: Any, db: str = TCC_DB) -> list[str] | None:
    """The grants TCC_PY found that a program sbx controls could use; None when the database was not read."""
    entry = data.get(db) if isinstance(data, dict) else None
    return list(entry.get("bad", [])) if isinstance(entry, dict) and entry.get("rows") else None


def _tcc_db(box: Any, add: Callable[[ProbeResult], None]) -> None:
    stdin = json.dumps({"services": list(TCC_SERVICES)}).encode()
    live = box.harness_exec([GUEST_PYTHON, "-I", "-c", TCC_PY, TCC_DB], 60, stdin=stdin)
    data = _json(live)
    bad = tcc_bad(data)
    kept = data[TCC_DB].get("kept", []) if bad is not None else []
    add(_result("tcc_grants_scoped", bad == [], "the system TCC database grants " + ", ".join(
        s.removeprefix("kTCCService") for s in TCC_SERVICES) + " only to programs sbx cannot write (root's path, "
        "nothing above it writable by others) or impersonate (an Apple-anchored code requirement)", live,
        f"kept {kept}; bad {bad}"))
    copy = "/var/root/pf-tcc-control.db"
    planted = ("INSERT OR REPLACE INTO access (service, client, client_type, auth_value, auth_reason, auth_version) "
               "VALUES ('kTCCServiceScreenCapture', '/opt/homebrew/bin/pf-planted', 1, 2, 3, 1), "
               "('kTCCServiceAccessibility', 'org.example.pf-planted', 0, 2, 3, 1)")
    made = _root(box, f"cp '{TCC_DB}' {copy} && chmod 600 {copy} && sqlite3 {copy} \"{planted}\"", 30)
    try:
        control = box.harness_exec([GUEST_PYTHON, "-I", "-c", TCC_PY, copy], 60, stdin=stdin)
    finally:
        _root(box, f"rm -f {copy}", 20)
    flagged = tcc_bad(_json(control), copy) or []
    add(_result("tcc_grants_scoped_control", made.exit_code == 0 and {"ScreenCapture /opt/homebrew/bin/pf-planted",
                "Accessibility org.example.pf-planted"} <= set(flagged),
                "the same check flags a copy of the database with Screen Recording planted for a path sbx owns and "
                "Accessibility for a bundle id with no code requirement", control, f"flagged {flagged}"))


def preflight(stdout: str) -> dict[str, bool] | None:
    try:
        data = json.loads(stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return {k: data.get(k) is True for k in TCC_KINDS} if isinstance(data, dict) else None


def _job(box: Any, argv: list[str]) -> tuple[ExecResult, dict[str, bool] | None]:
    """argv as a one-off launchd job in sbx's session, as gui_mac.post_scroll starts osascript: its own responsible
    process, as an app opened by LaunchServices is. (the job's output, its TCC preflight)"""
    label = f"pickfit.limits.{secrets.token_hex(4)}"
    out = f"/tmp/{label}.out"
    session = ["/bin/launchctl", "asuser", str(MAC_UID), "/bin/launchctl"]
    box.harness_exec(["/bin/rm", "-f", out], 20)
    submitted = box.harness_exec([*session, "submit", "-l", label, "-o", out, "-e", out, "--", *argv], 30)
    got = submitted
    try:
        deadline = time.monotonic() + JOB_WAIT_S
        while submitted.exit_code == 0 and time.monotonic() < deadline:
            time.sleep(1)
            got = box.harness_exec(["/bin/cat", out], 20)
            if preflight(got.stdout) is not None:
                break
    finally:
        box.harness_exec([*session, "remove", label], 20)
        box.harness_exec(["/bin/rm", "-f", out], 20)
    return got, preflight(got.stdout)


def _tcc_user(box: Any, add: Callable[[ProbeResult], None]) -> None:
    js = ["-l", "JavaScript", "-e", TCC_PREFLIGHT]
    own_db = f"/Users/{MAC_USER}/Library/Application Support/com.apple.TCC/TCC.db"
    probe = f"{MAC_WORKDIR}/pf-tcc-probe"  # a copy of osascript: the same code, at a path sbx owns
    rows = ", ".join(f"('kTCCService{s}', '{probe}', 1, 2, 3, 1)"
                     for s in ("ScreenCapture", "Accessibility", "PostEvent", "ListenEvent"))
    plant = box.exec(f"cp /usr/bin/osascript {probe} && sqlite3 '{own_db}' \"INSERT OR REPLACE INTO access (service, "
                     f"client, client_type, auth_value, auth_reason, auth_version) VALUES {rows}\" && echo planted", 30)
    try:
        app, app_tcc = _job(box, [probe, *js])
        cmd = box.exec(f"/usr/bin/osascript {shlex.join(js)}", 60)
        cmd_tcc = preflight(cmd.stdout)
    finally:
        box.exec(f"sqlite3 '{own_db}' \"DELETE FROM access WHERE client = '{probe}'\"; rm -f {probe}", 30)
    def none(seen: dict[str, bool] | None) -> bool:
        return seen is not None and not any(seen.values())

    add(_result("tcc_box_user_none", "planted" in plant.stdout and none(app_tcc) and none(cmd_tcc),
                "a program sbx installs, started as its own launchd job (even with grants sbx wrote into its own TCC "
                "database), and a command run as the model's commands run get no Screen Recording, Accessibility, "
                "Input Monitoring or PostEvent", app, f"sbx's program {app_tcc}; model command {cmd_tcc}; "
                f"plant {_detail(plant)}"))
    helper, helper_tcc = _job(box, ["/usr/bin/osascript", *js])
    add(_result("tcc_box_user_none_control", helper_tcc is not None and helper_tcc["post"],
                "the same preflight sees a grant: pickfit's scroll helper (osascript as a launchd job in sbx's "
                "session) holds PostEvent", helper, f"pickfit's osascript {helper_tcc}"))


def window_server(rows: str) -> dict[str, tuple[str, str]]:
    """`ps -axo uid=,pid=,comm=` -> {name: (uid, pid)} for WindowServer, loginwindow and Dock (first of each)."""
    out: dict[str, tuple[str, str]] = {}
    for line in rows.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3:
            name = parts[2].rsplit("/", 1)[-1]
            if name in ("WindowServer", "loginwindow", "Dock") and name not in out:
                out[name] = (parts[0], parts[1])
    return out


def _window_server(box: Any, add: Callable[[ProbeResult], None]) -> None:
    seen = window_server(_root(box, "ps -axo uid=,pid=,comm=", 30).stdout)
    ws, dock = seen.get("WindowServer", ("?", "0")), seen.get("Dock", ("?", "0"))
    r = box.exec(f"kill -0 {int(ws[1])} 2>&1; echo \"ws=$?\"; kill -0 {int(dock[1])} 2>&1; echo \"dock=$?\"", 20)
    owners = f"WindowServer uid {ws[0]}, loginwindow uid {seen.get('loginwindow', ('?',))[0]}, Dock uid {dock[0]}"
    add(_result("window_server_not_box_user", ws[0] not in ("?", str(MAC_UID)) and ws[1] != "0"
                and "Operation not permitted" in r.stdout and "ws=1" in r.stdout,
                f"WindowServer is not {MAC_USER}'s and {MAC_USER}'s kill -0 of it is refused (loginwindow is the "
                "console user's own by macOS's design: recorded, not judged)", r, f"{owners}; {_detail(r)}"))
    add(_result("window_server_not_box_user_control", dock[0] == str(MAC_UID) and "dock=0" in r.stdout,
                f"the same kill -0 works on {MAC_USER}'s own Dock", r, f"{owners}; {_detail(r)}"))


def _vnc_port(box: Any, add: Callable[[ProbeResult], None]) -> None:
    port = int(box.vnc_host_port or 0)
    target = {"vnc": f"http://$gw:{port}/"}
    began = time.monotonic()
    try:
        box.control.set_rules(allow=["@host"], block=[])
        allowed = box._curl_codes(target, 4)[0]["vnc"]
    finally:
        box.control.set_policy(True)
        box.network_enabled = True
    box._check_firewall(online=True)
    online = box._curl_codes(target, 4)[0]["vnc"]
    box.set_network(False)
    try:
        offline = box._curl_codes(target, 4)[0]["vnc"]
    finally:
        box.set_network(True)
    seconds = round(time.monotonic() - began, 2)
    add(ProbeResult("vnc_port_unreachable", port > 0 and online == CURL_DROP and offline == CURL_DROP,
                    f"the guest, as root, gets no reply from the host's VNC port {port} online or offline (exit 28)",
                    None, seconds, f"online exit {online}, offline exit {offline}"))
    add(ProbeResult("vnc_port_unreachable_control", allowed in HOST_REACHED,
                    "with @host allowed the same probe reaches the port (the probe is not a no-op)", None, seconds,
                    f"allowed exit {allowed}"))


# ---------------------------------------------------------------- the test


def gui_probes(box: Any, add: Callable[[ProbeResult], None]) -> None:
    """The macOS GUI box's own checks, in a started TartBox with display=True. Each check that raises is recorded as
    failed and the rest still run; the network is back on afterwards."""
    before: list[Any] = [None]  # the desktop's screenshot, before TextEdit opens

    def desktop() -> None:
        result, before[0] = _desktop(box)
        add(result)

    steps: list[tuple[str, Callable[[], None]]] = [
        ("desktop_screenshot", desktop),
        ("app_window_seen", lambda: add(_app_window(box, before[0]))),
        ("report_unforgeable", lambda: add(_unforgeable(box))),
        ("sbx_standard_user", lambda: _standard_user(box, add)),
        ("helper_locked", lambda: _helper_locked(box, add)),
        ("vnc_log_owner_only", lambda: _vnc_log(box, add)),
        ("vnc_password_not_in_guest", lambda: _vnc_secret(box, add)),
        ("tcc_grants_scoped", lambda: _tcc_db(box, add)),
        ("tcc_box_user_none", lambda: _tcc_user(box, add)),
        ("window_server_not_box_user", lambda: _window_server(box, add)),
        ("vnc_port_unreachable", lambda: _vnc_port(box, add)),
    ]
    for name, step in steps:
        try:
            step()
        except (BoxError, OSError, ValueError, KeyError, TypeError) as err:
            add(ProbeResult(name, False, f"{name} completes", None, 0.0, f"{type(err).__name__}: {err}"[-300:]))
    if not box.network_enabled:
        box.set_network(True)


def run_gui_limits_test(box: Any, log: Callable[[str], None] = print) -> list[ProbeResult]:
    """limits.py's checks on the box without its display, then the macOS GUI box's own (module doc)."""
    results = run_limits_test(NoDisplay(box), log)

    def add(result: ProbeResult) -> None:
        results.append(result)
        log(f"  {'ok  ' if result.ok else 'FAIL'} {result.name}: {result.expect} · exit {result.exit_code} · "
            f"{result.seconds:.1f}s · {result.detail[:140]}")

    gui_probes(box, add)
    return results


def gui_limits_test(make_box: Callable[[str, str], Any], runs_dir: Path, log: Callable[[str], None] = print
                    ) -> tuple[list[ProbeResult], Path]:
    """limits.limits_test for a macOS GUI box."""
    began = time.monotonic()
    box = make_box(f"limits-{taipei_now().strftime('%Y%m%d-%H%M%S')}", "limits")
    if not getattr(box, "display", None) or getattr(box, "os", None) != "macos":
        raise ValueError("the macOS GUI limits test needs a TartBox made with display=True")
    try:
        box.start()
        log(f"limits test · {box.runner} · {box.image} · desktop over VNC · started in {box.start_s}s")
        results = run_gui_limits_test(box, log)
    finally:
        box.close()
    path = save_limits(results, box, runs_dir)
    log(f"limits test · {sum(r.ok for r in results)}/{len(results)} held · {time.monotonic() - began:.0f}s · {path}")
    return results, path
