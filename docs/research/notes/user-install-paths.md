# Install commands for users vs. the commands pickfit ran

2026-11-03 · 念誠 asked that the OpenPets page's install commands work on an ordinary Mac (they named
`/Users/sbx`, the sandbox user's home) without changing what pickfit verified.

## The cause

A verified guide's commands are the run's own, word for word: `SoftwareRecord` refuses install steps that differ
from the run's (`install.macos steps must be the run's steps`). `pickfit/index.py` copied them into the index and
the Worker showed them as they were. On 11/3, 41 listed guides named a sandbox home (3 macOS: mergegate, openpets,
quill; 38 Linux), in steps, first tasks, setups or checks: 40 are rewritten, 1 is flagged.

## The change

The records and the verified fields of the index are unchanged. `pickfit/userpaths.py` makes a user's copy by one
rule (no model): unquoted, the sandbox home becomes `"$HOME"`; inside double quotes, `$HOME`; inside single quotes
nothing expands, so that command stays as run and is listed as not portable (bittune's step 4, the only one). A
guide naming the box's work folder (`~/work`, which existed before the first step; 15 guides) says so. The Worker
gives users the copy and keeps the commands as run in `verified_in_pickfit` (MCP) and in a "Verified in pickfit"
fold on the tool page.

## Checked on macOS (tart VM, macOS GUI base)

`openpets-vm-log.json` and `openpets-opened-from-jane-q-user.png` here. The user commands came from the index
this branch builds. The VM's logged-in account is still the sandbox's (the GUI base has no other desktop
session), so a second account's home was made the way macOS makes one: `ditto` of
`/System/Library/User Template/Non_localized` (Desktop, Documents, Downloads, Library, Movies, Music, Pictures,
Public) to `/Users/Shared/Jane Q User`, and every command ran with `HOME` set to it.

- No user command contains `sbx`; each parsed with `zsh -n` and `bash -n`.
- In zsh (macOS's default shell): the download (85 s) and the install (mount at
  `/Users/Shared/Jane Q User/mnt/openpets`, copy, eject) exited 0.
- `"$HOME"/Applications/openpets.app` resolved to `/Users/Shared/Jane Q User/Applications/openpets.app`, which
  existed with version 4.1.0; nothing was written to `/Users/sbx/Applications`.
- `open "$HOME"/Applications/openpets.app` exited 0; the app's processes ran from that path (pgrep), and the
  screenshot shows the pet on the desktop and OpenPets' menu bar item.

Found on the way: the first try used an empty folder as the home and the download failed (curl exit 56,
"Failed to open the file .../Downloads/OpenPets-mac-arm64.dmg: No such file or directory"): the verified steps assume `~/Downloads` exists, as it does for every
macOS account. Not checked: a separate logged-in macOS account (only `HOME` changed, in the same session), bash
running the install (only its syntax), and the 38 Linux guides on a real Linux machine (their rewritten commands
are checked for syntax by `tests/test_userpaths.py`, not run).
