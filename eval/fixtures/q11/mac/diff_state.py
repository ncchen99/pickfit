#!/usr/bin/env python3
"""Mac L2 (q11, q12): compare two snapshot_state.sh snapshots and print the
removal checklist for README section 5 ("每次跑完照清單移除裝過的東西").
Python 3.8+ stdlib.

  python3 diff_state.py DIR/before DIR/after            # what the run added
  python3 diff_state.py DIR/before DIR/after-cleanup    # must print "nothing left"

Every line present in "after" but not in "before" is something the run added
and has to be removed (or, for listeners and processes, stopped). Lines only in
"before" are printed too: something the run removed or changed.
Exit 0 when nothing was added or removed, 1 otherwise.
"""
import os
import sys

ACTIONS = {
    "applications.txt": "delete the app bundle (GUI application installed)",
    "launchd-plists.txt": "launchctl bootout the job, then delete the plist",
    "pkg-receipts.txt": "remove the files listed by `pkgutil --files ID`, then `sudo pkgutil --forget ID`",
    "bin-dirs.txt": "remove the command (or uninstall the package that owns it)",
    "etc-paths.txt": "remove the PATH entry from /etc/paths or /etc/paths.d",
    "users-shared.txt": "delete from /Users/Shared",
    "users.txt": "delete the test account (sudo sysadminctl -deleteUser NAME)",
    "listeners.txt": "stop the process listening on this port",
    "test-user-processes.txt": "quit the process (log the test user out, then sudo pkill -u NAME)",
}


def lines(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return [l.rstrip("\n") for l in f if l.strip()]


def action_for(name):
    if name.startswith("brew-formulae"):
        return "brew uninstall --formula NAME (as the Homebrew owner); also brew services stop NAME"
    if name.startswith("brew-casks"):
        return "brew uninstall --cask --zap NAME (as the Homebrew owner)"
    if name.startswith("brew-taps"):
        return "brew untap NAME"
    if name.startswith("brew-info"):
        return "Homebrew itself changed: restore the baseline Homebrew (RUNBOOK)"
    return ACTIONS.get(name, "remove")


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    before, after = argv
    names = sorted(set(os.listdir(before)) | set(os.listdir(after)))
    skip = {"info.txt", "changed-outside-home.txt", "large-files-in-test-home.txt"}
    changed = 0
    print("# removal checklist: %s -> %s" % (before, after))
    for n in names:
        if n in skip or not n.endswith(".txt"):
            continue
        b, a = lines(os.path.join(before, n)), lines(os.path.join(after, n))
        if b is None and a is None:
            continue
        b, a = set(b or []), set(a or [])
        added, gone = sorted(a - b), sorted(b - a)
        if not added and not gone:
            continue
        changed += 1
        print("\n## %s\naction: %s" % (n, action_for(n)))
        for x in added:
            print("- [ ] added: %s" % x)
        for x in gone:
            print("- [ ] removed or changed (restore?): %s" % x)
    extra = lines(os.path.join(after, "changed-outside-home.txt"))
    if extra:
        changed += 1
        print("\n## files outside the test home changed during the run\n"
              "action: delete each file the run created (keep macOS's own updates); "
              "re-run snapshot afterwards")
        for x in extra:
            print("- [ ] %s" % x)
    big = lines(os.path.join(after, "large-files-in-test-home.txt"))
    if big:
        print("\n## large files in the test home (deleted with the account)")
        for x in big:
            print("- %s" % x)
    print("\nnothing left" if not changed else "\n%d section(s) to clean up" % changed)
    return 0 if not changed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
