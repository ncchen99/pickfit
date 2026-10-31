"""The verdict comes from the command log, not from what the model says (P3.3 gap).

`finish` cites commands by their command_id; the program looks each one up in
the log and decides from what actually ran:

- a step counts only if it exited 0 and its exit code was not masked
  (`|| true`, `; echo $?`, a trailing `| head`, a background `&`);
- a smoke test passes only if its recorded exit code is the expected one, the
  exit code was not masked, the expected signal appears in its output, and the
  output shows no crash; a non-zero expected exit (a linter that found
  problems) needs the signal;
- the level is the weaker of the claim and what the passing checks support:
  install needs a passing check, function a README example (not only
  --version/--help), service a background server, inference a generation
  request against it. A GUI launch (launch_gui: a window of the app's own)
  supports install only: a GUI app is not function until an action is shown
  to change checkable state, which pickfit does not check yet;
- for an MCP server (mcp.py), only pickfit's probe counts: function needs its
  completed handshake, service a tool call; nothing else passes, and a check
  or step that sets a credential variable never counts.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple

from pickfit.schema import COMMAND_MAX, PASSED_LEVELS, is_passed
from pickfit.verify.mcp import credentials, parse_summary, probe_kind

if TYPE_CHECKING:
    from pickfit.verify.agent import CommandRecord, FinishArgs

EXCERPT_CHARS = 300

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")

# Last command of a `;` list whose exit code says nothing about the command before it.
_TRIVIAL = {"echo", "printf", "true", ":", "exit", "ls", "cat", "pwd", "sleep", "wait", "date",
            "which", "type", "command", "hash", "set", "test", "["}
# Last command of a pipeline that hides the exit code of what feeds it (no pipefail).
_FILTERS = {"head", "tail", "grep", "egrep", "fgrep", "rg", "cat", "less", "more", "sed", "awk", "tee",
            "wc", "sort", "uniq", "cut", "tr", "column", "jq", "xargs", "true", "nl", "fold", "fmt"}
# Compound commands: their exit code is whatever branch ran last.
_CONTROL = {"if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done", "case", "esac"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Output that means the program crashed, whatever the exit code says.
_CRASH = re.compile(r"Traceback \(most recent call last\)|panicked at|Segmentation fault|"
                    r": command not found|No module named |Error: Cannot find module")
_VERSION_HELP = re.compile(r"(?:^|\s)(?:--version|-V|-v|--help|-h|version|help)\s*$")
# A file a command writes: curl/wget -o/-O/--output, or a shell redirect.
_WRITES = re.compile(r"(?:\s-o|\s-O|\s--output(?:-document)?|>>?)\s*=?\s*([~$/\w][^\s;&|'\"<>]*)")
_GENERATION = re.compile(r"/v1/(?:chat/)?completions|/api/(?:generate|chat)|/completion\b|/v1/responses")


# ---------------------------------------------------------------- exit-code masking


def _top_level(command: str) -> list[tuple[str, str]]:
    """Split a bash command at top-level operators: [(operator before, text), ...].

    Quotes, $(...), backticks, (...) subshells, comments and heredoc bodies are
    skipped, so only operators that bash itself sees at the top split the text.
    """
    parts: list[tuple[str, str]] = []
    op, start, depth, i, n = "", 0, 0, 0, len(command)
    heredocs: list[tuple[str, bool]] = []
    while i < n:
        ch = command[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "'":
            end = command.find("'", i + 1)
            i = n if end < 0 else end + 1
            continue
        if ch == '"':
            i += 1
            while i < n and command[i] != '"':
                i += 2 if command[i] == "\\" else 1
            i += 1
            continue
        if ch == "`":
            end = command.find("`", i + 1)
            i = n if end < 0 else end + 1
            continue
        if ch == "#" and (i == 0 or command[i - 1] in " \t\n;|&("):
            end = command.find("\n", i)
            i = n if end < 0 else end
            continue
        if command.startswith("<<", i) and not command.startswith("<<<", i):
            m = re.match(r"<<(-?)\s*(['\"]?)([A-Za-z0-9_.-]+)\2", command[i:])
            if m:
                heredocs.append((m.group(3), m.group(1) == "-"))
                i += m.end()
                continue
        if ch in "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            two = command[i:i + 2]
            found = None
            if two in ("||", "&&"):
                found = two
            elif ch == "|":
                found = "|"
            elif ch == ";":
                found = ";"
            elif ch == "&" and not (i and command[i - 1] in "<>") and command[i + 1:i + 2] != ">":
                found = "&"
            elif ch == "\n":
                found = "\n"
            if found:
                parts.append((op, command[start:i]))
                op = found
                i += len(found)
                if found == "\n" and heredocs:
                    i = _skip_heredocs(command, i, heredocs)
                    heredocs = []
                start = i
                continue
        i += 1
    parts.append((op, command[start:]))
    return [(o, t) for o, t in parts if t.strip() or o]


def _skip_heredocs(command: str, i: int, heredocs: list[tuple[str, bool]]) -> int:
    for delimiter, strip_tabs in heredocs:
        while i < len(command):
            end = command.find("\n", i)
            line = command[i:] if end < 0 else command[i:end]
            i = len(command) if end < 0 else end + 1
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                break
    return i


def _first_word(text: str) -> str:
    words = text.strip().lstrip("({").split()
    while words and (_ASSIGNMENT.match(words[0]) or words[0] in ("time", "env", "exec", "nohup")):
        words = words[1:]
    return words[0].rsplit("/", 1)[-1] if words else ""


def written_paths(command: str) -> set[str]:
    """Files a command writes with -o/-O/--output or a redirect (not /dev/* or &N)."""
    return {p for p in _WRITES.findall(command) if not p.startswith("/dev/") and not p[:1].isdigit()}


def names_path(command: str, path: str) -> bool:
    """Whether a command names `path` as a whole word, not as part of a longer name."""
    return re.search(rf"(?<![\w./~$-]){re.escape(path)}(?![\w./-])", command) is not None


def missing_input(check_id: int, setup_ids: list[int], available: set[int],
                  commands: list[CommandRecord]) -> str | None:
    """Why a check cannot run in a fresh box: it, or a setup it cites, uses a file only another command
    wrote, one the replay does not run before it (not an install step, a setup of a check, or its own
    setup). None when every file it names is there."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    for cid in [*setup_ids, check_id]:
        user = by_id.get(cid)
        if user is None:
            continue
        own = written_paths(user.command)
        for earlier in commands:
            if earlier.command_id is None or earlier.command_id >= cid or earlier.command_id in available \
                    or earlier.command_id in setup_ids or earlier.tool != "run_command":
                continue
            for path in sorted(written_paths(earlier.command) - own):
                if names_path(user.command, path) and not any(
                        path in written_paths(by_id[a].command) for a in (*available, *setup_ids)
                        if a in by_id and a < cid):
                    who = "it" if cid == check_id else f"its setup {cid}"
                    return (f"{who} uses {path}, which only command {earlier.command_id} wrote; cite a command "
                            f"that writes it (and exits 0) in setup_ids, or a fresh box will not have it")
    return None


_SCRIPT = re.compile(r"\.(?:sh|bash|zsh|js|mjs|cjs|ts|py|ps1|rb|pl)$")
_SHELLS = re.compile(r"(?:sh|bash|zsh|dash|ksh|node|deno|bun|python(?:3(?:\.\d+)?)?|ruby|perl|pwsh)")
_READERS = {"cat", "head", "tail", "less", "more", "nl", "sed", "awk", "bat", "view"}
_URL = re.compile(r"https?://[^\s'\"|)<>]+")
# A shell fed straight from the network: bash <(curl ...), sh -c "$(wget -O- ...)", source <(curl ...).
_SUBSTITUTED = re.compile(rf"^\s*(?:sudo\s+)?(?:{_SHELLS.pattern}|source|\.)\b[^|]*(?:<\(|\$\()\s*(?:curl|wget)\b"
                          r"(?P<fetch>[^)]*)\)")


class Unread(NamedTuple):
    step_id: int
    name: str  # the file, or the URL a shell ran straight from the network
    how: str  # "piped": run without being saved; "ran": run after saving; "brought in": run by another script
    via: str | None = None  # "brought in": the downloaded script that may run it


def _words(part: str) -> list[str]:
    """A simple command's words, without leading VAR=value, sudo, env or exec."""
    try:
        words = shlex.split(part, comments=False)
    except ValueError:
        words = part.split()
    while words and (re.match(r"^\w+=", words[0]) or words[0] in ("sudo", "env", "exec", "command")):
        words = words[1:]
    return words


def _base(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def _fetched(words: list[str]) -> list[str] | None:
    """For curl or wget: the files it saves ([] when it writes to stdout); None for any other program."""
    program = _base(words[0]) if words else ""
    if program not in ("curl", "wget"):
        return None
    urls = [w for w in words if _URL.match(w)]
    named: list[str] = []
    remote = program == "wget"  # wget saves under the URL's name unless -O says otherwise
    i = 1
    while i < len(words):
        word, value = words[i], words[i + 1] if i + 1 < len(words) else None
        letter = "o" if program == "curl" else "O"
        long = "--output" if program == "curl" else "--output-document"
        if word == long or (re.fullmatch(rf"-[a-zA-Z]*{letter}", word) and value is not None):
            named.append(value or "-")
            remote, i = False, i + 2
            continue
        if word.startswith(long + "="):
            named.append(word.split("=", 1)[1])
            remote = False
        elif m := re.fullmatch(rf"-[a-zA-Z]*{letter}(.+)", word):  # -o- or -ofile
            named.append(m.group(1))
            remote = False
        elif program == "curl" and (word in ("--remote-name", "--remote-name-all") or
                                    re.fullmatch(r"-[a-zA-Z]*O[a-zA-Z]*", word)):
            remote = True
        i += 1
    saved = named + ([_base(u.split("?", 1)[0]) for u in urls] if remote else [])
    return [s for s in saved if s and s != "-"]


def _ran(words: list[str], part: str) -> list[str]:
    """Files a simple command runs: an interpreter's script argument or stdin, source, or ./file."""
    if not words:
        return []
    program = words[0]
    if program in ("source", "."):
        return words[1:2]
    if "/" in program:
        return [program]
    if not _SHELLS.fullmatch(_base(program)):
        return []
    args = [w for w in words[1:] if not w.startswith("-")]
    stdin = re.search(r"(?<![<\d])<\s*([^\s<>&|;]+)", part)
    return args[:1] + ([stdin.group(1)] if stdin else [])


def unread_scripts(step_ids: list[int], commands: list[CommandRecord]) -> list[Unread]:
    """Downloaded scripts a cited step ran, or brought in, before anything read them.

    - piped: a shell ran a URL without saving it (curl ... | bash, bash <(curl ...), sh -c "$(curl ...)").
    - ran: a file curl or wget saved, run by an interpreter, source or ./file, with no read of it between
      its download and the step that ran it.
    - brought in: a script (by its extension) a cited step saved and no step ran directly, while a later
      cited step ran another downloaded script that may run it (an installer's helper), unread before then.
    A read is a successful read_file, or cat, head, tail, less, more, nl, sed, awk or bat taking the file.
    """
    cited = set(step_ids)
    saved: dict[str, list[tuple[tuple[int, int], int]]] = {}  # name -> [(position, cited step id or 0)]
    reads: dict[str, list[tuple[int, int]]] = {}
    runs: list[tuple[tuple[int, int], int, str]] = []
    found: list[Unread] = []
    for i, record in enumerate(commands):
        if record.tool == "read_file":
            if record.exit_code == 0 and not record.stderr:
                reads.setdefault(_base(record.command.split(" [", 1)[0]), []).append((i, 0))
            continue
        if record.tool != "run_command":
            continue
        step = record.command_id if record.command_id in cited else 0
        parts = [(op, text) for op, text in _top_level(record.command) if text.strip()]
        for j, (_, text) in enumerate(parts):
            words = _words(text)
            fetched = _fetched(words)
            if step and (m := _SUBSTITUTED.match(text)):
                url = _URL.search(m.group("fetch"))
                found.append(Unread(step, url.group(0) if url else "a downloaded script", "piped"))
            if fetched is not None:
                if step and not fetched and j + 1 < len(parts) and parts[j + 1][0] == "|" and \
                        _SHELLS.fullmatch(_base((_words(parts[j + 1][1]) or [""])[0])):
                    url = next((w for w in words if _URL.match(w)), "a downloaded script")
                    found.append(Unread(step, url, "piped"))
                for name in fetched:
                    saved.setdefault(_base(name), []).append(((i, j), step))
            elif words and _base(words[0]) in _READERS:
                for word in words[1:]:
                    reads.setdefault(_base(word), []).append((i, j))
            elif step:
                runs += [((i, j), step, _base(path)) for path in _ran(words, text)]

    def read_between(name: str, start: tuple[int, int], end: tuple[int, int]) -> bool:
        return any(start < at < end for at in reads.get(name, []))

    def last_save(name: str, before: tuple[int, int]) -> tuple[tuple[int, int], int] | None:
        return max((s for s in saved.get(name, []) if s[0] < before), default=None)

    ran_downloaded = []  # (position, step, name) of cited runs of a saved file
    for at, step, name in runs:
        save = last_save(name, at)
        if save is None:
            continue
        ran_downloaded.append((at, step, name))
        if not read_between(name, save[0], at) and all(u.name != name for u in found):
            found.append(Unread(step, name, "ran"))
    run_names = {name for _, _, name in runs}
    for name, saves in saved.items():
        for at, step in saves:
            if not step or not _SCRIPT.search(name) or name in run_names:
                continue
            installer = next(((r_at, r_step, r_name) for r_at, r_step, r_name in ran_downloaded
                              if r_at > at and r_name != name), None)
            if installer and not read_between(name, at, installer[0]) and all(u.name != name for u in found):
                found.append(Unread(installer[1], name, "brought in", installer[2]))
    return sorted(found, key=lambda u: (u.step_id, u.name))


# ---------------------------------------------------------------- copies the box changed


# A pass must install what a user would get: a published package, or the project's own source as a
# cited step fetched it. A directory no cited step fetched (a copy made by an uncited command) or a
# copy the box edited (sed -i, patch, a rewritten source file) is not that.
_INSTALLERS = (("uv", "tool", "install"), ("uv", "pip", "install"), ("pip", "install"), ("pip3", "install"),
               ("pipx", "install"), ("npm", "install"), ("npm", "i"), ("pnpm", "add"), ("pnpm", "install"),
               ("bun", "add"), ("bun", "install"), ("yarn", "global", "add"), ("cargo", "install"))
_PATH_OPTIONS = {"--path", "--from", "-e", "--editable"}
_VALUE_OPTIONS = {"-r", "--requirement", "-c", "--constraint", "-t", "--target", "--prefix", "--root", "--python",
                  "-p", "--index-url", "-i", "--extra-index-url", "--with", "--registry", "--cache", "--git",
                  "--branch", "--tag", "--rev", "--features", "--bin", "--version", "--cwd"}
_SOURCE_FILE = re.compile(r"\.(?:py|js|mjs|cjs|ts|tsx|go|rs|java|kt|rb|php|c|cc|cpp|h|hpp|cs|swift|lua)$")
_PACKAGE_DIRS = re.compile(r"node_modules/|site-packages/|dist-packages/|\.local/(?:lib|share/uv|share/pipx)/|"
                           r"\.cargo/registry/")
_PYTHON = re.compile(r"python(?:3(?:\.\d+)?)?")


def _installer_args(words: list[str]) -> list[str] | None:
    if len(words) > 2 and _PYTHON.fullmatch(_base(words[0])) and words[1:3] == ["-m", "pip"]:
        words = ["pip", *words[3:]]
    for prefix in _INSTALLERS:
        if tuple(words[:len(prefix)]) == prefix:
            return words[len(prefix):]
    return None


def _is_local(target: str) -> bool:
    if "://" in target:
        return target.startswith("file://")
    return target in (".", "..") or target.startswith(("/", "./", "../", "~/")) or \
        target.endswith((".whl", ".tgz", ".tar.gz", ".zip"))


def local_installs(part: str) -> list[str]:
    """The local paths a package-manager install in one simple command installs from."""
    args = _installer_args(_words(part))
    if args is None:
        return []
    targets: list[str] = []
    take = skip = False
    for word in args:
        if take or skip:
            if take:
                targets.append(word)
            take = skip = False
        elif word in _PATH_OPTIONS:
            take = True
        elif word in _VALUE_OPTIONS:
            skip = True
        elif "=" in word and word.split("=", 1)[0] in _PATH_OPTIONS:
            targets.append(word.split("=", 1)[1])
        elif not word.startswith("-"):
            targets.append(word)
    return [t for t in (re.sub(r"\[[^\]]*\]$", "", t) for t in targets) if _is_local(t)]  # ./pkg[extra]


def _project(repo_url: str | None) -> str | None:
    """owner/name of a GitHub project URL, lowercased."""
    m = re.search(r"github\.com[/:]([^/\s]+/[^/\s#?]+?)(?:\.git)?/?$", repo_url or "")
    return m.group(1).lower() if m else None


_CLONE_VALUE_OPTIONS = {"--depth", "-b", "--branch", "-o", "--origin", "--filter", "--reference", "-c", "--config",
                        "-j", "--jobs", "--shallow-since", "--shallow-exclude", "--separate-git-dir", "-u"}


def _positional(words: list[str], value_options: set[str]) -> list[str]:
    args: list[str] = []
    skip = False
    for word in words:
        if skip:
            skip = False
        elif word in value_options or re.fullmatch(r"\d*(?:>>?|<)", word):  # a value or a redirect's file
            skip = True
        elif not word.startswith("-") and not re.match(r"\d*[<>]", word):  # 2>&1, >log
            args.append(word)
    return args


RELEASE = "*release*"  # a download from the project: an archive whose unpacked directory name is unknown


def _fetched_names(parts: list[str], project: str | None) -> set[str]:
    """Directory and file names cited steps fetched from the project: clones, release and archive downloads."""
    names: set[str] = set()
    for part in parts:
        words = _words(part)
        if words[:2] == ["git", "clone"] or words[:3] == ["gh", "repo", "clone"]:
            args = _positional(words[3 if words[0] == "gh" else 2:], _CLONE_VALUE_OPTIONS)
            if args and (project is None or project in args[0].lower()):
                names.add(_base(args[1]) if len(args) > 1 else _base(args[0]).removesuffix(".git"))
        elif (saved := _fetched(words)) is not None:
            urls = [w for w in words if _URL.match(w) and (project is None or project in w.lower())]
            if urls:
                names.update([*map(_base, saved), *(_base(u.split("?", 1)[0]) for u in urls), RELEASE])
        elif words[:3] == ["gh", "release", "download"]:
            names.add(RELEASE)
    return names


def _within(path: str, names: set[str], project: str | None) -> bool:
    """True when a path lies in (or is) something a cited step fetched from the project."""
    stem = (project or "").split("/")[-1]
    for part in path.removeprefix("file://").split("/"):
        if part in ("", ".", "..", "~"):
            continue
        if part in names or (RELEASE in names and stem and part.lower().startswith(stem)):
            return True
    return False


def _edits(part: str) -> list[str]:
    """Files a simple command edits in place (sed -i, perl -i, patch, git apply); ["."] for the cwd's tree."""
    words = _words(part)
    if not words:
        return []
    program = _base(words[0])
    in_place = {"sed": r"-[a-zA-Z]*i\S*|--in-place\S*", "perl": r"-[a-zA-Z]*i\S*"}.get(program)
    if in_place and any(re.fullmatch(in_place, w) for w in words[1:]):
        rest = [w for w in words[1:] if not w.startswith("-")]
        return rest[1:] or ["."]
    if program == "patch" or words[:2] in (["git", "apply"], ["git", "am"], ["git", "cherry-pick"]):
        return ["."]
    return []


def modified_copy(step_commands: list[str], check_commands: list[str], repo_url: str | None) -> list[str]:
    """Why the install is not of what a user would get, or [] when it is.

    step_commands: the cited install steps, in order; check_commands: the checks and their setups.
    """
    project = _project(repo_url)
    names = _fetched_names([part for command in step_commands for _, part in _top_level(command)], project)
    problems: list[str] = []
    cwd_fetched = False
    for command in step_commands:
        for _, part in _top_level(command):
            words = _words(part)
            if words[:1] == ["cd"] and len(words) > 1:
                cwd_fetched = _within(words[1], names, project)
            elif words[:1] == ["cp"] and len(words) > 2:  # a plain copy of what was fetched counts as fetched
                *sources, dest = _positional(words[1:], set())
                if sources and all(_within(s, names, project) for s in sources):
                    if dest in (".", "./"):
                        cwd_fetched = True
                    else:
                        names.add(_base(dest))
            for target in local_installs(part):
                relative = not target.startswith(("/", "~", "file:"))
                if not (relative and cwd_fetched or _within(target, names, project)):
                    problems.append("installs from a local copy no cited step fetched from the project: "
                                    + _one_line(part))
    for command, is_step in [*((c, True) for c in step_commands), *((c, False) for c in check_commands)]:
        for _, part in _top_level(command):
            ours = [path for path in _edits(part)
                    if path == "." or _SOURCE_FILE.search(path) and is_step or _PACKAGE_DIRS.search(path)
                    or _within(path, names, project)]
            if is_step and _fetched(_words(part)) is None:  # a source file a step writes (not downloads)
                ours += [path for path in written_paths(part) if _SOURCE_FILE.search(path)
                         and (_PACKAGE_DIRS.search(path) or _within(path, names, project))]
            if ours:
                problems.append(f"changes the tool's own files ({_one_line(part)}): a patched copy is not "
                                "what a user would install")
    return list(dict.fromkeys(problems))


def masked_exit(command: str) -> str | None:
    """Why the recorded exit code of `command` may not be its real result, or None."""
    parts = _top_level(command)
    if parts and parts[-1][0] == "&" and not parts[-1][1].strip():
        return "a trailing `&` sends it to the background"
    parts = [p for p in parts if p[1].strip()]
    if any(op == "||" for op, _ in parts):
        return "`||` runs another command when the first fails"
    for _, text in parts:
        words = text.split()
        if words[:1] == ["exit"] and (len(words) == 1 or words[1] == "0"):
            return "`exit` sets the exit code itself"
        if words[:2] == ["set", "+e"]:
            return "`set +e` ignores failures"
        if text.strip().startswith("!"):
            return "`!` inverts the exit code"
        if _first_word(text) in _CONTROL:
            return f"`{_first_word(text)}` decides the exit code itself"
    if not parts:
        return None
    # The exit code is the last list's: everything after the last `;`, `&` or newline. Within that
    # list it is the last pipeline's last command, since `&&`/`||` yield their final command's code
    # (so `cat x && tool y` is tool y's result, not cat's).
    cut = max((k for k, (op, _) in enumerate(parts) if op in (";", "&", "\n")), default=0)
    tail = parts[cut:]
    start = max(k for k, (op, _) in enumerate(tail) if op != "|")
    pipeline = tail[start:]
    last = _first_word(pipeline[-1][1])
    if cut and last in _TRIVIAL:
        return f"the last command is `{last}`, so it hides the exit code before it"
    if len(pipeline) > 1 and last in _FILTERS:
        return f"piping into `{last}` hides the exit code of the command before it"
    return None


def last_command(command: str) -> str:
    parts = [text for _, text in _top_level(command) if text.strip()]
    return parts[-1] if parts else command


def split_last(command: str) -> tuple[str, str] | None:
    """(what runs first, the last command) when they are joined by `&&`, `;` or a newline.

    Running the first part and then the last as two commands does the same work;
    a pipe cannot be split this way, so it returns None.
    """
    parts = [(op, text) for op, text in _top_level(command) if text.strip()]
    if len(parts) < 2 or parts[-1][0] not in ("&&", ";", "\n"):
        return None
    last = parts[-1][1]
    stripped = command.rstrip()
    if not stripped.endswith(last.rstrip()):
        return None
    head = stripped[: len(stripped) - len(last.rstrip())].rstrip()
    for op in ("&&", ";"):
        if head.endswith(op):
            head = head[: -len(op)].rstrip()
    return (head, last.strip()) if head else None


# ---------------------------------------------------------------- verdict


def _plain(text: str) -> str:
    return " ".join(_ANSI.sub("", text).split()).lower()


def _excerpt(record: CommandRecord, signal: str) -> str:
    """The output line that carries the signal, else the last non-empty line."""
    lines = [ln for ln in _ANSI.sub("", f"{record.stdout}\n{record.stderr}").splitlines() if ln.strip()]
    if signal:
        key = _plain(signal)
        for line in lines:
            if key and key in _plain(line):
                return line.strip()[:EXCERPT_CHARS]
    return lines[-1].strip()[:EXCERPT_CHARS] if lines else ""


MCP_KINDS = ("mcp", "mcp_call")


def check_kind(command: str, tool: str = "run_command") -> str:
    """gui (a launch_gui), mcp or mcp_call (pickfit's MCP probe), version (--version/--help only), generation
    (asks a model for text), or example."""
    if tool == "launch_gui":
        return "gui"
    probe = probe_kind(last_command(command))
    if probe:
        return probe
    if _GENERATION.search(command):
        return "generation"
    if _VERSION_HELP.search(last_command(command)):
        return "version"
    return "example"


@dataclass
class ResolvedCheck:
    """One claimed smoke test, read back from the log."""

    command_id: int
    command: str
    tool: str
    setup_ids: list[int]
    expected_signal: str
    expected_exit_code: int
    exit_code: int | None
    passed: bool
    kind: str
    observed_excerpt: str = ""
    problems: list[str] = field(default_factory=list)


@dataclass
class LogVerdict:
    claimed_level: str
    level: str
    unverified_reason: str | None
    step_ids: list[int]
    checks: list[ResolvedCheck]
    problems: list[str]
    failing_id: int | None = None  # a failed claim: the command whose failure a fresh box must repeat

    @property
    def agrees(self) -> bool:
        return self.level == self.claimed_level and not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "agrees": self.agrees}


def evaluate_check(record: CommandRecord, expected_exit_code: int, expected_signal: str, *,
                   trusted_only: bool = False) -> tuple[bool, list[str]]:
    """Whether one recorded command shows a passing check; the reasons when not.

    trusted_only (a GUI launch): the signal must be in stdout, pickfit's own lines; stderr is the app's output.
    """
    problems: list[str] = []
    masked = masked_exit(record.command)
    if masked:
        problems.append(f"exit code masked ({masked})")
    if record.timed_out:
        problems.append("timed out")
    if record.exit_code != expected_exit_code:
        problems.append(f"expected exit {expected_exit_code}, log shows {record.exit_code}")
    output = _plain(f"{record.stdout}\n{record.stderr}")
    if not output:
        problems.append("no output to show it worked")
    signal = _plain(expected_signal)
    if expected_exit_code != 0 and not signal:
        problems.append("a non-zero expected exit needs an expected_signal")
    if signal and signal not in (_plain(record.stdout) if trusted_only else output):
        where = "pickfit's own lines about the launch" if trusted_only else "the output"
        problems.append(f"expected_signal not in {where}: {expected_signal[:80]!r}")
    crash = _CRASH.search(_ANSI.sub("", f"{record.stdout}\n{record.stderr}"))
    if crash:
        problems.append(f"output shows a crash: {crash.group(0)!r}")
    return not problems, problems


def mcp_problems(kind: str, stdout: str) -> list[str]:
    """Why a probe check's output does not show what its kind claims; [] when it does."""
    summary = parse_summary(stdout)
    if summary is None:
        return ["no summary line from pickfit's MCP probe in the output"]
    if not summary.get("ok"):
        return [f"the MCP probe did not complete: {str(summary.get('error') or 'not ok')[:120]}"]
    if kind == "mcp_call" and not summary.get("called"):
        return ["the MCP probe's tool call did not return a result"]
    return []


def supported_level(steps_ok: bool, checks: list[ResolvedCheck], has_service: bool, *,
                    mcp: bool = False) -> str | None:
    """The strongest passed level the passing checks support, or None.

    An MCP server passes only on pickfit's probe: function for the handshake, service for a tool call.
    """
    passing = [c for c in checks if c.passed]
    if not steps_ok or not passing:
        return None
    if mcp:
        kinds = {c.kind for c in passing}
        return "service" if "mcp_call" in kinds else "function" if "mcp" in kinds else None
    if any(c.kind == "generation" for c in passing) and has_service:
        return "inference"
    if has_service and any(c.kind not in ("version", "gui") for c in passing):
        return "service"
    if any(c.kind not in ("version", "gui") for c in passing):
        return "function"
    return "install"


def weaker(a: str, b: str) -> str:
    return a if PASSED_LEVELS.index(a) > PASSED_LEVELS.index(b) else b


def log_verdict(finish: FinishArgs, commands: list[CommandRecord], *, mcp: bool = False,
                repo_url: str | None = None) -> LogVerdict:
    """Decide the level from the command log; the claim is only an upper bound.

    mcp: the software is an MCP server, so only pickfit's probe can make it pass.
    repo_url: the project, so an install from a local copy can be told apart from one of its own source.
    """
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    problems: list[str] = []

    steps_ok = bool(finish.steps)
    step_ids: list[int] = []
    for step in finish.steps:
        record = by_id.get(step.command_id)
        if record is None or record.tool != "run_command":
            steps_ok = False
            problems.append(f"step cites no run_command with id {step.command_id}")
            continue
        step_ids.append(step.command_id)
        masked = masked_exit(record.command)
        if record.exit_code != 0 or record.timed_out or masked:
            steps_ok = False
            why = masked or ("timed out" if record.timed_out else f"exit {record.exit_code}")
            problems.append(f"step {step.command_id} does not show a success ({why}): "
                            f"{_one_line(record.command)}")
        elif len(record.command) > COMMAND_MAX:
            steps_ok = False
            problems.append(f"step {step.command_id} is {len(record.command)} characters; an install step "
                            f"must fit in {COMMAND_MAX} (split it into shorter commands)")
        elif mcp and credentials(record.command):
            steps_ok = False
            problems.append(f"step {step.command_id} sets {', '.join(credentials(record.command))}: pickfit "
                            "never uses placeholder credentials")

    # A step that runs a file only an uncited command wrote cannot be replayed (a fresh box lacks it).
    cited = set(step_ids)
    for sid in step_ids:
        step = by_id[sid]
        own = written_paths(step.command)
        for earlier in commands:
            if earlier.command_id is None or earlier.command_id >= sid or earlier.command_id in cited:
                continue
            missing = sorted(p for p in written_paths(earlier.command) - own if p in step.command
                             and not any(p in written_paths(by_id[c].command) for c in cited if c < sid))
            if missing and earlier.exit_code == 0:
                steps_ok = False
                problems.append(f"step {sid} uses {missing[0]}, which only command {earlier.command_id} wrote; "
                                f"cite {earlier.command_id} as a step too, or the replay will not have it")
                break

    check_commands = [by_id[cid].command for test in finish.smoke_tests
                      for cid in (test.command_id, *test.setup_ids) if cid in by_id]
    copied = modified_copy([by_id[sid].command for sid in step_ids], check_commands, repo_url)
    if copied:
        steps_ok = False
        problems += copied

    checks: list[ResolvedCheck] = []
    has_service = False
    # Before a check, a fresh box runs every install step and the setups of every check.
    available = {*step_ids, *(s for t in finish.smoke_tests for s in t.setup_ids)}
    for test in finish.smoke_tests:
        record = by_id.get(test.command_id)
        if record is None:
            problems.append(f"smoke test cites no command with id {test.command_id}")
            continue
        check = ResolvedCheck(
            command_id=test.command_id, command=record.command, tool=record.tool,
            setup_ids=list(test.setup_ids), expected_signal=test.expected_signal.strip(),
            expected_exit_code=test.expected_exit_code, exit_code=record.exit_code, passed=False,
            kind=check_kind(record.command, record.tool))
        setup_ok = True
        for setup_id in test.setup_ids:
            if setup_id in step_ids:  # an install step: the replay runs every step first anyway
                continue
            setup = by_id.get(setup_id)
            if setup is None or setup_id >= test.command_id:
                setup_ok = False
                check.problems.append(f"setup {setup_id} is not a command that ran before it")
            elif setup.exit_code != 0 or setup.timed_out:
                setup_ok = False
                check.problems.append(f"setup {setup_id} exited {setup.exit_code}")
        missing = missing_input(test.command_id, list(test.setup_ids), available, commands)
        if missing:
            setup_ok = False
            check.problems.append(missing)
        ok, why = evaluate_check(record, check.expected_exit_code, check.expected_signal,
                                 trusted_only=check.kind == "gui")
        if check.kind in MCP_KINDS:
            why += mcp_problems(check.kind, record.stdout)
        if mcp:
            fake = sorted({name for cid in (test.command_id, *test.setup_ids) if cid in by_id
                           for name in credentials(by_id[cid].command)})
            if fake:
                why.append(f"sets {', '.join(fake)}: pickfit never uses placeholder credentials")
        ok = ok and not why
        check.problems += why
        check.passed = ok and setup_ok
        check.observed_excerpt = _excerpt(record, check.expected_signal)
        serves = record.tool == "run_background" or any(
            by_id[s].tool == "run_background" for s in test.setup_ids if s in by_id)
        if check.passed and serves:
            has_service = True
        problems += [f"smoke test {test.command_id}: {p}" for p in check.problems]
        checks.append(check)

    level, reason = finish.level, finish.unverified_reason
    if is_passed(level):
        supported = supported_level(steps_ok, checks, has_service, mcp=mcp)
        if supported is None:
            level, reason = "unverified", "other"
            if mcp and steps_ok and any(c.passed for c in checks):
                problems.append("an MCP server passes only when pickfit's probe completes the handshake")
            if not problems:
                problems.append("no passing check in the log")
        else:
            level = weaker(level, supported)
    failing_id = _failing_id(finish, checks, by_id, problems) if level == "failed" else None
    if level == "failed" and failing_id is None:  # nothing a fresh box could fail again
        level, reason = "unverified", "other"
    return LogVerdict(claimed_level=finish.level, level=level, unverified_reason=reason,
                      step_ids=step_ids, checks=checks, problems=problems, failing_id=failing_id)


def _failing_id(finish: FinishArgs, checks: list[ResolvedCheck], by_id: dict[int, CommandRecord],
                problems: list[str]) -> int | None:
    """The failed claim's failing command: the one cited, else the first cited check that failed with a
    non-zero exit (the most basic one: a --help that crashes comes before an example that fails). A check
    that passed with the non-zero exit it expected (a linter finding problems) is not a failure."""
    passed = {c.command_id for c in checks if c.passed}
    cid = finish.failing_command_id
    if cid is None:
        failed = [c.command_id for c in checks if c.command_id not in passed
                  and by_id[c.command_id].tool == "run_command"
                  and (by_id[c.command_id].exit_code not in (0, None) or by_id[c.command_id].timed_out)]
        cid = failed[0] if failed else None
    record = by_id.get(cid) if cid is not None else None
    if record is None or record.tool != "run_command":
        problems.append("failing_command_id cites no run_command" if cid is not None else
                        "a failed claim needs failing_command_id: the command that failed")
        return None
    if record.exit_code == 0 and not record.timed_out:
        problems.append(f"failing command {cid} exited 0")
        return None
    if cid in passed:
        problems.append(f"failing command {cid} is a check that passed (exit {record.exit_code} was expected)")
        return None
    return cid


def _one_line(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
