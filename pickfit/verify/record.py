"""Screen recordings of pickfit operating an app: the raw material of a verification video (video.py).

A recording runs from just before the app starts until pickfit's check has looked at the screen, one per
operation (gui_operate.run_operation). It is pickfit's, never the app's: the app cannot start, stop or touch it.

- Linux (XvfbRecorder): ffmpeg's x11grab reads pickfit's own Xvfb as DISPLAY_UID (never the box user), in the
  display's network namespace, and writes into EVIDENCE_DIR (mode 0700, the display uid's). ffmpeg prints the
  wall-clock time of its first frame; the display uid's hands stamp each action in the same clock (the box's).
  Root stops it with SIGINT, hashes the file and copies it out; the host copy must match that hash.
- macOS (VncRecorder): a host thread takes a frame of the VM's display at a fixed rate, each the first frame
  of a new VNC connection (vnc.VncClient.capture: a held connection gets stale frames), draws the pointer
  where pickfit last put it (VNC frames carry none), and pipes it to the host's ffmpeg. The operating loop
  stamps each action in the host's clock, which is the recording's.

Recordings are made at RECORD_FPS: Muse Spark Open samples at most 2 frames a second and placed changes
within 0.5 s at 2 fps or more (probe, 11/2). Which operations are recorded: PICKFIT_RECORD=all (every one),
off (none), else only a replay's (tag replay-...): the replay is the run whose checks a record keeps.
A recorder that fails never fails the operation: the recording is just missing, with the reason.
"""

from __future__ import annotations

import hashlib
import io
import re
import shlex
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from pickfit.env import get_env
from pickfit.verify import gui

if TYPE_CHECKING:
    from pickfit.verify.box import Box

RECORD_FPS = 4
MAX_SECONDS = 900  # a backstop: an operation takes 28 actions at most
MAX_BYTES = 40_000_000  # ffmpeg stops writing past this (-fs)
PART_BYTES = 8_000_000  # the host copies a recording out of the box in parts of this size
COPY_READS = 3  # a long read can come back short when the box's output stream is slow (gui.SHOT_READS)
START_WAIT_S = 10.0
STOP_WAIT_S = 15.0
ENCODE = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p", "-g", str(RECORD_FPS * 2),
          # fragmented: a recording cut short (a box that dies, a killed ffmpeg) is still playable up to there
          "-movflags", "+frag_keyframe+empty_moov+default_base_moof")
_START = re.compile(r"Input #0, x11grab.*?start: (\d+(?:\.\d+)?)", re.S)


def wanted(tag: str | int) -> bool:
    """Whether to record this operation (PICKFIT_RECORD: all, off, or by default a replay's only)."""
    setting = (get_env("PICKFIT_RECORD") or "replay").strip().lower()
    if setting in ("off", "0", "no", "false"):
        return False
    return setting == "all" or str(tag).startswith("replay-")


@dataclass
class Recording:
    """One raw recording; `started_at` is the wall-clock time of its first frame in `clock`, the clock the
    operation's step stamps (gui_operate.Step.at) use, so an action's place in the video is at - started_at."""

    path: str | None  # on the host
    sha256: str | None
    bytes: int = 0
    started_at: float | None = None
    seconds: float | None = None
    fps: int = RECORD_FPS
    width: int = 0
    height: int = 0
    clock: str = ""  # box: the Linux box's clock; host: this machine's
    recorder: str = ""  # x11grab, vnc
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Recorder(Protocol):
    def start(self) -> None: ...

    def stop(self) -> Recording: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_seconds(path: Path) -> float | None:
    """The file's duration by the host's ffprobe (None without ffprobe or a readable file)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    done = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True, timeout=60)
    try:
        return round(float(done.stdout.strip()), 2)
    except ValueError:
        return None


def for_box(box: Box, tag: str | int, evidence_dir: Path | None) -> Recorder | None:
    """A recorder for this box's display, or None (no display, nowhere to keep it, or not wanted)."""
    if evidence_dir is None or not wanted(tag):
        return None
    if box.os == "macos":
        return VncRecorder(box, evidence_dir / f"{tag}.mp4")
    if box.display and getattr(box, "xvfb_pid", None):
        return XvfbRecorder(box, tag, evidence_dir / f"{tag}.mp4")
    return None


# ---------------------------------------------------------------- Linux: ffmpeg x11grab in the box


def ffmpeg_argv(out: str) -> list[str]:
    """The display uid's ffmpeg: pickfit's Xvfb, its pointer drawn, to `out` (in EVIDENCE_DIR)."""
    return ["/usr/bin/ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info", "-f", "x11grab", "-draw_mouse", "1",
            "-framerate", str(RECORD_FPS), "-video_size", f"{gui.SCREEN_W}x{gui.SCREEN_H}", "-i", gui.DISPLAY,
            "-t", str(MAX_SECONDS), "-fs", str(MAX_BYTES), *ENCODE, "-f", "mp4", out]


def start_script(enter: list[str], seccomp: list[str], out: str, log: str) -> str:
    """Root: the display uid's ffmpeg, detached (its output to `log`, so this command returns); prints its pid."""
    drop = ["/usr/bin/setpriv", f"--reuid={gui.DISPLAY_UID}", f"--regid={gui.DISPLAY_UID}", "--clear-groups",
            "--inh-caps=-all", "--no-new-privs", "--"]
    env = ["/usr/bin/env", "-i", f"PATH={gui.HARNESS_PATH}", f"HOME={gui.EVIDENCE_DIR}", f"DISPLAY={gui.DISPLAY}"]
    argv = [*enter, *drop, *seccomp, *env, *ffmpeg_argv(out)]
    return (f"/usr/bin/rm -f -- {shlex.quote(out)} {shlex.quote(log)}; "
            f"{{ /usr/bin/setsid {shlex.join(argv)} < /dev/null > {shlex.quote(log)} 2>&1 & }}; "
            "echo \"rec_pid $!\"")


def stop_script(pid: int, out: str) -> str:
    """Root: SIGINT (ffmpeg finishes the file), SIGKILL after STOP_WAIT_S; then the file's size and hash."""
    rounds = int(STOP_WAIT_S / 0.25)
    return (f"p={int(pid)}; if [ \"$(/usr/bin/cat /proc/$p/comm 2>/dev/null)\" = ffmpeg ]; then "
            f"/usr/bin/kill -INT $p; for i in $(/usr/bin/seq 1 {rounds}); do /usr/bin/kill -0 $p 2>/dev/null || break; "
            f"/usr/bin/sleep 0.25; done; /usr/bin/kill -KILL $p 2>/dev/null && echo killed; fi; "
            f"echo \"size $(/usr/bin/stat -c %s -- {shlex.quote(out)})\"; /usr/bin/sha256sum -- {shlex.quote(out)}")


def first_frame_at(log: str) -> float | None:
    """The wall-clock time of x11grab's first frame, from ffmpeg's input line ("start: 1762052345.123456")."""
    found = _START.search(log)
    return float(found.group(1)) if found else None


class XvfbRecorder:
    """ffmpeg x11grab of pickfit's Xvfb, as the display uid, in the box."""

    def __init__(self, box: Box, tag: str | int, host_path: Path) -> None:
        self.box, self.host_path = box, host_path
        self.out = f"{gui.EVIDENCE_DIR}/{tag}.mp4"
        self.log = f"{gui.EVIDENCE_DIR}/{tag}.rec.log"
        self.pid: int | None = None
        self.rec = Recording(path=None, sha256=None, clock="box", recorder="x11grab", width=gui.SCREEN_W,
                             height=gui.SCREEN_H)

    def _root(self, script: str, timeout_s: int = 30) -> Any:
        return self.box.harness_exec(["/usr/bin/bash", "-c", script], timeout_s)

    def start(self) -> None:
        try:
            script = start_script(self.box.display_enter(), self.box.seccomp(), self.out, self.log)
            started = self._root(script)
            pid = next((line.split()[1] for line in started.stdout.splitlines() if line.startswith("rec_pid ")), "")
            self.pid = int(pid) if pid.isdigit() else None
            if self.pid is None:
                raise RuntimeError(f"ffmpeg did not start: {started.stderr.strip()[-200:]}")
            deadline = time.monotonic() + START_WAIT_S
            while time.monotonic() < deadline:
                log = self._root(f"/usr/bin/cat -- {shlex.quote(self.log)}").stdout
                self.rec.started_at = first_frame_at(log)
                if self.rec.started_at is not None:
                    return
                if "Exiting" in log or "Error" in log or "error" in log.lower().split("input #0")[0][-400:]:
                    raise RuntimeError(f"ffmpeg failed: {log.strip()[-300:]}")
                time.sleep(0.3)
            raise RuntimeError("ffmpeg printed no first frame in time")
        except Exception as err:  # never the operation's failure
            self.rec.error = f"recording did not start: {type(err).__name__}: {err}"[:400]

    def stop(self) -> Recording:
        if self.pid is None:
            return self.rec
        try:
            done = self._root(stop_script(self.pid, self.out), int(STOP_WAIT_S) + 30)
            size = next((line.split()[1] for line in done.stdout.splitlines() if line.startswith("size ")), "")
            digest = next((line.split()[0] for line in done.stdout.splitlines() if re.match(r"^[0-9a-f]{64} ", line)), "")
            if not size.isdigit() or not digest:
                raise RuntimeError(f"no recording to copy: {(done.stdout + done.stderr).strip()[-200:]}")
            data = copy_out(self.box, self.out, int(size), digest)
            self.host_path.parent.mkdir(parents=True, exist_ok=True)
            self.host_path.write_bytes(data)
            self.rec.path, self.rec.sha256, self.rec.bytes = str(self.host_path), digest, len(data)
            self.rec.seconds = probe_seconds(self.host_path)
            if "killed" in done.stdout.split():
                self.rec.error = "ffmpeg did not stop on SIGINT and was killed: the end of the file may be cut"
        except Exception as err:
            self.rec.error = f"recording not kept: {type(err).__name__}: {err}"[:400]
        return self.rec


def copy_out(box: Box, path: str, size: int, sha256: str) -> bytes:
    """A file of pickfit's evidence copied out by root, in parts of PART_BYTES, checked against its hash."""
    if size > MAX_BYTES + PART_BYTES:
        raise RuntimeError(f"{size} bytes is more than a recording may be")
    parts = [path]
    if size > PART_BYTES:
        prefix = f"{path}.part."
        split = box.harness_exec(["/usr/bin/split", "-b", str(PART_BYTES), "-d", "-a", "3", "--", path, prefix], 60)
        if split.exit_code != 0:
            raise RuntimeError(f"split failed: {split.stderr.strip()[-200:]}")
        parts = [f"{prefix}{i:03d}" for i in range((size + PART_BYTES - 1) // PART_BYTES)]
    data = bytearray()
    for i, part in enumerate(parts):
        want = min(PART_BYTES, size - i * PART_BYTES) if len(parts) > 1 else size
        got = b""
        for _ in range(COPY_READS):
            got = box.harness_read(part, want)
            if len(got) == want:
                break
        if len(got) != want:
            raise RuntimeError(f"copy of {part} incomplete after {COPY_READS} reads ({len(got)} of {want} bytes)")
        data += got
    if hashlib.sha256(data).hexdigest() != sha256:
        raise RuntimeError("the copy does not match the hash root took in the box")
    return bytes(data)


# ---------------------------------------------------------------- macOS: VNC frames on the host


def draw_pointer(frame: bytes, width: int, height: int, x: int, y: int) -> bytes:
    """A plain arrow where pickfit last put the pointer (BGRX bytes in, BGRX bytes out)."""
    from PIL import Image, ImageDraw

    img = Image.frombytes("RGBX", (width, height), frame)  # channel order does not matter for black and white
    draw = ImageDraw.Draw(img)
    arrow = [(x, y), (x, y + 18), (x + 5, y + 14), (x + 9, y + 22), (x + 12, y + 20), (x + 8, y + 13), (x + 14, y + 13)]
    draw.polygon(arrow, fill=(255, 255, 255, 0), outline=(0, 0, 0, 0))
    return img.tobytes()


def fit(width: int, height: int, frame: bytes, to_w: int, to_h: int) -> bytes:
    """A BGRX frame at the recording's size (a frame of another size is scaled to it)."""
    if (width, height) == (to_w, to_h):
        return frame
    from PIL import Image

    return Image.frombytes("RGBX", (width, height), frame).resize((to_w, to_h)).tobytes()


class VncRecorder:
    """Frames of a tart VM's display at RECORD_FPS, encoded by the host's ffmpeg."""

    def __init__(self, box: Box, host_path: Path, fps: int = RECORD_FPS) -> None:
        self.box, self.host_path, self.fps = box, host_path, fps
        self.rec = Recording(path=None, sha256=None, clock="host", recorder="vnc", fps=fps)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self.frames = 0
        self.captures = 0

    def _pointer(self) -> tuple[int, int] | None:
        screen = getattr(self.box, "_screen", None)
        client = getattr(screen, "_client", None)
        pointer = getattr(client, "pointer", None) if client is not None and client.sock is not None else None
        return pointer if pointer and pointer != (0, 0) else None  # (0, 0): pickfit has not moved it yet

    def start(self) -> None:
        from pickfit.verify.vnc import VncClient

        try:
            ffmpeg = shutil.which("ffmpeg")
            url = getattr(self.box, "vnc_url", None)
            if not ffmpeg or not url:
                raise RuntimeError("no ffmpeg on the host" if not ffmpeg else "the box has no VNC display")
            client = VncClient.from_url(url)
            # The recording takes the display's size as pickfit drives it (VncDisplay): a new connection's first
            # frame has come back at another size, black (1280x720 on the 1280x800 desktop, 11/2).
            screen = self.box.screen() if hasattr(self.box, "screen") else None
            width, height = screen.size if screen is not None else client.capture()[:2]
            self.rec.width, self.rec.height = width, height
            frame = fit(*client.capture(), width, height)
            self.host_path.parent.mkdir(parents=True, exist_ok=True)
            self.host_path.unlink(missing_ok=True)
            self._proc = subprocess.Popen(
                [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr0",
                 "-video_size", f"{width}x{height}", "-framerate", str(self.fps), "-i", "-", "-t", str(MAX_SECONDS),
                 "-fs", str(MAX_BYTES), *ENCODE, "-f", "mp4", str(self.host_path)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.rec.started_at = time.time()
            self._thread = threading.Thread(target=self._run, args=(client, frame), daemon=True)
            self._thread.start()
        except Exception as err:
            self.rec.error = f"recording did not start: {type(err).__name__}: {err}"[:400]

    def _emit(self, frame: bytes) -> None:
        """Every frame due by now: frame k shows the screen at started_at + k / fps (the latest capture by then)."""
        assert self._proc is not None and self._proc.stdin is not None and self.rec.started_at is not None
        due = min((time.time() - self.rec.started_at) * self.fps, MAX_SECONDS * self.fps)
        while self.frames <= due:
            pointer = self._pointer()
            self._proc.stdin.write(draw_pointer(frame, self.rec.width, self.rec.height, *pointer) if pointer else frame)
            self.frames += 1

    def _run(self, client: Any, frame: bytes) -> None:
        assert self.rec.started_at is not None
        latest = frame
        try:
            while not self._stop.is_set():
                self._emit(latest)
                self._stop.wait(max(0.0, self.rec.started_at + self.frames / self.fps - time.time()))
                latest = fit(*client.capture(), self.rec.width, self.rec.height)  # a new connection's first frame
                self.captures += 1
            self._emit(latest)
        except Exception as err:  # the VM went away, or ffmpeg did
            self.rec.error = f"recording cut short: {type(err).__name__}: {err}"[:400]

    def stop(self) -> Recording:
        if self._proc is None:
            return self.rec
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        try:
            _, err = self._proc.communicate(timeout=60)  # closes ffmpeg's stdin: the end of the video
            if self._proc.returncode != 0:
                raise RuntimeError(f"ffmpeg exited {self._proc.returncode}: {err.decode(errors='replace')[-200:]}")
            self.rec.path, self.rec.sha256 = str(self.host_path), sha256_file(self.host_path)
            self.rec.bytes = self.host_path.stat().st_size
            self.rec.seconds = probe_seconds(self.host_path) or round(self.frames / self.fps, 2)
        except Exception as err:
            self._proc.kill()
            self.rec.error = "; ".join(filter(None, [self.rec.error, f"recording not kept: {type(err).__name__}: {err}"]))[:400]
        return self.rec


def png_frame(path: Path, at_s: float) -> bytes:
    """One frame of a recording as PNG, at `at_s` seconds (for looking at a clip without playing it)."""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    done = subprocess.run([ffmpeg, "-v", "error", "-ss", f"{at_s:.2f}", "-i", str(path), "-frames:v", "1", "-f",
                           "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60)
    if done.returncode != 0 or not done.stdout:
        raise RuntimeError(f"no frame at {at_s}s: {done.stderr.decode(errors='replace')[-200:]}")
    return io.BytesIO(done.stdout).getvalue()
