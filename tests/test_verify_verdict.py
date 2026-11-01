"""The verdict comes from the command log: masked exit codes, cited ids, supported levels."""

from __future__ import annotations

from typing import Any

import pytest

from pickfit.verify.agent import CommandRecord, FinishArgs
from pickfit.verify.verdict import (
    check_kind,
    install_command,
    local_installs,
    log_verdict,
    masked_exit,
    modified_copy,
    split_last,
    unmasked,
    unread_scripts,
    written_paths,
)


@pytest.mark.parametrize("command", [
    "pipx install evnx",
    "evnx sync && evnx validate",
    "echo '{\"a\": 1}' | tinyq .a",
    "cd sub; graphtty graph.json",
    "graphtty graph.json 2>&1",
    "llama-server -m m.gguf &> server.log && curl -s localhost:8080/health",
    "echo 'a || b; echo $?' > notes.txt && cat notes.txt | wc -l > n && tool n",
    "cat > graph.json <<'EOF'\n{\"nodes\": [\"a\"]; \"x\": 1 || 2}\nEOF\ngraphtty graph.json",
    "python3 -c 'import sys; sys.exit(0)' && tool --help",
    "tool --format=\"a|b\" input.txt",
    # A `&&`/`||` chain after a separator: the result is the chain's final command, not its first
    # (the bug that dropped shep's `shep start` step and left its `shep flock` check unrun).
    "echo hi\ncat /tmp/x && false",
    "printf go; cat /tmp/Flockfile.toml && shep start /tmp/Flockfile.toml",
    "ls; make && echo keep | cat && tool run",
])
def test_honest_commands_are_not_masked(command: str):
    assert masked_exit(command) is None


@pytest.mark.parametrize(("command", "why"), [
    ("pipx install evnx || true", "`||`"),
    ("evnx validate; echo $?", "`echo`"),
    ("evnx validate; echo exit=$?", "`echo`"),
    ("tool --help | head -20", "`head`"),
    ("pip install x 2>&1 | tail -5", "`tail`"),
    ("tool --version | grep 1.2", "`grep`"),
    ("tool run &", "background"),
    ("tool check\nexit 0", "`exit`"),
    ("if tool --version; then echo ok; fi", "`if`"),
    ("! tool --broken", "`!`"),
    ("set +e; tool x", "`set +e`"),
    ("tool x || :", "`||`"),
    ("cat > in.txt <<EOF\nhello\nEOF\ntool in.txt; true", "`true`"),
])
def test_masked_exit_codes_are_caught(command: str, why: str):
    reason = masked_exit(command)
    assert reason is not None and why in reason


@pytest.mark.parametrize(("command", "clean", "dropped"), [
    ("uv tool install agent-lsp 2>&1 | tail -30", "uv tool install agent-lsp 2>&1", "| tail -30"),
    ("tool --help | head -n 20", "tool --help", "| head -n 20"),
    ("curl -s localhost:8000/api 2>&1 | head -c 2000", "curl -s localhost:8000/api 2>&1", "| head -c 2000"),
    ("tool --help 2>&1; echo \"EXIT:$?\"", "tool --help 2>&1", "; echo \"EXIT:$?\""),
    ("pip install x 2>&1 | tail -5; echo exit=$?", "pip install x 2>&1", "| tail -5; echo exit=$?"),
    ("git clone u /tmp/y && ls /tmp/y | head -n 20", "git clone u /tmp/y && ls /tmp/y", "| head -n 20"),
    ("cat > in.txt <<'EOF'\nhi; echo no\nEOF\necho ok", "cat > in.txt <<'EOF'\nhi; echo no\nEOF", "echo ok"),
    ("tool x;\necho ok", "tool x", ";\necho ok"),
])
def test_a_trailing_tail_head_or_echo_is_dropped(command: str, clean: str, dropped: str):
    assert unmasked(command) == (clean, dropped)
    assert masked_exit(clean) is None


@pytest.mark.parametrize("command", [
    "pipx install evnx",
    "tool --version | grep 1.2",
    "pipx install evnx || true",
    "tool x || :",
    "set +e; tool x | tail -2",
    "! tool x | tail -2",
    "pipx install evnx; cat README.md | head -5",  # still masked by `cat` without the head
    "yes | head -5",  # head is what ends these
    "tail -f server.log | head -5",
    "tool x | tail -f",
    "tool x | head -5 > out.txt",
    "tool x; echo done > marker",
    "tool x; echo \"$(tool --version)\"",
    "tool run &",
])
def test_other_masks_are_left_for_the_log_rules(command: str):
    assert unmasked(command) is None


@pytest.mark.parametrize(("command", "tidy"), [
    ("curl -fsSL https://bun.sh/install | bash 2>&1 | tail -20; ls ~/.bun/bin/bun; ~/.bun/bin/bun --version",
     "curl -fsSL https://bun.sh/install | bash 2>&1; ~/.bun/bin/bun --version"),
    ("git clone u x && ls x | head -n 50 && du -sh x", "git clone u x"),
    ("curl -L -o /tmp/a.tar.xz u && tar -tf /tmp/a.tar.xz | head -n 20 && mkdir -p /tmp/e && "
     "tar -xf /tmp/a.tar.xz -C /tmp/e && ls -R /tmp/e",
     "curl -L -o /tmp/a.tar.xz u && mkdir -p /tmp/e && tar -xf /tmp/a.tar.xz -C /tmp/e"),
    ("curl -fsSL u -o /tmp/i.sh && ls -l /tmp/i.sh && head -c 2000 /tmp/i.sh; echo \"---\"; wc -c /tmp/i.sh",
     "curl -fsSL u -o /tmp/i.sh"),
    ("openssl version; echo \"---\"; sh /tmp/install.sh", "sh /tmp/install.sh"),
    ("bash /tmp/b.sh 2>&1 | tail -10; export PATH=\"$HOME/.bun/bin:$PATH\" && bun --version",
     "bash /tmp/b.sh 2>&1; export PATH=\"$HOME/.bun/bin:$PATH\" && bun --version"),
    # The weaker joint stays, so what ran whatever came before still does.
    ("a && ls; b", "a; b"),
    ("a; ls && b", "a; b"),
    ("rm x\nls -l ~/.local/bin/\nsh install.sh 2>&1\necho DONE:$?\nx --version", "rm x\nsh install.sh 2>&1\nx --version"),
    ("cat > ~/bin/t <<'EOS'\n#!/bin/sh\nls; echo hi\nEOS\nchmod +x ~/bin/t\n~/bin/t --version\necho EXIT:$?\n~/bin/t --help",
     "cat > ~/bin/t <<'EOS'\n#!/bin/sh\nls; echo hi\nEOS\nchmod +x ~/bin/t\n~/bin/t --help"),
    ("find /tmp -maxdepth 3 -name 'x*'; pwd; tar -xzf /tmp/x.tgz -C /tmp", "tar -xzf /tmp/x.tgz -C /tmp"),
    ("curl -L --fail -o /tmp/k.zip u && unzip -l /tmp/k.zip && unzip -q -o /tmp/k.zip -d /tmp",
     "curl -L --fail -o /tmp/k.zip u && unzip -q -o /tmp/k.zip -d /tmp"),
    # A sum printed to look at goes; a sum checked (`-c`) stays.
    ("curl -fLO u/x.tgz && curl -fLO u/SUMS && cat SUMS && sha256sum x.tgz && tar -xzf x.tgz",
     "curl -fLO u/x.tgz && curl -fLO u/SUMS && tar -xzf x.tgz"),
    ("cd /tmp/d && cat x.tgz.sha256 && sha256sum -c x.tgz.sha256 && tar -tzf x.tgz", "cd /tmp/d && sha256sum -c x.tgz.sha256"),
])
def test_an_install_step_loses_its_looking_around(command: str, tidy: str):
    assert install_command(command) == tidy


@pytest.mark.parametrize("command", [
    "pipx install evnx",
    "cd repo && make install",
    "VERSION=1.2 && curl -fLo x https://e.x/$VERSION/x",
    "pip install x || true",  # `||` is left as it is
    "tool serve &",
    "ls -la",  # only looking: nothing would be left
    "tool --version",  # the step's own check
    "echo 'export PATH=$HOME/.bun/bin:$PATH' >> ~/.bashrc && source ~/.bashrc",
    "find . -name '*.pyc' -delete && pip install .",
    "cat install.sh | sh",
    "x=$(ls dist) && pip install dist/$x",
    "yes | head -5 && tool init",
    "cat > f <<'EOF' && ls\nbody\nEOF\ntool f",  # the heredoc body follows `ls`: never dropped with it
    "chmod +x ~/bin/lox && curl -fsSL u.sha256 | cat && sha256sum ~/bin/lox",  # `| cat` would be last
    "curl -fLO u/x.tgz && echo \"abc  x.tgz\" | sha256sum -c && tar -xzf x.tgz",
    "curl -fLO u/r && curl -fLO u/SUMS && sha256sum -c --ignore-missing SUMS 2>&1",
])
def test_an_install_step_that_only_installs_is_left_alone(command: str):
    assert install_command(command) == command


def test_check_kind():
    assert check_kind("evnx --version") == "version"
    assert check_kind("pipx install x && x --help") == "version"
    assert check_kind("graphtty graph.json") == "example"
    assert check_kind("curl -s localhost:8080/v1/completions -d '{}'") == "generation"
    assert check_kind("curl -s http://127.0.0.1:11434/api/generate -d @req.json") == "generation"


# ---------------------------------------------------------------- log_verdict


def rec(cid: int, command: str, code: int, out: str = "", err: str = "", tool: str = "run_command",
        timed_out: bool = False) -> CommandRecord:
    return CommandRecord(turn=cid, tool=tool, command=command, exit_code=code, seconds=0.1, stdout=out,
                         stderr=err, timed_out=timed_out, command_id=cid)


def claim(level: str, steps: list[int], tests: list[dict[str, Any]], **extra: Any) -> FinishArgs:
    return FinishArgs.model_validate({
        "level": level, "steps": [{"command_id": s, "purpose": "install"} for s in steps],
        "smoke_tests": [{"setup_ids": [], "expected_signal": "", "expected_exit_code": 0,
                         "observed_excerpt": "", **t} for t in tests], **extra})


LOG = [
    rec(1, "pipx install evnx", 0, "installed package evnx 0.10.18"),
    rec(2, "evnx --version", 0, "evnx 0.10.18"),
    rec(3, "evnx validate", 2, "", "Error: .env.example does not exist."),
    rec(4, "evnx sync", 0, "wrote .env.example"),
    rec(5, "evnx validate", 1, "SECRET_KEY looks like a placeholder"),
]


def test_function_needs_a_readme_example_from_the_log():
    verdict = log_verdict(claim("function", [1], [
        {"command_id": 2, "expected_signal": "0.10.18"},
        {"command_id": 5, "setup_ids": [4], "expected_signal": "SECRET_KEY", "expected_exit_code": 1}]), LOG)
    assert verdict.level == "function" and verdict.agrees
    assert [c.passed for c in verdict.checks] == [True, True]
    assert [c.kind for c in verdict.checks] == ["version", "example"]
    assert verdict.checks[1].observed_excerpt == "SECRET_KEY looks like a placeholder"


def test_claimed_exit_code_is_checked_against_the_log():
    # The model says the failing validate (exit 2) was the passing example.
    verdict = log_verdict(claim("function", [1], [
        {"command_id": 2, "expected_signal": "0.10.18"},
        {"command_id": 3, "expected_signal": "Error", "expected_exit_code": 1}]), LOG)
    assert verdict.level == "install"
    assert "smoke test 3: expected exit 1, log shows 2" in verdict.problems


def test_a_version_check_alone_supports_install():
    verdict = log_verdict(claim("function", [1], [{"command_id": 2, "expected_signal": "0.10.18"}]), LOG)
    assert verdict.level == "install" and not verdict.agrees and verdict.problems == []


def test_masked_step_or_check_is_not_counted():
    log = [rec(1, "pipx install nothere || true", 0, "No matching distribution"),
           rec(2, "nothere --help | head -5", 0, "usage: nothere")]
    verdict = log_verdict(claim("function", [1], [{"command_id": 2, "expected_signal": "usage"}]), log)
    assert verdict.level == "unverified" and verdict.unverified_reason == "other"
    assert any("step 1 does not show a success (`||`" in p for p in verdict.problems)
    assert any("exit code masked" in p for p in verdict.problems)


def test_signal_must_be_in_the_output_and_crashes_fail():
    log = [rec(1, "uv tool install x", 0, "Installed 1 executable: x"),
           rec(2, "x demo.txt", 0, "Traceback (most recent call last):\n  ...\nKeyError: 'a'"),
           rec(3, "x --version", 0, "x 1.0")]
    verdict = log_verdict(claim("function", [1], [{"command_id": 2, "expected_signal": "rendered"},
                                                  {"command_id": 3, "expected_signal": "1.0"}]), log)
    problems = verdict.checks[0].problems
    assert "expected_signal not in the output: 'rendered'" in problems
    assert any("crash" in p for p in problems)
    assert verdict.level == "install"


def test_non_zero_exit_needs_a_signal_and_setup_must_come_first():
    verdict = log_verdict(claim("function", [1], [
        {"command_id": 5, "setup_ids": [4], "expected_exit_code": 1},
        {"command_id": 2, "setup_ids": [5], "expected_signal": "0.10.18"}]), LOG)
    assert "a non-zero expected exit needs an expected_signal" in verdict.checks[0].problems
    assert "setup 5 is not a command that ran before it" in verdict.checks[1].problems
    assert verdict.level == "unverified"


def test_unknown_ids_and_no_checks():
    verdict = log_verdict(claim("install", [9], [{"command_id": 8}]), LOG)
    assert verdict.level == "unverified"
    assert verdict.problems == ["step cites no run_command with id 9", "smoke test cites no command with id 8"]
    verdict = log_verdict(claim("install", [1], []), LOG)
    assert verdict.level == "unverified" and verdict.problems == ["no passing check in the log"]


def test_service_and_inference_need_a_background_server():
    log = [rec(1, "curl -L -o llama.tgz https://example.invalid/llama.tgz && tar xzf llama.tgz", 0, ""),
           rec(2, "./llama-server -m m.gguf --port 8080", 0, "pid 7\nport 8080 open after 2s",
               tool="run_background"),
           rec(3, "curl -s localhost:8080/health", 0, '{"status":"ok"}'),
           rec(4, "curl -s localhost:8080/v1/completions -d '{\"prompt\":\"Hi\"}'", 0,
               '{"choices":[{"text":" there"}],"usage":{"completion_tokens":4}}')]
    tests = [{"command_id": 3, "setup_ids": [2], "expected_signal": '"status":"ok"'},
             {"command_id": 4, "setup_ids": [2], "expected_signal": "completion_tokens"}]
    assert log_verdict(claim("inference", [1], tests), log).level == "inference"
    assert log_verdict(claim("inference", [1], tests[:1]), log).level == "service"
    # Without the server as setup, a curl is only an example.
    alone = [{**t, "setup_ids": []} for t in tests]
    assert log_verdict(claim("inference", [1], alone), log).level == "function"


def test_failed_and_unverified_claims_stand():
    verdict = log_verdict(claim("failed", [1], [], blocking_error="validate breaks", failing_command_id=3), LOG)
    assert verdict.level == "failed" and verdict.agrees and verdict.failing_id == 3
    verdict = log_verdict(claim("unverified", [], [], unverified_reason="needs_gpu"), LOG)
    assert (verdict.level, verdict.unverified_reason) == ("unverified", "needs_gpu")


def test_a_failed_claim_needs_a_command_that_failed():
    # No failing command cited: the first cited check that failed with a non-zero exit stands in for it.
    # Check 3 exited 2 as it expected (it passed), so it is not the failure.
    verdict = log_verdict(claim("failed", [1], [{"command_id": 2, "expected_signal": "0.10.18"},
                                                {"command_id": 3, "expected_signal": "Error", "expected_exit_code": 2},
                                                {"command_id": 5, "expected_signal": "ok"}],
                                blocking_error="validate rejects the example"), LOG)
    assert (verdict.level, verdict.failing_id) == ("failed", 5)
    # Citing that passing check as the failing command is refused too.
    verdict = log_verdict(claim("failed", [1], [{"command_id": 3, "expected_signal": "Error", "expected_exit_code": 2}],
                                blocking_error="validate rejects the example", failing_command_id=3), LOG)
    assert verdict.level == "unverified"
    assert "failing command 3 is a check that passed (exit 2 was expected)" in verdict.problems
    # Nothing failed, or the cited command exited 0: nothing a fresh box could repeat.
    verdict = log_verdict(claim("failed", [], [], blocking_error="no wheel"), LOG)
    assert (verdict.level, verdict.unverified_reason, verdict.failing_id) == ("unverified", "other", None)
    assert verdict.problems == ["a failed claim needs failing_command_id: the command that failed"]
    verdict = log_verdict(claim("failed", [1], [], blocking_error="x", failing_command_id=2), LOG)
    assert verdict.level == "unverified" and verdict.problems == ["failing command 2 exited 0"]


def test_long_steps_and_steps_cited_as_setup():
    long_step = "curl -L -o t.tgz https://example.invalid/" + "x" * 480 + " && tar xzf t.tgz"
    log = [rec(1, long_step, 0), rec(2, "tool --version", 0, "tool 1.0"),
           rec(3, "rm -rf src && git clone https://example.invalid/src", 0, "Cloning")]
    verdict = log_verdict(claim("install", [1], [{"command_id": 2, "expected_signal": "1.0"}]), log)
    assert verdict.level == "unverified"
    assert verdict.problems[0].startswith(f"step 1 is {len(long_step)} characters; an install step must fit in 500")
    # A clean re-clone after the checks is an install step, not a setup that "ran after" them.
    verdict = log_verdict(claim("install", [3], [{"command_id": 2, "setup_ids": [3], "expected_signal": "1.0"}]),
                          log)
    assert verdict.level == "install" and verdict.problems == []


def test_split_last_separates_what_runs_first():
    heredoc = "cat > g.json <<'EOF'\n{\"a\": 1; \"b\": 2 && 3}\nEOF"
    assert split_last(f"{heredoc}\ngraphtty g.json") == (heredoc, "graphtty g.json")
    assert split_last("evnx sync && evnx validate") == ("evnx sync", "evnx validate")
    assert split_last("cd sub; tool run") == ("cd sub", "tool run")
    assert split_last("echo '{}' | tinyq .a") is None  # a pipe cannot be split
    assert split_last("tool --version") is None


def test_a_step_that_runs_a_file_only_an_uncited_command_wrote():
    assert written_paths("curl -fsSL https://x.dev/i.sh -o /tmp/i.sh && head /tmp/i.sh") == {"/tmp/i.sh"}
    assert written_paths("echo hi > notes.txt 2>&1 >/dev/null") == {"notes.txt"}
    log = [rec(1, "curl -fsSL https://x.dev/i.sh -o /tmp/i.sh && head -40 /tmp/i.sh", 0, "#!/bin/sh"),
           rec(2, "sh /tmp/i.sh", 0, "installed rimz"),
           rec(3, "rimz --version", 0, "rimz 0.4.3")]
    verdict = log_verdict(claim("install", [2], [{"command_id": 3, "expected_signal": "0.4.3"}]), log)
    assert verdict.level == "unverified"
    assert verdict.problems == ["step 2 uses /tmp/i.sh, which only command 1 wrote; cite 1 as a step too, "
                                "or the replay will not have it"]
    # Citing the download (even with its head) fixes it.
    assert log_verdict(claim("install", [1, 2], [{"command_id": 3, "expected_signal": "0.4.3"}]),
                       log).level == "install"


def read(path: str, ok: bool = True) -> CommandRecord:
    return CommandRecord(turn=0, tool="read_file", command=f"{path} [0-4000]", exit_code=0 if ok else None,
                         seconds=0.0, stderr="" if ok else "No such file or directory")


def unread(log: list[CommandRecord], steps: list[int] | None = None) -> list[tuple]:
    cited = steps if steps is not None else [r.command_id for r in log if r.command_id is not None]
    return [tuple(u) for u in unread_scripts(cited, log)]


MI_LSP = [rec(1, "curl -fsSL https://x.dev/install.sh -o install.sh", 0),
          rec(2, "curl -fsSL https://x.dev/validate-worker-manifest.js -o validate-worker-manifest.js", 0),
          read("install.sh"), rec(3, "bash install.sh --skip-worker-install", 0)]


def test_a_helper_the_installer_runs_must_be_read_before_the_installer():
    assert unread(MI_LSP) == [(3, "validate-worker-manifest.js", "brought in", "install.sh")]
    assert unread([*MI_LSP[:3], read("validate-worker-manifest.js"), MI_LSP[3]]) == []
    # Read only after the installer ran (before a later PATH step) is too late.
    late = [*MI_LSP, read("validate-worker-manifest.js"), rec(4, "ln -sf ~/.mi/bin/mi-lsp ~/.local/bin/mi-lsp", 0)]
    assert unread(late) == [(3, "validate-worker-manifest.js", "brought in", "install.sh")]
    # A downloaded script no downloaded script could run (a linter's sample input) is no helper.
    sample = [rec(1, "curl -fsSLo example.py https://x.dev/example.py", 0), rec(2, "ruff check example.py", 1)]
    assert unread(sample) == []


@pytest.mark.parametrize("command", [
    "curl -fsSL https://x.dev/install.sh | bash",
    "curl -o- https://x.dev/install.sh | bash -s -- --yes",
    "wget -qO- https://x.dev/install.sh | sh",
    "bash <(curl -fsSL https://x.dev/install.sh)",
    'sh -c "$(curl -fsSL https://x.dev/install.sh)"',
])
def test_a_script_run_straight_from_the_network_is_always_noted(command: str):
    assert unread([rec(1, command, 0)]) == [(1, "https://x.dev/install.sh", "piped", None)]


@pytest.mark.parametrize("fetch", [
    "curl -fsSLo install.sh https://x.dev/install.sh",
    "curl -LO https://x.dev/install.sh",
    "curl -o \"install.sh\" https://x.dev/install.sh",
    "curl --output=install.sh https://x.dev/install.sh",
    "wget -qO install.sh https://x.dev/install.sh",
    "wget https://x.dev/install.sh?ref=main",
])
def test_download_spellings(fetch: str):
    assert unread([rec(1, f"{fetch} && bash install.sh", 0)]) == [(1, "install.sh", "ran", None)]


def test_what_counts_as_reading_a_script_before_it_runs():
    fetch, run = rec(1, "curl -fsSL https://x.dev/i.sh -o /tmp/i.sh", 0), rec(3, "sh /tmp/i.sh", 0)
    for reading in ("head -40 /tmp/i.sh", "sed -ne '1,200p' /tmp/i.sh", "awk 'NR<=200' /tmp/i.sh"):
        assert unread([fetch, rec(2, reading, 0), run], [1, 3]) == []
    assert unread([rec(1, "curl -fsSL https://x.dev/i.sh -o i.sh && cat i.sh", 0), rec(3, "sh i.sh", 0)]) == []
    # Running it with its output cut by tail, a read after it ran, a failed read_file, or one before the
    # download: not a read.
    not_reads = [
        [fetch, rec(2, "bash /tmp/i.sh 2>&1 | tail -40", 1), run],
        [fetch, run, rec(4, "cat /tmp/i.sh", 0)],
        [fetch, read("/tmp/i.sh", ok=False), run],
        [read("i.sh"), fetch, run],
    ]
    for log in not_reads:
        assert unread(log, [1, 3]) == [(3, "i.sh", "ran", None)], log


def test_how_a_downloaded_file_is_run():
    assert unread([rec(1, "curl -fsSL -o install https://x.dev/install && chmod +x install && ./install", 0)]) == [
        (1, "install", "ran", None)]
    assert unread([rec(1, "curl -fsSL -o get.py https://x.dev/get.py", 0), rec(2, "python3 - < get.py", 0)]) == [
        (2, "get.py", "ran", None)]
    assert unread([rec(1, "curl -fsSLO https://x.dev/env.sh", 0), rec(2, "source env.sh && tool --version", 0)]) == [
        (2, "env.sh", "ran", None)]


def test_files_that_are_not_downloaded_scripts():
    # Written by the agent itself, a release tarball and its binary, an uncited run.
    assert unread([rec(1, "curl -fsSL -o data.json https://x.dev/d.json && cat > run.sh <<'EOF'\necho hi\nEOF", 0),
                   rec(2, "bash run.sh", 0)]) == []
    assert unread([rec(1, "curl -fL -o tool.tgz https://x.dev/tool.tgz && tar xzf tool.tgz", 0),
                   rec(2, "./tool --version", 0)]) == []
    assert unread([rec(1, "curl -fsSL https://x.dev/i.sh | bash", 0)], steps=[]) == []


REPO = "https://github.com/acme/tinyq"


@pytest.mark.parametrize("steps", [
    ["git clone --depth 1 https://github.com/acme/tinyq.git /tmp/tinyq 2>&1", "pip install /tmp/tinyq"],
    ["git clone https://github.com/acme/tinyq tq && cd tq && pip install -e .[dev]"],
    ["rm -rf /tmp/x && git clone https://github.com/acme/tinyq /tmp/x && cp -r /tmp/x/. ./", "pip install -e ."],
    ["curl -L -o /tmp/tinyq.tgz https://github.com/acme/tinyq/releases/download/v1/tinyq-1.0.tgz", "npm i -g /tmp/tinyq.tgz"],
    ["pip install tinyq", "npm i -g @acme/tinyq", "uv tool install --from git+https://github.com/acme/tinyq tinyq"],
    ["pip install -r /tmp/requirements.txt tinyq", "cargo install --git https://github.com/acme/tinyq --root ~/.local"],
])
def test_the_published_package_or_the_projects_own_source_is_what_a_user_installs(steps: list[str]):
    assert modified_copy(steps, ["cat > /tmp/sample/main.go <<'EOF'\npackage main\nEOF"], REPO) == []


@pytest.mark.parametrize("steps, checks, why", [
    (["uv tool install /tmp/tinyq_fix --force 2>&1"], [], "local copy"),
    (["git clone https://github.com/other/fork /tmp/tinyq", "pip install /tmp/tinyq"], [], "local copy"),
    (["cd /tmp/scratch && pip install ."], [], "local copy"),
    (["git clone https://github.com/acme/tinyq /tmp/tinyq && sed -i 's/x/y/' /tmp/tinyq/tinyq/cli.py",
      "pip install /tmp/tinyq"], [], "patched"),
    (["git clone https://github.com/acme/tinyq t && cd t && git apply /tmp/fix.diff && pip install ."], [], "patched"),
    (["git clone https://github.com/acme/tinyq t && cat > t/tinyq/server.py <<'EOF'\nprint(1)\nEOF",
      "pip install ./t"], [], "patched"),
    (["npm i -g tinyq"], ["sed -i 's/a/b/' ~/.local/lib/node_modules/tinyq/index.js && tinyq --help"], "patched"),
])
def test_a_copy_the_box_made_or_edited_is_not(steps: list[str], checks: list[str], why: str):
    problems = modified_copy(steps, checks, REPO)
    assert problems and ("no cited step fetched" if why == "local copy" else "patched copy") in problems[0]


def test_local_install_targets():
    assert local_installs("python3 -m pip install -e ./pkg/core --no-deps") == ["./pkg/core"]
    assert local_installs('pip install --user "./nexus-agent[all]"') == ["./nexus-agent"]
    assert local_installs("cargo install --path . --locked") == ["."]
    assert local_installs("pip install requests -t /tmp/target") == [] and local_installs("ls /tmp") == []


def test_an_install_from_a_patched_copy_does_not_pass():
    log = [rec(1, "git clone https://github.com/acme/tinyq /tmp/t && sed -i 's/bug/fix/' /tmp/t/tinyq/main.py", 0),
           rec(2, "pip install /tmp/t", 0, "Successfully installed tinyq"),
           rec(3, "tinyq --version", 0, "tinyq 1.0"), rec(4, "tinyq run demo", 0, "demo done")]
    tests = [{"command_id": 3, "expected_signal": "1.0"}, {"command_id": 4, "expected_signal": "demo done"}]
    verdict = log_verdict(claim("function", [1, 2], tests), log, repo_url=REPO)
    assert verdict.level == "unverified" and any("patched copy" in p for p in verdict.problems)
    clean = [rec(1, "git clone https://github.com/acme/tinyq /tmp/t", 0), *log[1:]]
    assert log_verdict(claim("function", [1, 2], tests), clean, repo_url=REPO).level == "function"


def test_a_check_that_reads_a_file_only_an_uncited_command_wrote_does_not_pass():
    """mcp-audit, 2026-10-31: a dashboard setup read a scan another check wrote; the fresh box had none."""
    log = [rec(1, "uv tool install mcp-audit-scanner", 0, "installed"),
           rec(2, "cat > /tmp/risky.json <<'EOF'\n{\"mcpServers\": {}}\nEOF", 0),
           rec(3, "mcp-audit scan --path /tmp/risky.json --format json -o /tmp/scan.json", 1, "grade F"),
           rec(4, "mcp-audit dashboard --from-json /tmp/scan.json --no-open --port 8088", 0, "pid 7",
               tool="run_background"),
           rec(5, "curl -s http://127.0.0.1:8088/", 0, "Security Dashboard"),
           rec(6, "mcp-audit lock /tmp/risky.json.d --path /tmp/risky.json", 0, "Lock: 3 servers checked")]
    tests = [{"command_id": 3, "setup_ids": [2], "expected_signal": "grade F", "expected_exit_code": 1},
             {"command_id": 5, "setup_ids": [4], "expected_signal": "Security Dashboard"},
             {"command_id": 6, "expected_signal": "Lock: 3"}]
    verdict = log_verdict(claim("service", [1], tests), log)
    by_id = {c.command_id: c for c in verdict.checks}
    assert by_id[3].passed  # its input file is its own setup
    assert not by_id[5].passed and by_id[5].problems == [
        "its setup 4 uses /tmp/scan.json, which only command 3 wrote; cite a command that writes it (and exits 0) "
        "in setup_ids, or a fresh box will not have it"]
    assert by_id[6].passed  # setup 2 runs before every check in a fresh box, cited by check 3
    assert verdict.level == "function"
    # A name that only contains the path is not a use of it.
    log[5] = rec(6, "mcp-audit lock /tmp/scan.json.d", 0, "Lock: 3 servers checked")
    assert {c.command_id: c.passed for c in log_verdict(claim("function", [1], tests), log).checks}[6]
