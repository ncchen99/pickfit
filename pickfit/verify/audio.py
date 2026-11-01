"""A simulated microphone in a Linux box (P3.13): pickfit speaks fresh random words into it, the app under test
records them, and pickfit finds the words in what the app produced.

- Root starts PulseAudio as DISPLAY_UID (pickfit's harness uid: not the box user, not root) in the harness's own
  network namespace (loopback only, the display's), with only the modules it loads at start: a null sink pickfit
  plays into (SPEAKER), the sink's monitor remapped as a plain source (MIC, the default source, so apps that skip
  monitor sources still see a microphone), and the native protocol on a socket file in AUDIO_DIR that any local
  client may use (auth-anonymous; no TCP module). After start the server refuses to load or unload a module and to
  exit (--disallow-module-loading, --disallow-exit): a client cannot make it read a file as DISPLAY_UID, open a
  port or stop. The box user's apps reach it by its socket file (a network namespace does not hide one), found by
  PULSE_SERVER, /etc/pulse/client.conf.d (autospawn off) and ALSA's default device (the pulse plugin), so arecord,
  parecord, ffmpeg -f pulse, PortAudio, GStreamer and SDL all record from MIC.
- Speech: flite (CMU, BSD-style licence, its built-in cmu_us_slt voice), run by DISPLAY_UID on a text file it writes
  from stdin in EVIDENCE_DIR (mode 0700, closed to the box user). The words are never on a command line (any uid can
  read /proc/<pid>/cmdline), in an environment, a file name or a stream name the box user can see. Playback is
  paplay as DISPLAY_UID into SPEAKER: the sentence, a pause, again, until pickfit stops it, so a recording of a few
  seconds made at any moment holds the whole sentence.
- The check is pickfit's (gui_operate.py's rules): every word, as a whole word in any case, in a file the app wrote
  after the operation began (read by root), on the clipboard, in text the screen judge read on pickfit's own
  screenshot, or, for a command-line tool (listen), in what the command printed. A word the operator typed shows
  nothing. A fresh set of words is spoken for every operation and every replay.
"""

from __future__ import annotations

import re
import secrets
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator

from pickfit.verify import gui
from pickfit.verify.box import ExecResult

if TYPE_CHECKING:
    from pickfit.verify.box import Box

# xdotool-free: everything here is the harness's. flite speaks; pulseaudio-utils plays; alsa-utils and the ALSA pulse
# plugin give ALSA apps the same source.
AUDIO_PACKAGES = ("pulseaudio", "pulseaudio-utils", "alsa-utils", "libasound2-plugins", "flite")
AUDIO_DIR = "/run/pickfit-audio"  # DISPLAY_UID's, 0755: only the server's socket is in it
PULSE_SOCKET = f"{AUDIO_DIR}/native"
PULSE_SERVER = f"unix:{PULSE_SOCKET}"
PULSE_HOME = f"{gui.EVIDENCE_DIR}/pulse"  # the server's own files (cookie, runtime dir): closed to the box user
PULSE_LOG = f"{gui.EVIDENCE_DIR}/pulse.log"
SPEAKER = "pickfit_speaker"
MIC = "pickfit_mic"
MODULES = (f"module-null-sink sink_name={SPEAKER} rate=16000 channels=1 "
           "sink_properties=device.description=pickfit-speaker",
           f"module-remap-source master={SPEAKER}.monitor source_name={MIC} "
           "source_properties=device.description=Microphone",
           f"module-native-protocol-unix socket={PULSE_SOCKET} auth-anonymous=1")
CLIENT_CONF = f"default-server = {PULSE_SERVER}\nautospawn = no\n"
ASOUND_CONF = "pcm.!default { type pulse }\nctl.!default { type pulse }\n"
VOICE = "slt"  # flite's cmu_us_slt (CMU ARCTIC), built into Debian's flite
SPEECH_STRETCH = 1.1  # a little slower than flite's default
PAUSE_S = 1.5  # between two sayings of the sentence
LEAD_S = 0.8  # silence before the sentence when a program opens the microphone (capture starts a little late)
PLAY_MAX_S = 1800  # a player pickfit failed to stop dies anyway
LISTEN_MAX_S = 600  # a listen's command, at most (the box caps it too)
SPOKEN_FIELD = "{spoken}"
# What a run records about the box's microphone (VerificationRun.microphone).
MICROPHONE = "simulated: a PulseAudio source playing fresh random words pickfit spoke with flite for each check"
WORD_COUNT = 3

# Concrete, common English nouns that sound like no other word on the list and that speech recognizers spell one
# way (no homophones, numbers, names, compounds or British/American pairs: Whisper wrote "yoghurt"). Calibrated
# 2026-11-02: each of 196 words spoken twice by flite in these sentences; the 40 that Whisper tiny.en or base.en
# missed even once are out. Three of the 156 left, in any order: about 1 in 620,000 for a guess.
WORDS = (
    "anchor", "apple", "banana", "basket", "beaver", "bicycle", "blanket", "bracelet", "bridge", "bucket",
    "buffalo", "butter", "button", "cabbage", "cactus", "camera", "candle", "canoe", "carpet", "carrot", "castle",
    "cherry", "chimney", "circus", "cobra", "coconut", "compass", "cookie", "copper", "cotton", "cowboy", "crayon",
    "crystal", "cushion", "dentist", "diamond", "dinosaur", "doctor", "drummer", "eagle", "elbow", "elephant",
    "engine", "envelope", "falcon", "feather", "festival", "finger", "forest", "fountain", "galaxy", "garage",
    "garden", "garlic", "giraffe", "glacier", "gorilla", "helmet", "hippo", "hospital", "igloo", "jacket", "jungle",
    "kangaroo", "kitchen", "kitten", "koala", "lantern", "lemon", "leopard", "library", "lobster", "magnet",
    "mango", "marble", "meadow", "melon", "mermaid", "meteor", "mirror", "monkey", "mountain", "muffin", "museum",
    "noodle", "ocean", "octopus", "onion", "orange", "orchestra", "oven", "paddle", "panda", "parrot", "peanut",
    "pelican", "pencil", "penguin", "pepper", "piano", "pickle", "pillow", "pizza", "pocket", "potato", "pumpkin",
    "puppet", "pyramid", "rabbit", "raccoon", "radio", "rainbow", "river", "robot", "rocket", "saddle", "salmon",
    "sandal", "satellite", "saucer", "scarf", "shadow", "shovel", "silver", "skeleton", "spider", "squirrel",
    "station", "statue", "stomach", "strawberry", "submarine", "sunset", "sweater", "tablet", "telescope", "tennis",
    "tiger", "tomato", "tornado", "tractor", "trumpet", "tunnel", "umbrella", "unicorn", "valley", "velvet",
    "village", "violin", "volcano", "waffle", "window", "blossom", "cinnamon", "hamster", "pineapple",
)


def new_words(count: int = WORD_COUNT) -> list[str]:
    """Distinct words from WORDS, chosen with the system's secure random source."""
    pool = list(WORDS)
    return [pool.pop(secrets.randbelow(len(pool))) for _ in range(count)]


def sentence(words: list[str]) -> str:
    """What flite says: the words in a plain sentence. Measured 2026-11-02 (6 sets, Whisper base.en): a list of
    single words lost one in three; the sentence kept all three in 5 of 6 (the miss was "yoghurt")."""
    named = [f"{'an' if w[0] in 'aeiou' else 'a'} {w}" for w in words]
    return f"I saw {', '.join(named[:-1])}, and {named[-1]}.\n"


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def heard(text: str, words: list[str]) -> list[bool]:
    """Whether each word is in the text as a whole word, in any case (a transcript capitalizes and punctuates)."""
    found = tokens(text)
    return [w.lower() in found for w in words]


# A result may name a few other words of the list (a word misheard as another); one that names more is a list, not
# a transcript: the list is public, and printing all of it would hold any three words.
OTHERS_MAX = 3


def others(text: str, words: list[str]) -> list[str]:
    """The list's words in the text that were not spoken."""
    found, spoken = tokens(text), {w.lower() for w in words}
    return [w for w in WORDS if w in found and w not in spoken]


def too_many(extra: list[str]) -> str | None:
    """Why a result naming these unspoken list words shows nothing; None when it names few enough."""
    if len(extra) <= OTHERS_MAX:
        return None
    return (f"it also names {len(extra)} other words of pickfit's list ({', '.join(extra[:6])}"
            f"{'...' if len(extra) > 6 else ''}): a list of words, not a transcript")


def typed_words(words: list[str], typed: list[str]) -> list[str]:
    """The spoken words the operator typed itself: a result holding them shows nothing."""
    found = tokens(" ".join(typed))
    return [w for w in words if w.lower() in found]


# ---------------------------------------------------------------- the server (root starts it)


def pulse_script(drop_argv: tuple[str, ...]) -> str:
    """Root: the client configuration every program reads, the server's directories, then PulseAudio as DISPLAY_UID
    (`drop_argv`: into the harness's network namespace, setpriv to DISPLAY_UID, its filter and an empty
    environment), detached; MIC is made the default source. Prints `pulse_pid N` once the socket answers."""
    drop = " ".join(drop_argv)
    loads = " ".join(f"-L {shlex.quote(m)}" for m in MODULES)
    pactl = f"{drop} /usr/bin/pactl --server={PULSE_SERVER}"
    return (f"/usr/bin/install -d -m 0755 /etc/pulse/client.conf.d && "
            f"/usr/bin/printf %s {shlex.quote(CLIENT_CONF)} > /etc/pulse/client.conf.d/00-pickfit.conf && "
            f"/usr/bin/printf %s {shlex.quote(ASOUND_CONF)} > /etc/asound.conf && "
            f"/usr/bin/install -d -m 0700 -o {gui.DISPLAY_UID} -g {gui.DISPLAY_UID} {gui.EVIDENCE_DIR} {PULSE_HOME} && "
            f"/usr/bin/install -d -m 0755 -o {gui.DISPLAY_UID} -g {gui.DISPLAY_UID} {AUDIO_DIR} && "
            f"{{ /usr/bin/setsid {drop} HOME={PULSE_HOME} XDG_RUNTIME_DIR={PULSE_HOME} /usr/bin/pulseaudio "
            "--daemonize=no --system=no -n --disallow-module-loading --disallow-exit --exit-idle-time=-1 "
            "--use-pid-file=no --realtime=no --high-priority=no --log-target=stderr "
            f"{loads} < /dev/null > {PULSE_LOG} 2>&1 & }}; "
            f"for i in $(/usr/bin/seq 1 60); do {pactl} info > /dev/null 2>&1 && break; /usr/bin/sleep 0.25; done; "
            f"{pactl} set-default-source {MIC} && "
            f"echo \"pulse_pid $(/usr/bin/pgrep -u {gui.DISPLAY_UID} -x pulseaudio)\" || "
            f"{{ /usr/bin/tail -5 {PULSE_LOG}; exit 1; }}")


# ---------------------------------------------------------------- speaking (DISPLAY_UID, in EVIDENCE_DIR)


def _as_harness(box: Box, script: str, timeout_s: int, stdin: bytes | None = None) -> ExecResult:
    return box.harness_exec(["/usr/bin/bash", "-c", script], timeout_s, as_uid=gui.DISPLAY_UID, stdin=stdin)


def speak(box: Box, words: list[str], tag: str | int) -> tuple[str | None, str | None]:
    """flite says the words into a WAV in EVIDENCE_DIR; (its path, None) or (None, why). The words travel on stdin."""
    name = f"{gui.EVIDENCE_DIR}/speech-{tag}-{secrets.token_hex(4)}"
    script = (f"umask 077 && /usr/bin/cat > {name}.txt && /usr/bin/flite -voice {VOICE} "
              f"--setf duration_stretch={SPEECH_STRETCH} -f {name}.txt -o {name}.wav && /usr/bin/rm -f {name}.txt && "
              f"/usr/bin/stat -c 'wav_bytes %s' {name}.wav")
    done = _as_harness(box, script, 60, stdin=sentence(words).encode())
    size = next((int(line.split()[1]) for line in done.stdout.splitlines() if line.startswith("wav_bytes ")), 0)
    if done.exit_code != 0 or size < 1000:
        return None, f"flite failed (exit {done.exit_code}): {(done.stdout + done.stderr).strip()[-200:]}"
    return f"{name}.wav", None


def start_playback(box: Box, wav: str) -> tuple[int | None, str | None]:
    """DISPLAY_UID plays the WAV into SPEAKER, again after each pause, until stopped; (its process group, None).

    Each time a program opens a recording stream (a new source-output), the loop starts over with LEAD_S of
    silence, so a recorder that stops at the first pause hears the whole sentence, not its tail.
    """
    paplay = f"/usr/bin/paplay --server={PULSE_SERVER} --device={SPEAKER} {wav}"
    # USR1 kills the step in progress and starts again from the lead; `wait` returns at once for a trapped signal.
    player = ("trap 'kill -KILL $c 2>/dev/null; r=1' USR1; while :; do r=0; "
              f"for s in '/usr/bin/sleep {LEAD_S}' {shlex.quote(paplay)} '/usr/bin/sleep {PAUSE_S}'; do "
              "$s & c=$!; wait $c; [ $r = 1 ] && break; done; done")
    loop = (f"/usr/bin/bash -c {shlex.quote(player)} & p=$!; "
            f"/usr/bin/stdbuf -oL /usr/bin/pactl --server={PULSE_SERVER} subscribe | while read -r l; do "
            "case $l in *\"'new' on source-output\"*) kill -USR1 $p;; esac; done")
    script = (f"{{ /usr/bin/setsid /usr/bin/timeout -s KILL {PLAY_MAX_S} /usr/bin/bash -c {shlex.quote(loop)} "
              "> /dev/null 2>&1 < /dev/null & }; echo \"player $!\"")
    done = _as_harness(box, script, 30)
    pid = next((line.split()[1] for line in done.stdout.splitlines() if line.startswith("player ")), "")
    if done.exit_code != 0 or not pid.isdigit():
        return None, f"playback did not start: {(done.stdout + done.stderr).strip()[-200:]}"
    time.sleep(0.3)
    return int(pid), None


def stop_playback(box: Box, pid: int | None) -> None:
    """Stop the player's process group (setsid made the player its leader; Xvfb and the server are not in it)."""
    if pid:
        _as_harness(box, f"/usr/bin/kill -KILL -- -{int(pid)} 2>/dev/null; true", 20)


# ---------------------------------------------------------------- listen: a command-line tool and the microphone


class ListenCheck(BaseModel):
    kind: Literal["output", "file"]
    path: str | None = Field(default=None, description="file: the file the command writes (a folder ending in /).")

    @field_validator("path", mode="before")
    @classmethod
    def _nulls(cls, value: Any) -> Any:
        return None if isinstance(value, str) and value.strip().lower() in {"", "null", "none"} else value


class ListenArgs(BaseModel):
    command: str = Field(min_length=1)
    timeout_s: int = 120
    feature: int | None = None
    check: ListenCheck

    @field_validator("feature", mode="before")
    @classmethod
    def _nulls(cls, value: Any) -> Any:
        return None if isinstance(value, str) and value.strip().lower() in {"", "null", "none"} else value


def listen_problems(args: ListenArgs) -> list[str]:
    """Why pickfit cannot run this check as asked; [] when it can."""
    problems: list[str] = []
    if SPOKEN_FIELD in args.command:
        problems.append("the command cannot name the words: pickfit speaks them, the tool must hear them")
    if args.check.kind == "file":
        from pickfit.verify.gui_operate import home_path

        if not args.check.path:
            problems.append("a file check needs the path of the file the command writes (or a folder ending in /)")
        else:
            try:
                home_path(args.check.path)
            except ValueError as err:
                problems.append(str(err))
    elif args.check.path:
        problems.append("an output check takes no path")
    return problems


@dataclass
class Listening:
    """How one listen went; `passed` is pickfit's check."""

    feature: int | None
    command: str
    check: dict[str, Any]
    words: list[str]
    passed: bool = False
    line: str = ""
    why: str | None = None
    exit_code: int | None = None
    seconds: float = 0.0
    error: str | None = None
    seen: dict[str, Any] = field(default_factory=dict)
    speech: str | None = None  # the WAV pickfit played, in EVIDENCE_DIR (root can copy it out as evidence)


MIC_PASSED_LINE = "mic check: passed"
MIC_NOTE = (f"mic: pickfit spoke {WORD_COUNT} fresh words (flite, voice cmu_us_slt) into the box's simulated "
            f"microphone ({MIC}, PulseAudio) while the command ran; the box never had them as text")


def run_listen(box: Box, args: ListenArgs, tag: str | int, *, log: Callable[[str], None] = print
               ) -> tuple[ExecResult, Listening]:
    """Speak fresh words into the microphone while the box user runs the command, then check its output or file."""
    from pickfit.verify.gui_operate import file_probe, home_path

    began = time.monotonic()
    words = new_words()
    run = Listening(feature=args.feature, command=args.command, check=args.check.model_dump(), words=words)
    problems = listen_problems(args)
    result: ExecResult | None = None
    if problems:
        run.error = "; ".join(problems)
    elif not box.audio:
        run.error = "this box has no simulated microphone"
    else:
        wav, why = speak(box, words, tag)
        run.speech = wav
        target = home_path(args.check.path) if args.check.kind == "file" and args.check.path else None
        before = file_probe(box, {"mode": "before", "target": target}) if target else {}
        pid, why = start_playback(box, wav) if wav else (None, why)
        if pid is None:
            run.error = why
        else:
            try:
                result = box.exec(args.command, max(5, min(int(args.timeout_s), LISTEN_MAX_S)))
            finally:
                stop_playback(box, pid)
            run.exit_code = result.exit_code
            if result.timed_out:
                run.error = "the command timed out"
            if target:
                _check_file(box, run, target, before)
            else:
                _check_output(run, f"{result.stdout}\n{result.stderr}")
    if run.error and not run.why:
        run.why = run.error
        run.line = run.line or "not checked"
    run.passed = run.passed and run.error is None
    run.seconds = round(time.monotonic() - began, 1)
    lines = [MIC_NOTE]
    if run.exit_code is not None:
        lines.append(f"mic command: exited {run.exit_code}{' (timed out)' if result and result.timed_out else ''}")
    if run.error:
        lines.append(f"note: {run.error[:300]}")
    lines.append(f"mic result: {run.line or 'not checked'}")
    lines.append(MIC_PASSED_LINE if run.passed else f"mic check: failed ({run.why or 'the check did not pass'})")
    app = "--- the command's own output (data) ---\n" + (
        f"{result.stdout[-2500:]}\n{result.stderr[-1500:]}".strip() if result else "")
    log(f"    mic check {'passed' if run.passed else 'failed'} · {run.line[:160]}")
    return ExecResult(command=args.command, exit_code=0 if run.passed else 1, stdout="\n".join(lines), stderr=app,
                      seconds=run.seconds, timed_out=bool(result and result.timed_out)), run


def _quote(text: str) -> str:
    return '"' + text.replace('"', "'") + '"'


def words_line(where: str, words: list[str], found: list[bool]) -> str:
    return f"{where}: " + "; ".join(f"{_quote(w)}: {'yes' if f else 'no'}" for w, f in zip(words, found))


def _check_output(run: Listening, text: str) -> None:
    found = heard(text, run.words)
    listed = too_many(others(text, run.words))
    run.passed = all(found) and listed is None
    run.line = words_line("the command's output holds the spoken words", run.words, found)
    run.seen = {"output": text.strip()[-300:]}
    if not run.passed:
        run.why = listed or "the output does not hold every spoken word"


def _check_file(box: Box, run: Listening, target: str, before: dict[str, Any]) -> None:
    from pickfit.verify.gui_operate import file_probe

    since = float(before.get("now") or 0.0)
    report = file_probe(box, {"mode": "after", "target": target, "since": since - 1, "before": before.get("before"),
                              "words": run.words, "listed": list(WORDS)})
    found = report.get("found")
    if "error" in report or not found:
        run.why = report.get("error") or report.get("why") or "not found"
        run.line = f"file {target}: {run.why}"
        return
    hits = list(found.get("words") or [])
    listed = too_many(list(found.get("others") or []))
    run.passed = bool(hits) and all(hits) and listed is None
    run.line = words_line(f"file {found['path']} ({found['bytes']} bytes, written after the command started) holds "
                          "the spoken words", run.words, hits)
    run.seen = {"path": found["path"], "excerpt": found.get("excerpt")}
    if not run.passed:
        run.why = listed or "the file does not hold every spoken word"
