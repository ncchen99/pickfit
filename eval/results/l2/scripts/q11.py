"""L2 for q11 (eval/fixtures/q11/README.md), run 1, in a tart clone (16 GB, 8 vCPU; method change of 2026-11-02).

  uv run python eval/results/l2/scripts/q11.py control|experimental setup|install|model|ask|score

Phases share one clone (clone.txt); `score` deletes it. Recorded choices, the same for both groups:
- Install method: the one the pick extraction recorded (README 9.1 C2: "含指定的安裝方式"). Control: the first
  option, the macOS app from https://ollama.com/download ("拖進「應用程式」再打開"); the grader does the browser
  download, the drag and the opening with curl, hdiutil/cp and `open` (a curl download carries no quarantine flag,
  so no Gatekeeper first-open dialog). Experimental: its brew lines.
- The answer's lines run one by one in zsh (the Terminal shell) with interactivecomments set, so a trailing
  `# ...` is a comment as in bash on Linux (zsh's interactive default would pass it to the command as words).
- First run that downloads the model (control step 2): run once online under a pty, `/bye` typed, no prompt sent.
- Modelfile: the answer's file, verbatim, in the home folder; then the answer's `ollama create`.
- Asking: the answer's first way, `ollama run tw`, one new run per prompt with the frozen prompt pasted (stdin).
  temperature 0.6 is the answer's and no documented env var or config file fixes the seed, so P1-P5 run three
  times and 2 of 3 decide (README "取樣設定" rule 2).
- Memory: footprint_watch.py for the test user from before the first install line to after the last reply;
  the Tart Guest Agent (runs as the test user from /usr/local/libexec) is excluded at recompute.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mac_common import FIX, ROOT, VM, clone_name, keep_files, setup, zsh  # noqa: E402
from mac_vm import now, pressure  # noqa: E402

GROUP, PHASE = sys.argv[1], sys.argv[2]
OUT = ROOT / "eval" / "results" / "l2" / f"q11-{GROUP}"
R = f"/Users/Shared/eval-runs/q11-{GROUP}"
ANSWER = (ROOT / f"eval/results/runs/run1/q11/{GROUP}/attempt-1/answer.md").read_text()
MODELFILE = re.search(r"```\n(FROM .*?)```", ANSWER, re.S).group(1)
PINS = {i["id"]: i for i in json.loads((ROOT / "eval/fixtures/pins.json").read_text())["items"]}

if GROUP == "control":
    INSTALL = """curl -fL -o ~/Downloads/Ollama.dmg https://ollama.com/download/Ollama.dmg
hdiutil attach -nobrowse -mountpoint /tmp/ollama-dmg ~/Downloads/Ollama.dmg && cp -R /tmp/ollama-dmg/Ollama.app /Applications/ && hdiutil detach /tmp/ollama-dmg
open /Applications/Ollama.app"""
    FIRST_RUN = "ollama run hf.co/phate334/Llama-3-Taiwan-8B-Instruct-Q4_K_M-GGUF"
else:
    INSTALL = """brew install ollama          # 安裝 Ollama
brew install opencc          # 安裝簡轉繁工具
brew services start ollama   # 讓 Ollama 在背景執行（也可以另開一個視窗跑 ollama serve）
ollama pull hf.co/DevQuasar-9/voidful.Llama-Breeze2-8B-Instruct-text-only-GGUF:Q4_K_M"""
    FIRST_RUN = None
CREATE = "ollama create tw -f Modelfile"
DIAG = ("sleep 45; lsappinfo list | grep -E '^ *[0-9]+\\) \"' ; /bin/zsh -il -c 'command -v ollama'; ls -l /usr/local/bin/ollama 2>&1; "
        "ps -axo user,pid,command | grep -i [o]llama | cut -c1-160")

if PHASE == "setup":
    with VM(f"q11-{GROUP}", OUT, ["q11", "_mac", "_shared", "pins.json"], cpu=8, memory_mb=16384, keep=True) as vm:
        setup(vm, R)
        vm.sh(zsh("setopt | grep -i interactivecomments || echo 'interactivecomments off'"), "Terminal zsh: are # comments comments?")
        vm.sh("nohup sleep 600 > /dev/null 2>&1 < /dev/null & echo started $!", "grader check: does a background job outlive its exec?")
        vm.sh("pgrep -fl 'sleep 600' || echo gone", "grader check: background job still there")
    sys.exit(0)

with VM(f"q11-{GROUP}", OUT, [], name=clone_name(OUT), keep=PHASE != "score") as vm:
    if PHASE == "install":
        vm.sh(f"sudo nohup /usr/bin/python3 {FIX}/q11/mac/footprint_watch.py --uid $(id -u) --out {R}/footprint "
              f"> {R}/footprint.log 2>&1 & sleep 3; cat {R}/footprint.log", "L2-1 footprint watch starts")
        vm.put(f"{R}/install.lines", (INSTALL + "\n").encode())
        vm.sh(zsh(f"setopt interactivecomments; cd ~ && OUT={R}; . {R}/lib.zsh; run_lines install {R}/install.lines; all_ok install && echo INSTALL-OK || echo INSTALL-FAIL"),
              "L2-1 install lines (one zsh; # starts a comment, as in bash)", timeout=3600)
        vm.sh(DIAG, "after install: apps in the session, ollama on PATH, processes", timeout=300)
        if GROUP == "control":  # the app's first launch: an authorization dialog (SecurityAgent) to install its CLI.
            # A person types the password and presses OK; nobody can click in the headless guest, so the grader does
            # what the dialog does (the CLI link), closes the dialog and restarts the app (attempt 2 showed this works).
            vm.sh("lsappinfo info -only name `lsappinfo front`; ls /usr/local/bin/ollama 2>&1", "the window in front; CLI link present?")
            vm.sh("sudo mkdir -p /usr/local/bin && sudo ln -sf /Applications/Ollama.app/Contents/Resources/ollama /usr/local/bin/ollama && "
                  "ls -l /usr/local/bin/ollama", "grader does the authorization dialog's default (CLI link in /usr/local/bin)")
            vm.sh("sudo pkill -x SecurityAgent; pkill -x Ollama; sleep 5; open /Applications/Ollama.app; echo reopen exit $?",
                  "dialog closed, app restarted")
            vm.sh(DIAG, "after restarting the app: apps in the session, ollama on PATH, processes", timeout=300)
            vm.sh(zsh("ollama --version; curl -s http://127.0.0.1:11434/api/version"), "CLI and server answer")
    elif PHASE == "reopen":  # control only: install 3 was `open -a Ollama`, run before LaunchServices knew the copied app
        vm.sh('pkill -x "Setup Assistant"; sleep 2; pgrep -x "Setup Assistant" || echo closed',
              "the new account's first-login Setup Assistant closed (part of making the account, CHECKLIST)")
        vm.sh(zsh("cd ~ && open /Applications/Ollama.app; echo open exit $?"), "install 3 again as the double-click: open /Applications/Ollama.app")
        vm.sh(DIAG, "after opening: apps in the session, ollama on PATH, processes", timeout=300)
    elif PHASE == "gui-default":  # control only: the app's first launch shows an authorization dialog (SecurityAgent)
        # to install its command line tool; a person types the password and presses OK. Nobody can click in the
        # headless guest, so the grader does what that dialog does (the CLI link), closes the dialog, reopens the app.
        vm.sh("ls -l /Applications/Ollama.app/Contents/Resources/ | grep -i ollama; lsappinfo info -only name `lsappinfo front`",
              "the app's CLI binary; the window in front")
        vm.sh("sudo mkdir -p /usr/local/bin && sudo ln -s /Applications/Ollama.app/Contents/Resources/ollama /usr/local/bin/ollama && ls -l /usr/local/bin/ollama",
              "grader does the authorization dialog's default (CLI link in /usr/local/bin)")
        vm.sh('pkill -x SecurityAgent; sleep 3; pgrep -x SecurityAgent || echo dialog-gone; osascript -e \'quit app "Ollama"\'; sleep 5; '
              'open /Applications/Ollama.app; echo reopen exit $?', "dialog closed, app quit and opened again")
        vm.sh(DIAG, "after reopening: apps in the session, ollama on PATH, processes", timeout=300)
        vm.sh(zsh("ollama --version; curl -s http://127.0.0.1:11434/api/version"), "CLI and server answer")
    elif PHASE == "gui-default2":  # the dialog runs as a system user: close it with sudo, restart the app
        vm.sh("ps -axo user,pid,command | grep [S]ecurityAgent; sudo pkill -x SecurityAgent; sleep 5; pgrep -x SecurityAgent || echo dialog-gone",
              "authorization dialog closed (sudo)")
        vm.sh("pkill -x Ollama; sleep 5; pgrep -x Ollama || echo app-quit; open /Applications/Ollama.app; echo reopen exit $?", "app restarted")
        vm.sh(DIAG, "after restarting: apps in the session, ollama on PATH, processes", timeout=300)
        vm.sh(zsh("ollama --version; curl -s http://127.0.0.1:11434/api/version"), "CLI and server answer")
    elif PHASE == "resume":  # experimental: `ollama create` (which downloads the model) hit the grader's 20-minute step
        # limit, so `tw` never existed and the prompts after it ran against no model. Set those aside and finish the step.
        vm.sh(f"cd {R} && mv replies replies-attempt1-no-model && sudo mv footprint footprint-part1 && sudo mv footprint.log footprint-part1.log && ls",
              "set aside the replies made without a model; keep footprint part 1")
        vm.sh(f"sudo nohup /usr/bin/python3 {FIX}/q11/mac/footprint_watch.py --uid $(id -u) --out {R}/footprint "
              f"> {R}/footprint.log 2>&1 & sleep 3; cat {R}/footprint.log", "L2-1 footprint watch part 2 starts")
        vm.sh(zsh(f"cd ~ && {CREATE}; echo create exit $?"), "ollama create tw -f Modelfile again (it downloads the model; no grader limit short of 90 min)", timeout=5400)
        vm.sh(zsh("ollama list; ollama --version"), "models and version")
    elif PHASE == "reboot":  # host swapping while the guest's memory was full of the download (2026-11-02 20:50):
        # network back on, footprint part 2 closed, clean reboot so the guest starts with empty memory, part 3 started
        vm.sh(f"PATH=/usr/bin:/bin:/usr/sbin:/sbin sudo sh {FIX}/q11/mac/offline.sh on {R}/net-state.txt 2>&1 | tail -2; "
              f"cd {R} && sudo rm -f net-state.txt; [ -d replies ] && mv replies replies-attempt2-hostswap; ls", "network on; prompts so far set aside")
        vm.sh(f"sudo touch {R}/footprint/stop; sleep 5; ls {R}/footprint; cd {R} && sudo mv footprint footprint-part2 && sudo mv footprint.log footprint-part2.log",
              "L2-1 footprint part 2 stop")
        vm.reboot()
    if PHASE in ("reboot", "restart"):  # restart: the reboot step alone (the first try stopped inside reboot())
        if PHASE == "restart":
            vm.reboot()
        vm.sh("whoami; stat -f %Su /dev/console; pgrep -fl 'ollama serve' | cut -c1-80", "after reboot: user, the answer's background server")
        vm.sh(f"sudo nohup /usr/bin/python3 {FIX}/q11/mac/footprint_watch.py --uid $(id -u) --out {R}/footprint "
              f"> {R}/footprint.log 2>&1 & sleep 3; cat {R}/footprint.log", "L2-1 footprint watch part 3 starts")
    elif PHASE == "model":
        if FIRST_RUN:
            vm.sh(f"cd ~ && ( until grep -q 'Send a message' {R}/first-run.txt 2> /dev/null; do sleep 5; done; printf '/bye\\n' ) | "
                  f"script -q -t 0 {R}/first-run.txt /bin/zsh -ilc {json.dumps(FIRST_RUN)}; echo first-run exit $?; "
                  f"tail -c 300 {R}/first-run.txt | tr -d '\\033'", "first run online (model download), /bye typed at the prompt, no prompt sent", timeout=5400)
        vm.put("/tmp/Modelfile", MODELFILE.encode())
        vm.sh("cp /tmp/Modelfile ~/Modelfile && cat ~/Modelfile", "Modelfile (the answer's, verbatim)")
        vm.sh(zsh(f"cd ~ && {CREATE}; echo create exit $?"), "ollama create tw -f Modelfile", timeout=1200)
        vm.sh(zsh("ollama list; ollama --version"), "models and version")
    elif PHASE == "ask":
        START = tuple(int(x) for x in os.environ.get("Q11_START", "1:1").split(":"))  # resume at run:prompt
        vm.sh(f"PATH=/usr/bin:/bin:/usr/sbin:/sbin; if [ -f {R}/net-state.txt ]; then sh {FIX}/q11/mac/offline.sh check 2>&1 | tail -1; "
              f"else sudo sh {FIX}/q11/mac/offline.sh off {R}/net-state.txt 2>&1 | tail -4; fi", "L2-2 offline off (guest network services)")
        for run in (1, 2, 3):
            free = subprocess.run("memory_pressure | tail -1", shell=True, capture_output=True, text=True).stdout.strip()
            swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout.strip()
            level = pressure()
            vm.log.append({"what": f"host memory before prompt set {run}", "at": now(), "exit": 0,
                           "tail": f"{free}; swap {swap}; pressure level {level}"})
            print(f"host memory before prompt set {run}: {free}; swap {swap}; level {level}", flush=True)
            used_mb = float(swap.split("used = ")[1].split("M")[0])
            if level >= 4 or used_mb > 16384:
                vm.log.append({"what": f"stopped before prompt set {run}: host memory", "at": now(), "exit": 1, "tail": swap})
                raise SystemExit(f"host memory: level {level}, swap used {used_mb:.0f} MB; stopping (coordinator rule)")
            vm.sh(f"mkdir -p {R}/replies/run{run}", f"run {run} folder", quiet=True)
            for p in range(1, 6):
                if (run, p) < START:
                    continue
                # README L2-2: a prompt with no reply within 10 minutes fails; the watchdog stops the client at 600 s
                # (attempts before 2026-11-02 21:25 used perl's alarm, which does not stop ollama)
                out, err = f"{R}/replies/run{run}/P{p}.txt", f"{R}/replies/run{run}/P{p}.err"
                vm.sh(zsh(f"cd ~ && ollama run tw < {FIX}/q11/prompts/P{p}.txt > {out} 2> {err} & pid=$!; "
                          f"( sleep 600; kill $pid 2> /dev/null && echo 'grader: stopped at the 10-minute limit' >> {err} ) & w=$!; "
                          f"wait $pid; rc=$?; kill $w 2> /dev/null; echo exit $rc; wc -m < {out}"),
                      f"L2-2 run {run} P{p}", timeout=700, quiet=True)
        vm.sh(f"PATH=/usr/bin:/bin:/usr/sbin:/sbin sh {FIX}/q11/mac/offline.sh check 2>&1 | tail -2; sudo sh {FIX}/q11/mac/offline.sh on {R}/net-state.txt 2>&1 | tail -2",
              "L2-2 offline check after the prompts, then network on")
        vm.sh(f"sudo touch {R}/footprint/stop; sleep 5; ls {R}/footprint; pgrep -u $(id -u) -fl tart-guest-agent; tail -3 {R}/footprint.log", "L2-1 footprint stop")
        vm.sh(f"python3 {FIX}/q11/score_replies.py --write-judge-requests {R}/judge-requests.jsonl "
              f"{R}/replies/run1 {R}/replies/run2 {R}/replies/run3", "L2-3 blind judge requests")
        keep_files(vm, R, OUT, "run-folder-after-ask.tgz")
    elif PHASE == "score":
        for run in (1, 2, 3):
            vm.put(f"{R}/replies/run{run}/judge.json", (OUT / f"judge-run{run}.json").read_bytes())
        for d in ("STCharacters", "STPhrases", "TSCharacters", "TWVariants"):
            p = PINS[f"opencc-{d}.txt"]
            vm.sh(f"mkdir -p /tmp/opencc && curl -fsSL -o /tmp/opencc/{d}.txt '{p['url']}' && "
                  f"echo '{p['verified_sha256']}  /tmp/opencc/{d}.txt' | shasum -a 256 -c -", f"grader pin opencc {d}", quiet=True)
        vm.sh(f"python3 {FIX}/q11/score_replies.py --dict-dir /tmp/opencc --json {R}/replies/run1 {R}/replies/run2 {R}/replies/run3 "
              f"> {R}/score.json; echo exit $?", "L2-3, L2-4, L2-5 score_replies", quiet=True)
        vm.sh(f"AG=$(pgrep -u $(id -u) -f tart-guest-agent | tr '\\n' ' '); python3 {FIX}/q11/mac/footprint_watch.py recompute "
              f"{R}/footprint/footprint.json --exclude-pid $AG > {R}/footprint-recompute.txt 2>&1; echo exit $?", "L2-1 recompute without the guest agent", quiet=True)
        vm.sh(f"sudo sh {FIX}/q11/mac/snapshot_state.sh {R} after evaluser > {R}/snapshot-after.log 2>&1; "
              f"python3 {FIX}/q11/mac/diff_state.py {R}/before {R}/after > {R}/diff-before-after.md 2>&1; echo exit $?", "after snapshot and diff", timeout=1800, quiet=True)
        keep_files(vm, R, OUT)
