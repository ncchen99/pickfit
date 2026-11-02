# Why Linux desktop features go unchecked: environment, step budget, or model? (11/3)

Measure only: nothing was written back to data/software. Script: `scripts/gui_compare.py` (`census`,
`rerun`, `tally`); raw rows: `linux-gui-comparison-results.jsonl`. Two flags were added for this comparison,
both off by default: `PICKFIT_GUI_DESKTOP=full` (gui.py) and `PICKFIT_OPERATOR_EFFORT` (gui_operate.py).

## Answer
- **The fixed step cap was not binding.** Every Linux operation the operator finished itself and that passed
  took 15 steps or fewer. 60 steps rescued none of the 12 failed features, and Muse Wonder at 60 steps
  rescued none of 4. The operations that hit the cap were going in circles.
- **The model mattered somewhat.** At the same 28 steps, Muse Wonder passed 2 failed features that Muse Spark
  Open did not, at about 4x the cost per step. Muse Spark Open at reasoning effort medium passed 1.
- **The environment mattered for one class of feature: opening or choosing a file in a Flatpak app.**
  - With a session bus, the desktop portal and a file opener, portfolio's "open files" passed in 4 steps. It had
    failed at 60 steps and with Muse Wonder.
  - The Flatpak file chooser that never opened for concessio now opens.
- **The largest causes are upstream of all three.** The goals and checks the planning agent writes, and the
  app's own state:
  - checks whose expected text is what the operator types;
  - goals that name a control the app lacks ("press Ctrl+O");
  - setup dialogs that need a service (moose's Ollama provider).

## Arm 0: saved evidence (no cost)
All operations in `~/.pickfit/evidence` (agent runs and fresh-box replays):

| | Linux | macOS |
|---|---|---|
| operations chosen by the model | 75 | 45 |
| stopped at the step cap | 40 (11 at the old 18-step cap, 29 at 28) | 21 |
| ... of them going in circles at some point (`circling`) | 38 | 19 |
| said done | 24 (12 passed pickfit's check) | 21 (12 passed) |
| gave up / budget / no window / error | 5 / 2 / 2 / 2 | 3 / 0 / 0 / 0 |
| passed | 17 | 21 |
| steps of passes the operator finished (said done) | 3-15, median 8 | 4-23, median 11 |
| passes at the cap (the operator never said done; the check passed) | 4 | 9 |

So 28 was not binding for operations that worked. The p90 of 28 steps among passes comes from passes where
the operator never said done.

A tighter stop on loops would save steps but cost passes: the loop note does make the operator recover.
Stopping when the note fired in 6 of the last 8 steps would save 397 of 1,376 Linux steps (29%), and lose
2 of 17 Linux passes and 6 of 19 macOS passes.

## Arms A-D: the same features run again
**How.** For each app, `rerun` starts a fresh Modal box like the original run's: the same runtime and image,
with a display and no GPU. It reruns the agent's shell commands that exited 0 before the operation (the
install, folders it made). Then it runs the same operation spec (goal, inputs, check) with
`gui_operate.run_operation`, changing only the named factor.

**Models.** Muse Spark Open ran on the Modal endpoint (Baseten was at $96.76 of its $100). Muse Wonder ran on
the Meta API. It takes the screenshot through the same call path, returns the strict JSON and points in 0-1000
(probe: 22 px from the target, inside the button).

**Features.** 14 Linux operations on 10 apps that stopped at the cap: 12 had failed, and 2 had passed although
the operator never said done (hivemind F2, comic-book-reader F2). No GPU boxes.

**Arm A** used the 6 operations whose notes blame the box:
- no portal for the file chooser (concessio, moose, comic-book-reader);
- no URI handler (portfolio).

| arm | change (everything else as before) | failed features now passing (of 12; A: of 6) | steps used | model cost | boxes |
|---|---|---|---|---|---|
| 0 | census of saved evidence | - | see above | $0 | $0 |
| A | 1920x1080, session bus with the GTK portal, mousepad as file opener; Spark Open, 28 | 1 of 6: portfolio "open files" (4 steps) | 5 of 6 hit 28 | Modal $0.61, Meta $0.02 | $0.07 |
| B | 60 steps; Spark Open | 1: quran-companion F3 (5 steps) | 9 of 14 used all 60; no pass after step 28 except one that had passed before | Modal $2.20, Meta $0.02 | $0.22 |
| C | Muse Wonder; 28 | 3: quran F3 (4), qelectrotech F4 (16), waywallen F4 (24) | 7 of 14 hit 28 | Meta $4.30 | $0.18 |
| C60 | Muse Wonder; 60, on the 4 it failed while the screen still changed | 0 of 4 | 3 used all 60, 1 gave up at 58 | Meta $3.64 | $0.14 |
| D | Spark Open, reasoning effort medium; 28 | 2: quran F3 (4), concessio F4 (28) | 11 of 14 hit 28 | Modal $1.40, Meta $0.03 | $0.16 |

quran-companion F3 passed in every rerun in 4-5 steps, so its original failure came from that run's state, not
from any of the factors.

Leaving it out, the rescues per arm are:

| arm | rescues |
|---|---|
| A | 1 (environment) |
| B | 0 |
| C | 2 |
| C60 | 0 |
| D | 1 |

The two operations that had passed at the cap passed again in every arm that ran them, at 10-32 steps.

Total: Meta $8.02 (of $10; includes the $0.01 Muse Wonder probe), Modal LLM $4.20, boxes about $0.77.

| app, op (feature) | before | A | B (60) | C (Wonder) | C60 | D (medium) |
|---|---|---|---|---|---|---|
| cinecred 15 (F1 arrange and style credits) | cap 28 | | give_up 31 | give_up 28 | | cap 28 |
| comic-book-reader 19 (F3 convert: QR code saved) | cap 28 | cap 28 | cap 60 | cap 28 | cap 60 | cap 28 |
| comic-book-reader 20 (F1 read CBZ, extract pages) | cap 28 | cap 28 | | | | |
| comic-book-reader 22 (F2 single/double page) | pass 28 | | pass 32 | pass 28 | | pass 28 |
| concessio 11 (F2 open a file) | cap 28 | cap 28 | | | | |
| concessio 12 (F4 change permissions) | cap 28 | cap 28 | cap 60 | cap 28 | | pass 28 |
| hivemind 8 (F2 workspace widgets) | pass 18 | | pass 17 | pass 18 | | pass 10 |
| moose 8 (F4 search document library) | cap 28 | cap 28 | cap 60 | cap 28 | give_up 58 | cap 28 |
| nip4 8 (F2 large images) | cap 28 | | cap 60 | cap 28 | | cap 28 |
| portfolio 18 (F2 open files) | cap 28 | **pass 4** | cap 60 | cap 28 | | cap 28 |
| portfolio 24 (F3 copy/move/delete) | cap 28 | | cap 60 | cap 28 | cap 60 | cap 28 |
| qelectrotech 16 (F1 create diagrams) | cap 28 | | cap 60 | cap 28 | cap 60 | cap 28 |
| qelectrotech 19 (F4 print to PDF) | cap 28 | | cap 60 | **pass 16** | | cap 28 |
| quran-companion 9 (F4 search verses) | cap 28 | | done 10 | done 7 | | done 14 |
| quran-companion 14 (F3 download recitations) | cap 28 | | pass 5 | pass 4 | | pass 4 |
| waywallen 16 (F4 smart playlists) | cap 28 | | cap 60 | **pass 24** | | cap 28 |

## What held the rest back (last steps of the reruns)

**Checks that can never pass.** These checks expect text that the operator itself typed, which pickfit rightly
discounts. They stopped at done every time.
- quran-companion F4 expects "Al-Fatiha" on screen.
- concessio F2 expects the file name "sample2.txt".

**Goals that guess the UI.**
- concessio's goals say "press Ctrl+O": the app opens files from a button. The operator kept pressing Ctrl+O
  because "the goal requires" it.
- qelectrotech F4's goal says keyboard only.
- comic-book-reader F3's goal is a QR-code tool, for the feature "convert comic books".

**App state that needs a service.** moose's library sits behind a "create a provider (Ollama)" dialog that the
operator could not leave.

**The environment.**
- Without a portal, the Flatpak file chooser never opens (concessio, moose import).
- Without an OpenURI handler, portfolio shows "Could not open".
- In A, both open. Still, comic-book-reader's GTK folder chooser kept "Select" disabled after the operator typed
  the path.
- The bigger screen was not tested on its own.

**A black screen, and precision.**
- cinecred (B and C): the screen went black once the creation wizard started, and the operator gave up. This
  may be the missing window manager: a new top-level window with nothing to map and raise it. A was not run on
  it.
- nip4: also black in B; in C, clicks on a menu that never opened.
- moose: clicks just outside a modal's close button.

**Caveats.**
- One run per arm and feature: rerun variance is large (quran F3).
- The rerun replays the agent's shell commands only. App state that earlier operations in the original run
  left (onboarding done, popups dismissed) starts fresh.

## Proposals (not implemented)
Since the cap was not binding, an adaptive step budget would not raise coverage. Keep 28 as the ceiling. A
budget that extends while the screen keeps changing would mostly fund loops: the screen changes when the
operator opens and closes the same dialog. A tighter loop stop saves about 29% of steps but loses passes (see
arm 0), so it is not worth it either.

What would raise coverage, in order of evidence:
1. **Refuse at spec time a screen_text or clipboard check whose expected text the goal tells the operator to
   type.** Today it is refused only after the operation, and the agent spends an operation and 28 steps
   first.
2. **Give the planning agent the app's first screenshot (from launch_gui) when it writes an operation's goal.**
   It should name controls the app shows, not guessed shortcuts. Tell the operator that a control the goal
   names may not exist, and to use the equivalent one. The operator instructions say this already, but the
   goal's wording wins.
3. **Ship the session bus, the GTK portal and a file opener in the Linux display image (arm A's change).**
   This needs a check of what the portal and dbus add to the box's attack surface. The watcher and the
   operator handled the portal's dialogs in these runs. It unblocks file choosers and "open with" in Flatpak apps, a class that no model or budget fixed.
4. **Optionally, a second try with Muse Wonder for a feature that failed with Muse Spark Open.** Price about
   $0.37 per 28-step try on Meta's budget. It won 2 of 12 here; more steps for it did not help.
