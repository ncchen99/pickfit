"""Shared steps of the Mac L2 flows (q11, q12) in a tart clone (eval/runner/mac_vm.py).

setup(): the CHECKLIST's start, in the VM: baseline part 1 (new user, image Homebrew aside, reboot), part 2 (an empty
Homebrew from the official installer, its "next steps" line in ~/.zprofile), the run folder R, the before snapshot
and preflight. Every step after that runs as the new user in `zsh -il` (a Terminal window's shell).
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "eval" / "runner"))
from mac_vm import FIX, VM  # noqa: E402,F401

SCRIPTS = Path(__file__).resolve().parent
BREW_INSTALL = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"


def zsh(cmd: str) -> str:
    """A command as typed into a Terminal window (login, interactive zsh)."""
    return f"/bin/zsh -il -c {shlex.quote(cmd)}"


def clone_name(out: Path) -> str:
    return (out / "clone.txt").read_text().strip()


def setup(vm: VM, R: str) -> None:
    vm.baseline(SCRIPTS / "mac_baseline.sh")
    vm.sh(f"curl -fsSL {BREW_INSTALL} -o /tmp/brew-install.sh && shasum -a 256 /tmp/brew-install.sh && "
          "NONINTERACTIVE=1 /bin/bash /tmp/brew-install.sh > /tmp/brew-install.log 2>&1; rc=$?; tail -15 /tmp/brew-install.log; exit $rc",
          "baseline part 2: empty Homebrew, official installer (NONINTERACTIVE: no RETURN prompt)", timeout=2400)
    vm.sh("L=$(grep -o 'eval \"$(/opt/homebrew/bin/brew shellenv[^)]*)\"' /tmp/brew-install.log | head -1); "
          "[ -n \"$L\" ] && echo >> ~/.zprofile && echo \"$L\" >> ~/.zprofile && cat ~/.zprofile",
          "baseline: the installer's next-steps line in ~/.zprofile (copied from its output)")
    vm.sh(zsh("brew --version; brew list --formula | wc -l; brew list --cask | wc -l; xcode-select -p; "
              "pkgutil --pkg-info=com.apple.pkg.CLTools_Executables | grep version"), "baseline: Homebrew and CLT versions")
    vm.put("/tmp/lib.zsh", (SCRIPTS / "_lib_mac.zsh").read_bytes())
    vm.sh(f"sudo mkdir -p {R} && sudo chown evaluser {R} && cp /tmp/lib.zsh {R}/lib.zsh", "run folder")
    vm.sh(f"sudo sh {FIX}/q11/mac/snapshot_state.sh {R} before evaluser > {R}/snapshot-before.log 2>&1; echo exit $?",
          "before snapshot", timeout=1800, quiet=True)
    vm.sh(zsh(f"sh {FIX}/q11/mac/preflight.sh {R}/preflight.txt; echo preflight exit $?; tail -5 {R}/preflight.txt"), "preflight")


def keep_files(vm: VM, R: str, out: Path, name: str = "run-folder.tgz") -> None:
    vm.sh(f"cd {R} && tar czf /tmp/keep.tgz --exclude '*.gguf' --exclude 'models' . && ls -l /tmp/keep.tgz", "pack run folder", quiet=True)
    (out / name).write_bytes(vm.get("/tmp/keep.tgz"))
