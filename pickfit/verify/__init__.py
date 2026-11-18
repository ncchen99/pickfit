"""Sandbox verification: install a tool in a fresh box, fix errors, prove it works.

- box.py: the Box interface and DockerBox (local development).
- machine.py: the provider seam, one fresh Linux machine driven as root; linux_box.py: LinuxBox, what turns any
  provider's machine into a box; modal_box.py: ModalMachine and ModalBox (gVisor or a VM on Modal);
  ssh_machine.py: a rented VM over SSH with the box as a container on it; ec2_machine.py: Ec2Machine and Ec2Box,
  and what every instance on EC2 shares (security groups, lifetime, the pool of started-once instances).
- win_machine.py: a rented Windows VM over SSH; windows_box.py: WindowsBox, the box on it; ec2_windows.py: the
  Windows Server image, Ec2WinMachine and Ec2WindowsBox. vbox_box.py: the older Windows box, on VirtualBox on a PC.
- plan.py, rules.py: rank the install methods a README states; rule table for common errors.
- agent.py: the Muse Spark agent loop that drives a Box through function tools.
- verdict.py: the level the command log supports (finish only cites command ids).
- replay.py: a fresh box reruns the steps online and the smoke tests offline.
- screenshot.py, judge.py: redrawn terminal screenshots and the separate screen judge.
- result.py: the VerificationRun, and the write-back into data/software/<slug>.json.
- pipeline.py: agent -> replay -> judge -> VerificationRun for one tool; batch.py: many at once.
- limits.py: `--limits-test`, the guard-rail probes for a box; limits_mac.py: the same for a macOS GUI box (limits.py's
  checks without its Xvfb ones, then the desktop, window list, VNC secret, TCC and window-server checks).
"""
