"""Sandbox verification: install a tool in a fresh box, fix errors, prove it works.

- box.py: the Box interface and DockerBox (local development); modal_box.py: ModalBox (gVisor).
- plan.py, rules.py: rank the install methods a README states; rule table for common errors.
- agent.py: the Muse Spark agent loop that drives a Box through function tools.
- verdict.py: the level the command log supports (finish only cites command ids).
- replay.py: a fresh box reruns the steps online and the smoke tests offline.
- screenshot.py, judge.py: redrawn terminal screenshots and the separate screen judge.
- result.py: the VerificationRun, and the write-back into data/software/<slug>.json.
- pipeline.py: agent -> replay -> judge -> VerificationRun for one tool; batch.py: many at once.
- limits.py: `--limits-test`, the guard-rail probes for a box.
"""
