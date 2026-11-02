"""L2 for q12 (eval/fixtures/q12/README.md), run 1, in a tart clone (8 GB, 8 vCPU: host memory, coordinator 2026-11-02; method change of 2026-11-02).

  uv run python eval/results/l2/scripts/q12.py control|experimental setup|run

`run` deletes the clone at the end. Recorded choices, the same for both groups:
- Option A, the first given (uv), as for the Linux questions; optional steps are not run (control's
  "Optional: try generation first"), required ones are (experimental's "Quick test").
- The frozen fixture model (model_pin.env, pinned 2026-11-02 as late calibration before any q12 run) fills the
  answers' example model, in generate and in the server command (README L2-2: filling the placeholder).
- Server and checks in one shell call: the server line as written, in the background with its transcript, the
  grader waits for it to listen, then check_model_files.py and client_check.py (pinned openai client in a grader
  venv outside the test user's PATH). Model name sent: the repo id passed to --model (both answers say so);
  API key: the placeholder each answer names.
- L2-5: server stopped, guest network services off, the same server line, both requests again, network on.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mac_common import FIX, ROOT, VM, clone_name, keep_files, setup, zsh  # noqa: E402

GROUP, PHASE = sys.argv[1], sys.argv[2]
OUT = ROOT / "eval" / "results" / "l2" / f"q12-{GROUP}"
R = f"/Users/Shared/eval-runs/q12-{GROUP}"
PIN = dict(re.findall(r"^(\w+)=(.*)$", (ROOT / "eval/fixtures/q12/model_pin.env").read_text(), re.M))
REPO = PIN["REPO_ID"]
OPENAI = "3.42.1"  # the latest release on PyPI at the late calibration (2026-11-02)
G = "/var/eval-grader/venv/bin/python"

INSTALL = """brew install uv
uv tool install mlx-lm"""  # control's first line ends in "# or: curl -LsSf https://astral.sh/uv/install.sh | sh" (a comment)
if GROUP == "control":
    INSTALL = INSTALL.replace("brew install uv", "brew install uv            # or: curl -LsSf https://astral.sh/uv/install.sh | sh")
    FIRST = []
    SERVER = f"mlx_lm.server --model {REPO} --host 127.0.0.1 --port 8080"
    KEY = "local"
else:
    FIRST = [f'mlx_lm.generate --model {REPO} --prompt "Write a Python hello world"']
    SERVER = f"mlx_lm.server --model {REPO} --port 8080"
    KEY = "sk-local"
INSTALL = "# Option A\n" + INSTALL  # the block's own first line is a comment too


PBS = ("https://github.com/astral-sh/python-build-standalone/releases/download/20261026/"
       "cpython-3.12.16%2B20261026-aarch64-apple-darwin-install_only.tar.gz")
PBS_SHA = "fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e"


def grader_venv(vm: VM) -> None:
    """The grader's Python (openai 3.42.1 needs 3.10+; macOS has 3.9): a pinned standalone CPython in /var/eval-grader,
    outside the test user's home and PATH, with the pinned openai client."""
    vm.sh(f"sudo mkdir -p /var/eval-grader && cd /var/eval-grader && sudo curl -fsSL -o py.tgz '{PBS}' && "
          f"echo '{PBS_SHA}  py.tgz' | shasum -a 256 -c - && sudo tar xzf py.tgz && sudo rm -rf venv && "
          f"sudo /var/eval-grader/python/bin/python3 -m venv /var/eval-grader/venv && sudo {G} -m pip install -q openai=={OPENAI} && "
          f"{G} -m pip freeze > {R}/grader-requirements.lock; {G} -V; shasum -a 256 {R}/grader-requirements.lock; grep -i openai {R}/grader-requirements.lock",
          "grader venv outside the user's PATH (pinned standalone CPython 3.12.16, openai 3.42.1)", timeout=900)


def serve_and_check(tag: str) -> str:
    return (f"cd ~ && ( {SERVER} ) > {R}/server-{tag}-transcript.txt 2>&1 & SRV=$!; "
            f"for i in $(seq 1 300); do lsof -nP -iTCP:8080 -sTCP:LISTEN > /dev/null 2>&1 && break; kill -0 $SRV 2> /dev/null || break; sleep 2; done; "
            f"lsof -nP -iTCP -sTCP:LISTEN -a -u $USER > {R}/listen-{tag}.txt 2>&1; cat {R}/listen-{tag}.txt; "
            + (f"python3 {FIX}/q12/check_model_files.py --marker {R}/marker > {R}/model-files.txt 2>&1; echo model-files exit $?; " if tag == "online" else "")
            + f"{G} {FIX}/q12/client_check.py --base-url http://127.0.0.1:8080/v1 --model {REPO} --api-key {KEY} "
            f"--out {R}/client-{tag}.json > {R}/client-{tag}.txt 2>&1; echo client exit $?; "
            f"kill $SRV; sleep 3; pkill -f mlx_lm.server; sleep 2; lsof -nP -iTCP:8080 -sTCP:LISTEN || echo port-closed")


if PHASE == "setup":
    with VM(f"q12-{GROUP}", OUT, ["q12", "q11", "_mac", "_shared"], cpu=8, memory_mb=8192, keep=True) as vm:
        setup(vm, R)
        grader_venv(vm)
        vm.sh(f"cd {FIX}/q12 && {G} selftest.py 2>&1 | tail -3", "q12 selftest with the grader venv", timeout=600)
    sys.exit(0)

if PHASE == "grader":  # control: the setup's venv step failed (the image's Homebrew Python cannot run once moved)
    with VM(f"q12-{GROUP}", OUT, [], name=clone_name(OUT), keep=True) as vm:
        grader_venv(vm)
        vm.sh(f"cd {FIX}/q12 && {G} selftest.py 2>&1 | tail -3", "q12 selftest with the grader venv", timeout=600)
    sys.exit(0)

with VM(f"q12-{GROUP}", OUT, [], name=clone_name(OUT)) as vm:
  if PHASE == "run":
    vm.sh(f"curl -s https://huggingface.co/api/models/{REPO}/revision/main | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"sha\"])'; "
          f"echo pinned {PIN['REVISION']}", "fixture model: latest revision still the pinned one?")
    vm.sh(f"touch {R}/marker", "marker before the first install line")
    vm.put(f"{R}/install.lines", (INSTALL + "\n" + "\n".join(FIRST) + "\n").encode())
    vm.sh(zsh(f"setopt interactivecomments; cd ~ && OUT={R}; . {R}/lib.zsh; run_lines install {R}/install.lines; "
              f"all_ok install && echo INSTALL-OK || echo INSTALL-FAIL; cat {R}/install-*.txt > {R}/steps-transcript.txt"),
          "L2-1 install lines (one zsh; # starts a comment, as in bash)", timeout=3600)
  if PHASE in ("run", "checks"):
    if PHASE == "checks":  # control: the install shell kept running in the guest after the host-side run was stopped
        vm.sh("while pgrep -f 'run_lines install' > /dev/null; do sleep 10; done; "
              f"cat {R}/steps.txt; cat {R}/install-*.txt > {R}/steps-transcript.txt", "L2-1 install lines finished (exits in steps.txt)", timeout=3600)
    vm.sh(zsh(serve_and_check("online")), "L2-2, L2-3, L2-4 server online and checks", timeout=1800)
    vm.sh(f"sudo sh {FIX}/q11/mac/offline.sh off {R}/net-state.txt 2>&1 | tail -2", "L2-5 offline off")
    vm.sh(zsh(serve_and_check("offline")), "L2-5 server restarted offline and checks", timeout=1800)
    vm.sh(f"sh {FIX}/q11/mac/offline.sh check 2>&1 | tail -1; sudo sh {FIX}/q11/mac/offline.sh on {R}/net-state.txt 2>&1 | tail -1",
          "L2-5 offline check, then network on")
    vm.sh(f"python3 {FIX}/q11/mac/scan_transcript.py {R}/*transcript.txt > {R}/scan-transcript.txt 2>&1; echo exit $?", "L2-6 transcript scan", quiet=True)
    vm.sh(f"sudo sh {FIX}/q11/mac/snapshot_state.sh {R} after evaluser > {R}/snapshot-after.log 2>&1; "
          f"python3 {FIX}/q11/mac/diff_state.py {R}/before {R}/after > {R}/diff-before-after.md 2>&1; echo exit $?",
          "L2-1 after snapshot and diff (GUI apps, casks)", timeout=1800, quiet=True)
    keep_files(vm, R, OUT)
