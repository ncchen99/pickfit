# SAM 3.1 as a locator for GUI controls: probe (11/3)

Question: can Meta's SAM 3.1 find the control the GUI operator wants to click on pickfit's saved screenshots,
so the operator could name a target ("gear icon") and pickfit click the box's centre? Measure only; the
operating loop is unchanged.

## Method
- 29 screenshots from saved GUI verification evidence (~/.pickfit/evidence, 25 apps, Linux Xvfb and macOS),
  each with a recorded operator click that changed the next screen. 19 targets are icon-only controls (menu,
  gear, plus, close, folder, arrows, slider knob, radio, stop), 10 are text controls (a control group).
- Ground truth: the click point, nudged onto the control by eye where the click landed a few pixels off.
  The noun phrase for each target was written before any SAM call
  (`sam-3-1-gui-probe-targets.json`).
- One call per screenshot: Meta Responses API, model `sam-3.1`, an `input_text` phrase and the PNG as a
  base64 data URL (accepted), streamed; boxes parsed from `<|box;x1;y1;x2;y2;w;h[;c]|>` (source pixels).
  Every call held and settled in the ledger's Meta budget, stage `probe-sam-3.1` (`scripts/probe_sam_gui.py`).
- hit = the target point lies inside any returned box; top = inside the first/most confident box.

## Numbers (`sam-3-1-gui-probe-results.json`)
| | hit | top box hit | no box returned | boxes per query (median, max) | latency median (range) |
|---|---|---|---|---|---|
| icons (19) | 8 (42%) | 7 (37%) | 9 | 1, 8 | 1.25 s (0.4-3.5) |
| text (10) | 4 (40%) | 4 (40%) | 6 | 0, 2 | 1.0 s (0.7-3.5) |

Cost: 31 calls (29 + 2 tests) x $0.0025 = $0.078, within the $0.10 limit.

## Failures
- nip4 "close button" (window x at top right): one confident box on a different header button at the left.
- vimix "open folder icon": one box on a small glyph 70 px away; the toolbar's folder icon was not found.
- portfolio "back arrow": three boxes; the first is a different arrow, the true one is second.
- freeorion "gear icon": eight boxes; the first is right, seven others are other round icons.
- No box at all for plain, common controls: a hamburger menu (waywallen), a radio button, a slider knob, and
  text buttons ("Play", "Skip", "Open File") and menu items ("Save As...", "Window").

## Verdict
Not worth adding now. It finds fewer than half of the icon targets (8/19), returns nothing for a third of
them, and sometimes one confident box on the wrong control, which a "click the box centre" rule would follow
blindly. In the GUI runs the operator's misses were not targeting (the zoomed view with the last click ringed
lands its clicks); the failures came from the environment (no Flatpak file dialog, no URI handler) and goals.

If it is tried later, the smallest safe design, behind a flag: the operator may answer `target: "<phrase>"`
instead of coordinates; pickfit calls SAM once; exactly one box -> click its centre; several -> draw them
numbered on the next screenshot and let the operator pick a number; none -> tell the operator and keep its
own 0-1000 click. That costs $0.0025 and about 1 s per targeted click, and with these hit rates it would
fall back more often than it helps.
