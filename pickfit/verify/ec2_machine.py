"""Ec2Machine: an EC2 instance as a Machine. The second provider under LinuxBox, after Modal.

SshMachine (ssh_machine.py) is the VM-over-SSH part every cloud shares. Ec2Instance, here, is what every pickfit
instance on EC2 is, Linux or Windows (ec2_windows.py is the Windows half). What is EC2's own:

- The image is an AMI pickfit bakes (bake_image): Debian, Docker, and a container image built on the instance.
  For a box that is sandbox.Dockerfile plus the box's image recipe, the inputs Modal builds from; WebBox brings
  its own (ContainerImage). The AMI's name carries the container image's tag and a hash of the host setup, so a
  change to either bakes a new one. The first start after a change bakes it (about five minutes);
  `pickfit verify --runner ec2 --prepare-base` does it ahead of time.
- A fresh instance per start() in the default VPC, with a public address and no IPv6. No key pair and no
  instance profile: the instance has no AWS identity at all.
- Lifetime: the instance is launched so that its own poweroff terminates it, and its disk is deleted with it.
  reap() ends pickfit instances that outlived their lifetime anyway (one that never booted far enough to
  schedule the poweroff); every start() calls it.
- Egress is three security groups pickfit makes once and checks at every start: control (SSH in from the
  harness, nothing out), online (out to ONLINE_CIDRS, nothing in) and offline (nothing either way). An instance
  wears control and one of the other two; the cut is one call that swaps them, checked from the instance as
  root before set_egress returns. Security groups do not filter the VPC's resolver, its link-local services or
  already-tracked connections; SshMachine's rules on the VM and LinuxBox's DNS rule cover those. The control
  group's rule for an address the harness had a week ago is removed when the group is next checked.
- Seal: the metadata service is needed while the instance boots (cloud-init reads the keys from it) and is
  turned off before the box exists, where root inside cannot turn it back on.
- The pool (POOL_ENV; POOL_DEFAULT members for each image): a new volume fetches every block from the image's snapshot
  on its first read, and that is most of a cold start. A pool member is an instance of the image that booted
  once behind the offline group with nobody's keys, read its whole disk, forgot the boot (cloud-init's record,
  the host keys it made) and stopped; stopped, it costs its disk only. A start takes one, gives it this
  machine's user data and starts it, so it boots into this machine's keys exactly as a new instance would, and
  launches the member that replaces it. A member nobody took in a week is reaped. Two harnesses that take the
  same member are told apart by a tag (see _claim); should that fail, the pinned host key refuses the loser,
  which then launches a new instance.
- Boxes come first. An account's quota is counted in vCPUs (8 for a new account) and a member that is warming
  up holds two of them. A member is added only while pickfit's instances in the region stay within VCPUS_ENV
  (6 by default: two boxes and one member warming), and a box the quota refuses ends the newest warming member
  and takes its room; with none to end it waits for another box to finish, up to QUOTA_WAIT_S.
- The lane limit: at most MAX_BOXES (2) machines of pickfit's at once in a region from one host, boxes and AMI
  builders alike, each holding a slot (a locked file) from before its launch to its end. A third waits for a slot.
- The ledger: every instance has a row in the boxes table (meter.BoxMeter: its type's price, at least a minute)
  and carries RUN_TAG and PURPOSE_TAG, which AWS's bill groups by once they are activated as cost allocation tags.
- The region is REGION_ENV, or DEFAULT_REGION: Taipei, because the harness is in Taiwan. Prices are on file for
  the regions in PRICES (Taipei's are 13% above us-east-1's for Linux and 8% for Windows; a command's round
  trips cost half). The security groups, the images and the pool are a region's own and are made there on
  first use.
- Credentials are boto3's default chain (an `aws login` session, a profile, or keys in the environment). The
  calls used: Describe*, RunInstances, StartInstances, TerminateInstances, ModifyInstanceAttribute,
  ModifyInstanceMetadataOptions, CreateTags, security group create/authorize/revoke, and for baking
  StopInstances and CreateImage.

Measured 2026-11-16 and 17 on c7i-flex.large, with the harness in Taiwan:

- `pickfit verify --limits-test --runner ec2` holds 23 of 23, in us-east-1 and in ap-east-2.
- Where a cold start went (us-east-1, 95 s): 10 s until EC2 says running; the kernel 9 s; cloud-init 18 s before
  sshd, 7.6 s of it waiting on the IPv6 metadata address these instances do not have; then dockerd 23 s and
  containerd 10 s, reading their own files from the snapshot. The same instance, stopped and started: 29 s, with
  dockerd up in under a second. With the image's two fixes (HOST_SETUP) a cold start is 71 s in us-east-1 and
  43 s in ap-east-2; from the pool it is 34 s in us-east-1 and 28 to 34 s in ap-east-2, of which 9 to 14 s are
  the claim's API calls and EC2's own start. Modal starts in about 6 s.
- A member's one boot takes 70 to 80 s for a box and 90 s for a web machine (thirty-two readers; with eight a
  box's took two and a half minutes).
- A web machine (web_box.on_ec2, ap-east-2) starts in 70 to 83 s as a new instance, 29 s of it reading the
  browser ahead (us-east-1, eight readers: 98 s), and in 37 s from the pool, where nothing is read ahead and
  Chromium opens its DevTools port in 2 s. On a new instance with nothing read ahead it took 9 s in ap-east-2
  and more than its 30 s in us-east-1.
- With a quota of 8 vCPUs, 2 of them another project's: a box that was refused ended a member that was warming
  up and started 17 s after it was asked for; a start with pickfit at six vCPUs added no member.
- A box costs about US$0.103 an hour in ap-east-2 and US$0.0915 in us-east-1 (Modal's 2 vCPU and 2 GiB:
  US$0.19); a pool member's disk, US$1.38 a month (us-east-1: US$1.28).
- A command takes about 0.4 s to ap-east-2 and 0.9 s to us-east-1: nearly all of it the round trips of one ssh
  session. A harness in the instance's region would not notice it.
- The turned-off metadata service still answers "403" to root; the box user gets nothing (the VM's own rule).
- After the cut, a connection the box user had open carried nothing more; one root had open still got its
  answer, as AWS's documentation says a tracked connection would. That is the limit SshMachine's docstring names.
"""

from __future__ import annotations

import datetime
import fcntl
import hashlib
import ipaddress
import json
import math
import os
import secrets
import shlex
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pickfit.env import get_env
from pickfit.verify.box import SANDBOX_DOCKERFILE, BoxError, BoxLimits, sandbox_image_tag
from pickfit.verify.linux_box import ImageRecipe, LinuxBox, image_recipe
from pickfit.verify.machine import ONLINE_CIDRS
from pickfit.verify.meter import BoxMeter, identity
from pickfit.verify.ssh_machine import DOCKER, NO_VSOCK_MODULES, SshMachine, lifetime_bootcmd

REGION_ENV = "PICKFIT_EC2_REGION"
DEFAULT_REGION = "ap-east-2"  # Taipei: next to the harness, so a command's round trips cost half of us-east-1's
CONTROL_CIDR_ENV = "PICKFIT_EC2_CONTROL_CIDR"  # where the harness connects from, when it is not this host's address
MY_ADDRESS_URL = "https://checkip.amazonaws.com"

# The host under the box's container. Debian's own account publishes the images.
BASE_AMI_OWNER = "136693071363"
BASE_AMI_NAME = "debian-13-amd64-*"
# (type, vCPU, MiB). The flex types are not burstable (a T3 in unlimited mode bills CPU credits on top, which a
# per-second ledger cannot know), and the two .large ones are what a Free Tier plan account may launch.
INSTANCE_SIZES = (("c7i-flex.large", 2, 4096), ("m7i-flex.large", 2, 8192), ("c7i-flex.xlarge", 4, 8192),
                  ("m7i-flex.xlarge", 4, 16384), ("m7i-flex.2xlarge", 8, 32768))
# USD an hour on demand for INSTANCE_SIZES in their order, and gp3's USD per GB-month: AWS's public price list,
# read 2026-11-16. "windows" includes the Windows Server licence. A region not listed here has no price on file.
PRICES: dict[str, dict[str, Any]] = {
    "us-east-1": {"linux": (0.08479, 0.09576, 0.16958, 0.19152, 0.38304),
                  "windows": (0.17219, 0.18316, 0.34438, 0.36632, 0.73264), "disk": 0.08},
    "ap-northeast-1": {"linux": (0.10673, 0.12369, 0.21347, 0.24738, 0.49476),
                       "windows": (0.19413, 0.21109, 0.38827, 0.42218, 0.84436), "disk": 0.096},
    "ap-east-2": {"linux": (0.09606, 0.11132, 0.19212, 0.22264, 0.44528),
                  "windows": (0.18346, 0.19872, 0.36692, 0.39744, 0.79488), "disk": 0.0864},
}
PRICES_READ = "2026-11-16"
PRICE_REGION = DEFAULT_REGION  # what pick_type prices by when it is given no region
INSTANCE_TYPES = tuple((name, vcpus, mib, PRICES[PRICE_REGION]["linux"][i])
                       for i, (name, vcpus, mib) in enumerate(INSTANCE_SIZES))
HOST_RESERVE_MB = 1024  # the VM's kernel, sshd and dockerd, next to the box's cgroup
IPV4_USD_PER_HOUR = 0.005  # a public IPv4 address, every region
HOURS_PER_MONTH = 730
DISK_GB = 16  # the plain box: the host, the image, and the box user's 1.5 GB of files
DISK_GB_EXTRA = {"gui": 8, "audio": 2, "build": 24}

GROUPS = {"control": "pickfit-box-control", "online": "pickfit-box-online", "offline": "pickfit-box-offline"}
GROUP_NOTES = {"control": "pickfit: SSH in from the harness, nothing out",
               "online": "pickfit: a box online, out to public IPv4 only",
               "offline": "pickfit: a box offline, nothing in or out"}
EXPIRES_TAG = "pickfit:expires"  # unix time after which reap() may end the instance
REAP_MARGIN_S = 300
BAKE_TYPE = "c7i-flex.large"
BAKE_LIFETIME_S = 60 * 60
LIVE_STATES = ["pending", "running", "stopping", "stopped"]
QUOTA_WAIT_S = 900  # a start the account's vCPU quota refuses is tried again this long: other boxes end
EVICT_SETTLE_S = 30  # after a warming member was ended for a box, how long before another may be
HARNESS_RULE = "pickfit harness, added "  # how the control group's own rules are described, with their date
HARNESS_RULE_DAYS = 7  # a rule for an address the harness had this long ago is removed when a new one is added

# The pool: instances that booted pickfit's image once, read their disk and stopped. A volume made from a snapshot
# fetches each block on its first read, which is most of a cold start; a pool member has its blocks already.
POOL_ENV = "PICKFIT_EC2_POOL"  # how many to keep for each image (0: none)
POOL_DEFAULT = 2  # one for the agent's box and one for the replay's
VCPUS_ENV = "PICKFIT_EC2_VCPUS"  # the vCPUs pickfit's own instances may hold in a region when a member is added
VCPUS_DEFAULT = 6  # two boxes and one member warming up: a new account's quota is 8, and not all of it is pickfit's
POOL_TAG = "pickfit:pool"  # the image a member was made from
CLAIM_TAG = "pickfit:claim"  # the box that took it; a member with one is nobody else's
POOL_KEEP_S = 7 * 24 * 3600  # a member nobody took in this long is reaped
WARM_LIFETIME_S = 20 * 60  # a member that is still up this long after its launch stops anyway
CLAIM_SETTLE_S = 2.0  # between writing a claim and reading it back, so that of two harnesses one sees the other
WARM_BOOT_WAIT_S = 100  # a claimed member answers in about 30 s; one that does not is replaced by a new instance

# The cost allocation tags (docs/proposals/machines-cost.md, M1): every instance says which run it is for and why
# it exists (agent, replay, confirm, limits, bake, warmup, web). AWS's bill groups by them once the account's owner
# activates them as cost allocation tags; scripts/box_reconcile.py reads Cost Explorer's answer grouped by purpose.
RUN_TAG = "pickfit:run_id"
PURPOSE_TAG = "pickfit:purpose"
MIN_BILLED_S = 60  # EC2 bills an instance for a minute at least, then by the second

# The lane limit: at most MAX_BOXES EC2 machines of pickfit's (boxes, AMI builders) at once in a region from this
# host. The account's quota is 8 vCPUs (ap-east-2, 11/17: not raised); two 2-vCPU boxes and one warming pool member
# fit it (VCPUS_DEFAULT), a third box does not. A machine takes a slot before it is launched and gives it back when
# it is destroyed; the slot is an exclusive lock on a file (SLOTS_DIR_ENV, else beside the ledger), so threads and
# processes on this host share the limit and a process that dies gives its slots back. A start with no free slot
# waits up to SLOT_WAIT_S. reserve(wait=False) takes one only if it is free now: the replay box a Windows run starts
# early (early_box) never makes a box that is already started wait. Pool members are not counted here: VCPUS_ENV
# keeps them out of the boxes' room.
MAX_BOXES = 2
MAX_BOXES_ENV = "PICKFIT_EC2_MAX_BOXES"  # may lower the limit, never raise it
SLOTS_DIR_ENV = "PICKFIT_SLOTS_DIR"
SLOT_WAIT_ENV = "PICKFIT_EC2_SLOT_WAIT_S"
SLOT_WAIT_S = 2 * 3600  # longer than a box's lifetime: the machines holding the slots end by then
SLOT_POLL_S = 5

# Root on a fresh Debian: Docker (Debian 13 ships the client apart, as docker-cli) and nftables, no bridge (the
# box uses the VM's own network; builds too), no apt timers competing with a box for CPU, room for the harness's
# parallel commands on one connection, and no vsock modules (the initramfs is rebuilt so it holds the rule too).
# Two things for the boot's speed, both measured 2026-11-16. cloud-init asks only the IPv4 metadata address: with
# its default list it waited 7.6 s of every boot on the IPv6 one, which these instances do not have. And a unit
# reads the container runtime's programs early in the boot: on a new volume dockerd took 23 s to start and
# containerd 10 s, nearly all of it their own files arriving from the snapshot a page at a time.
HOST_SETUP = r"""set -eu
export DEBIAN_FRONTEND=noninteractive
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service 2>/dev/null || true
apt-get -o DPkg::Lock::Timeout=180 update
apt-get -o DPkg::Lock::Timeout=180 install -y --no-install-recommends docker.io docker-cli nftables tini iptables ca-certificates
install -d -m 0755 /etc/docker
printf '%s\n' '{"bridge": "none", "iptables": false, "ip6tables": false}' > /etc/docker/daemon.json
printf '%s\n' 'MaxSessions 64' 'MaxStartups 64:30:128' 'PasswordAuthentication no' \
  'KbdInteractiveAuthentication no' 'AllowUsers root' > /etc/ssh/sshd_config.d/60-pickfit.conf
printf '%s\n' nf_tables > /etc/modules-load.d/pickfit.conf
printf '%s\n' @NO_VSOCK@ > /etc/modprobe.d/pickfit-no-vsock.conf
update-initramfs -u
printf '%s\n' 'datasource:' '  Ec2:' '    metadata_urls: ["http://169.254.169.254"]' '    timeout: 5' \
  '    max_wait: 30' > /etc/cloud/cloud.cfg.d/99-pickfit.cfg
for b in dockerd containerd containerd-shim-runc-v2 runc docker; do command -v "$b"; done > /etc/pickfit-readahead
printf '%s\n' '[Unit]' 'Description=pickfit: read the container runtime before it is started' \
  'DefaultDependencies=no' 'After=local-fs.target' '[Service]' 'Type=simple' \
  'ExecStart=/usr/bin/xargs -a /etc/pickfit-readahead /usr/bin/cat' 'StandardOutput=null' '[Install]' \
  'WantedBy=sysinit.target' > /etc/systemd/system/pickfit-readahead.service
systemctl enable pickfit-readahead.service
systemctl enable docker
systemctl restart docker
docker info --format 'docker {{.ServerVersion}} cgroup v{{.CgroupVersion}} init {{.InitBinary}}'
""".replace("@NO_VSOCK@", " ".join(shlex.quote(line) for line in NO_VSOCK_MODULES))
# The last command over SSH: nothing of the builder's boot may be in the image (its keys, cloud-init's record
# of having run). An empty machine-id is made anew at each boot without systemd's first-boot handling.
HOST_SEAL = r"""set -eu
apt-get clean
rm -rf /var/lib/apt/lists/*
cloud-init clean --logs
rm -f /etc/ssh/ssh_host_* /root/.ssh/authorized_keys
truncate -s 0 /etc/machine-id
sync
"""
# As root on the VM: does a new connection to the internet open? One "open" per address that answers.
EGRESS_PROBE = ('for a in 1.1.1.1 8.8.8.8; do (/usr/bin/timeout 2 /usr/bin/bash -c "echo > /dev/tcp/$a/443" '
                "2>/dev/null && echo open) & done; wait")
# As root on the VM: the status line of an IMDSv2 token request (200 while the service is on).
IMDS_PROBE = ("exec 3<>/dev/tcp/169.254.169.254/80 && printf 'PUT /latest/api/token HTTP/1.0\\r\\n"
              "X-aws-ec2-metadata-token-ttl-seconds: 60\\r\\n\\r\\n' >&3 && /usr/bin/head -c 12 <&3")
_sleep = time.sleep
_now = time.monotonic


def _code(error: Exception) -> str:
    """An AWS error's code, e.g. InvalidGroup.Duplicate ('' for anything else)."""
    return str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))


def region_name() -> str:
    return os.environ.get(REGION_ENV) or DEFAULT_REGION


def ec2_client(region: str | None = None) -> Any:
    import boto3

    return boto3.client("ec2", region_name=region or region_name())


def control_cidr() -> str:
    """The address the harness reaches instances from, as a /32: CONTROL_CIDR_ENV, or this host's public one."""
    given = os.environ.get(CONTROL_CIDR_ENV)
    if given:
        return str(ipaddress.ip_network(given, strict=False))
    try:
        with urllib.request.urlopen(MY_ADDRESS_URL, timeout=10) as reply:  # noqa: S310 (a fixed https URL)
            return f"{ipaddress.ip_address(reply.read().decode().strip())}/32"
    except (OSError, ValueError) as error:
        raise BoxError(f"cannot learn this host's public address ({error}); set {CONTROL_CIDR_ENV}") from error


def hourly_usd(name: str, region: str, platform: str = "linux") -> float | None:
    """USD an hour for that type on demand, or None when there is no price on file."""
    index = next((i for i, size in enumerate(INSTANCE_SIZES) if size[0] == name), None)
    prices = PRICES.get(region, {}).get(platform)
    return None if index is None or prices is None else prices[index]


def pick_type(cores: float, memory_mb: int, region: str = PRICE_REGION, platform: str = "linux",
              reserve_mb: int = HOST_RESERVE_MB) -> tuple[str, float]:
    """(instance type, USD an hour): the cheapest listed type that holds the box and the host under it."""
    priced = sorted(((hourly_usd(name, region, platform) or hourly_usd(name, PRICE_REGION, platform) or 0.0,
                      name, vcpus, mib) for name, vcpus, mib in INSTANCE_SIZES))
    for usd, name, vcpus, mib in priced:
        if vcpus >= math.ceil(cores) and mib >= memory_mb + reserve_mb:
            return name, usd
    raise ValueError(f"no listed EC2 type holds {cores:g} CPUs and {memory_mb} MiB (largest: {INSTANCE_SIZES[-1][0]})")


def pool_size() -> int:
    given = os.environ.get(POOL_ENV, "")
    return max(0, int(given)) if given.strip().isdigit() else POOL_DEFAULT


def vcpu_budget() -> int:
    given = os.environ.get(VCPUS_ENV, "")
    return max(0, int(given)) if given.strip().isdigit() else VCPUS_DEFAULT


def max_boxes() -> int:
    """MAX_BOXES, or less when MAX_BOXES_ENV says so (at least one)."""
    given = os.environ.get(MAX_BOXES_ENV, "").strip()
    return max(1, min(MAX_BOXES, int(given))) if given.isdigit() else MAX_BOXES


def slots_dir() -> Path:
    """Where the slot files are: SLOTS_DIR_ENV, else a `slots` directory beside the shared ledger."""
    given = os.environ.get(SLOTS_DIR_ENV, "").strip()
    if given:
        return Path(given)
    from pickfit.ledger import DEFAULT_PATH

    return Path(get_env("PICKFIT_LEDGER") or DEFAULT_PATH).parent / "slots"


def slot_wait_s() -> float:
    given = os.environ.get(SLOT_WAIT_ENV, "").strip()
    try:
        return max(0.0, float(given)) if given else SLOT_WAIT_S
    except ValueError:
        return SLOT_WAIT_S


class Slot:
    """One of a region's max_boxes() places, held as an exclusive lock on its file until release(). A timer gives it
    back when the machine holding it must be gone (its lifetime is over), should nobody release it."""

    def __init__(self, path: Path, fd: int) -> None:
        self.path, self.fd = path, fd
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    @property
    def held(self) -> bool:
        return self.fd >= 0

    def expire_after(self, seconds: float) -> None:
        """Release the slot after `seconds` unless it is released before (a later call replaces an earlier one)."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            if self.fd < 0:
                return
            self._timer = threading.Timer(seconds, self.release)
            self._timer.daemon = True
            self._timer.start()

    def release(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self.fd < 0:
                return
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = -1


def take_slot(region: str, *, wait_s: float = 0.0, log: Callable[[str], None] = print) -> Slot | None:
    """A free slot of the region's max_boxes(), waiting up to wait_s for one; None when none came free."""
    folder = slots_dir()
    folder.mkdir(parents=True, exist_ok=True)
    deadline = _now() + wait_s
    said = False
    while True:
        for index in range(max_boxes()):
            path = folder / f"ec2-{region}-{index}.lock"
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                continue
            return Slot(path, fd)
        if _now() >= deadline:
            return None
        if not said:
            log(f"ec2: {max_boxes()} machines already run in {region}; waiting for one to end (the lane's limit)")
            said = True
        _sleep(min(SLOT_POLL_S, max(0.1, deadline - _now())))


def _vcpus(instance: dict[str, Any]) -> int:
    """The vCPUs an instance holds while it runs, by its type (2 for one not in INSTANCE_SIZES)."""
    return next((vcpus for name, vcpus, _ in INSTANCE_SIZES if name == instance.get("InstanceType")), 2)


def _tag(instance: dict[str, Any], key: str) -> str | None:
    return next((t["Value"] for t in instance.get("Tags", []) if t["Key"] == key), None)


def disk_gb(recipe: ImageRecipe) -> int:
    return DISK_GB + sum(DISK_GB_EXTRA.get(kind, 0) for kind in recipe.kinds)


@dataclass(frozen=True)
class ContainerImage:
    """The image a machine's container runs, for one that is not a box's: its name inside the AMI (which must
    change when the Dockerfile does: the AMI is named after it), the Dockerfile, and the disk it needs."""

    tag: str
    dockerfile: str
    disk_gb: int = DISK_GB


def box_image(recipe: ImageRecipe) -> ContainerImage:
    """A box's image: sandbox.Dockerfile plus the recipe of its kind."""
    return ContainerImage(image_names(recipe)[0], dockerfile(recipe), disk_gb(recipe))


def ami_name(tag: str) -> str:
    """The AMI that holds a container image: the image's tag and a hash of the host under it."""
    host = hashlib.sha256((BASE_AMI_NAME + HOST_SETUP + HOST_SEAL).encode()).hexdigest()[:8]
    return f"{tag.replace(':', '-')}-host-{host}"


def image_names(recipe: ImageRecipe) -> tuple[str, str]:
    """(the sandbox image's tag inside the AMI, the AMI's name)."""
    tag = recipe.tag(sandbox_image_tag())
    return tag, ami_name(tag)


def dockerfile(recipe: ImageRecipe) -> str:
    """sandbox.Dockerfile plus the recipe, as Modal's builder applies it (apt_install, then run_commands)."""
    text = SANDBOX_DOCKERFILE.read_text(encoding="utf-8").rstrip("\n") + "\n"
    if recipe.packages:
        install = f"apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y {' '.join(recipe.packages)}"
        text += f"RUN {json.dumps(['/bin/sh', '-c', install])}\n"
    for command in recipe.commands:
        text += f"RUN {json.dumps(['/bin/sh', '-c', command])}\n"
    return text


def _tags(resource: str, tags: dict[str, str]) -> dict[str, Any]:
    return {"ResourceType": resource, "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}


# -- security groups


def _rules(permissions: list[dict[str, Any]]) -> set[tuple[str, Any, Any, str]]:
    """Security group permissions as (protocol, from port, to port, source or destination)."""
    rules = set()
    for p in permissions:
        ends = ([r["CidrIp"] for r in p.get("IpRanges", [])] + [r["CidrIpv6"] for r in p.get("Ipv6Ranges", [])]
                + [f"group {g.get('GroupId')}" for g in p.get("UserIdGroupPairs", [])]
                + [f"list {g.get('PrefixListId')}" for g in p.get("PrefixListIds", [])])
        rules |= {(str(p.get("IpProtocol")), p.get("FromPort"), p.get("ToPort"), end) for end in ends}
    return rules


def _check_groups(groups: dict[str, dict[str, Any]]) -> None:
    """The three groups are exactly what pickfit makes; BoxError names the one that is not."""
    online = {("-1", None, None, cidr) for cidr in ONLINE_CIDRS}
    want = {"online": (set(), online), "offline": (set(), set()), "control": (None, set())}
    for role, (ingress, egress) in want.items():
        group = groups[role]
        got_in, got_out = _rules(group.get("IpPermissions", [])), _rules(group.get("IpPermissionsEgress", []))
        ssh_only = all(rule[:3] == ("tcp", 22, 22) and "." in rule[3] and not rule[3].endswith("/0") for rule in got_in)
        if got_out != egress or (ingress is not None and got_in != ingress) or (ingress is None and not ssh_only):
            raise BoxError(f"security group {GROUPS[role]} ({group['GroupId']}) is not as pickfit makes it; delete it "
                           "(pickfit makes it again) or restore its rules")


def ensure_groups(ec2: Any, control: str) -> dict[str, str]:
    """{control, online, offline: group id} in the default VPC, made if missing, checked every time, with the
    harness's address allowed in on the control group."""
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise BoxError("this AWS region has no default VPC; pickfit launches its boxes there")
    vpc = vpcs[0]["VpcId"]

    def described() -> dict[str, dict[str, Any]]:
        found = ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc]},
                                                      {"Name": "group-name", "Values": list(GROUPS.values())}])
        by_name = {g["GroupName"]: g for g in found["SecurityGroups"]}
        return {role: by_name[name] for role, name in GROUPS.items() if name in by_name}

    have = described()
    for role, name in GROUPS.items():
        if role in have:
            continue
        try:
            made = ec2.create_security_group(GroupName=name, Description=GROUP_NOTES[role], VpcId=vpc,
                                             TagSpecifications=[_tags("security-group", {"pickfit": "verify"})])
        except Exception as error:
            if _code(error) != "InvalidGroup.Duplicate":  # another harness made it just now
                raise
            continue
        # A new group allows everything out; a box must never wear it like that.
        ec2.revoke_security_group_egress(GroupId=made["GroupId"], IpPermissions=[
            {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}])
        if role == "online":
            ec2.authorize_security_group_egress(GroupId=made["GroupId"], IpPermissions=[
                {"IpProtocol": "-1", "IpRanges": [{"CidrIp": cidr} for cidr in ONLINE_CIDRS]}])
    have = described()
    missing = [GROUPS[role] for role in GROUPS if role not in have]
    if missing:
        raise BoxError(f"security groups missing after making them: {missing}")
    _check_groups(have)
    if ("tcp", 22, 22, control) not in _rules(have["control"].get("IpPermissions", [])):
        try:
            ec2.authorize_security_group_ingress(GroupId=have["control"]["GroupId"], IpPermissions=[
                {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                 "IpRanges": [{"CidrIp": control,
                               "Description": f"{HARNESS_RULE}{time.strftime('%Y-%m-%d')}"}]}])
        except Exception as error:
            if _code(error) != "InvalidPermission.Duplicate":
                raise
    stale = _stale_harness_rules(have["control"], control, datetime.date.today())
    if stale:  # addresses the harness had a while ago; each rule left is a place SSH is answered from
        try:
            ec2.revoke_security_group_ingress(GroupId=have["control"]["GroupId"], IpPermissions=[
                {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": cidr} for cidr in stale]}])
        except Exception:  # another harness removed them just now, or may not: the rules are only old, not wrong
            pass
    return {role: group["GroupId"] for role, group in have.items()}


def _stale_harness_rules(group: dict[str, Any], keep: str, today: datetime.date) -> list[str]:
    """The control group's own SSH rules, by their description, that are HARNESS_RULE_DAYS old and not `keep`."""
    stale = []
    for permission in group.get("IpPermissions", []):
        for allowed in permission.get("IpRanges", []):
            note = str(allowed.get("Description", ""))
            if allowed.get("CidrIp") == keep or not note.startswith(HARNESS_RULE):
                continue
            try:
                added = datetime.date.fromisoformat(note[len(HARNESS_RULE):])
            except ValueError:
                continue
            if (today - added).days >= HARNESS_RULE_DAYS:
                stale.append(allowed["CidrIp"])
    return stale


# -- instances


def reap(ec2: Any, log: Callable[[str], None] = print, now: float | None = None) -> list[str]:
    """Terminate pickfit instances past their lifetime (the poweroff they schedule should have); their ids."""
    now = time.time() if now is None else now
    found = ec2.describe_instances(Filters=[{"Name": "tag-key", "Values": [EXPIRES_TAG]},
                                            {"Name": "instance-state-name", "Values": LIVE_STATES}])
    late = []
    for instance in (i for r in found.get("Reservations", []) for i in r.get("Instances", [])):
        expires = next((t["Value"] for t in instance.get("Tags", []) if t["Key"] == EXPIRES_TAG), "")
        if expires.isdigit() and int(expires) + REAP_MARGIN_S < now:
            late.append(instance["InstanceId"])
    if late:
        ec2.terminate_instances(InstanceIds=late)
        log(f"ec2: terminated {len(late)} instance(s) past their lifetime: {' '.join(late)}")
    return late


def _wait(what: str, done: Callable[[], bool], timeout_s: float, every_s: float = 2) -> None:
    deadline = _now() + timeout_s
    while not done():
        if _now() > deadline:
            raise BoxError(f"{what} did not happen in {timeout_s:.0f}s")
        _sleep(every_s)


def _instance(ec2: Any, instance_id: str) -> dict[str, Any]:
    """The instance as EC2 describes it now ({} in the moment after launch when it is not yet listed)."""
    try:
        found = ec2.describe_instances(InstanceIds=[instance_id])
    except Exception as error:
        if _code(error) != "InvalidInstanceID.NotFound":
            raise
        return {}
    return next((i for r in found.get("Reservations", []) for i in r.get("Instances", [])), {})


def find_image(ec2: Any, name: str) -> dict[str, Any] | None:
    """This account's AMI of that name, once it can be launched; None if there is none (or it failed)."""
    images = ec2.describe_images(Owners=["self"], Filters=[{"Name": "name", "Values": [name]}])["Images"]
    pending = [i for i in images if i.get("State") == "pending"]
    if pending:  # another harness is baking it
        _wait(f"AMI {name} becoming available",
              lambda: ec2.describe_images(ImageIds=[pending[0]["ImageId"]])["Images"][0].get("State") != "pending",
              30 * 60, 10)
        images = ec2.describe_images(Owners=["self"], Filters=[{"Name": "name", "Values": [name]}])["Images"]
    return next((i for i in images if i.get("State") == "available"), None)


def base_image(ec2: Any) -> dict[str, Any]:
    """The newest Debian AMI that BASE_AMI_NAME matches."""
    images = ec2.describe_images(Owners=[BASE_AMI_OWNER], Filters=[
        {"Name": "name", "Values": [BASE_AMI_NAME]}, {"Name": "state", "Values": ["available"]},
        {"Name": "architecture", "Values": ["x86_64"]}])["Images"]
    if not images:
        raise BoxError(f"no AMI named {BASE_AMI_NAME} from Debian's account in this region")
    return max(images, key=lambda i: i["CreationDate"])


class Ec2Instance:
    """What every pickfit instance on EC2 is, whatever runs on it: launched from pickfit's image behind pickfit's
    security groups, with no AWS identity, ended by its own poweroff. Mixed into the class that reaches the
    instance (SshMachine for the Linux box's host; ec2_windows.Ec2WinMachine for a Windows box), which gives the
    hooks at the end of this class.

    With a pool (POOL_ENV), _create first takes a stopped member: an instance of the same image that booted once
    with nobody's keys and no way in or out, read its disk and stopped. It is started with this machine's user
    data, so it boots into this machine's keys as a new instance would, in a third of the time. Each start then
    launches the pool's replacements."""

    provider = "ec2"
    platform = "linux"  # the price table's key
    lane = "linux"  # the ledger's (a web box sets "web")
    purpose: str | None = None  # the ledger's and PURPOSE_TAG's, when the tags name no role
    boot_wait_s: float = 240
    warm_boot_wait_s: float = WARM_BOOT_WAIT_S
    warm_lifetime_s: int = WARM_LIFETIME_S

    def _init_ec2(self, *, tags: dict[str, str] | None, region: str | None, ec2: Any, instance_type: str | None,
                  usd_per_hour: float | None, control: str | None, boot_image: dict[str, Any] | None,
                  role: str) -> None:
        self.slot: Slot | None = None  # this machine's place among the region's max_boxes()
        self.meter: BoxMeter | None = None
        self.tags = dict(tags or {})
        self.region = region or region_name()
        self.ec2 = ec2
        self.instance_type = instance_type
        self.usd_per_hour = usd_per_hour
        self.control = control
        self.boot_image = boot_image  # a builder boots the vendor's own AMI instead of pickfit's
        self.role = role
        self.groups: dict[str, str] = {}
        self.metadata_answer: str | None = None  # what the metadata service said once it was turned off
        self.warm = False  # this machine is a pool member, not a new instance
        self._crowded = False  # this start was refused by the vCPU quota at least once
        self._quota_deadline = 0.0
        self._made_room_at = float("-inf")
        self._image: str | None = None
        self._user_data = ""

    @property
    def image(self) -> str:
        """The AMI the instance started from; before it starts, the one it would start from now."""
        return self._image or self.image_name  # type: ignore[attr-defined]

    def _size(self) -> tuple[float, int]:
        """(vCPUs, MiB) the instance needs: the box, and what runs next to it on the instance."""
        return self.cores, self.memory_mb + HOST_RESERVE_MB  # type: ignore[attr-defined]

    def _price(self) -> tuple[str, float]:
        """(instance type, USD an hour for it), following the box's size as it is now."""
        name = self.instance_type
        if name is None:
            cores, mib = self._size()
            name = pick_type(cores, mib, self.region, self.platform, reserve_mb=0)[0]
        if self.usd_per_hour is not None:
            return name, self.usd_per_hour
        usd = hourly_usd(name, self.region, self.platform)
        if usd is None:
            raise ValueError(f"no price on file for {name} in {self.region}; pass usd_per_hour")
        return name, usd

    def usd_per_second(self) -> float:
        """The instance, its public address and its disk. EC2 bills an instance at least 60 seconds."""
        per_gb = PRICES.get(self.region, PRICES[PRICE_REGION])["disk"]
        return (self._price()[1] + IPV4_USD_PER_HOUR + self._disk_gb() * per_gb / HOURS_PER_MONTH) / 3600

    def _purpose(self) -> str:
        """Why the machine exists, for the ledger and PURPOSE_TAG: the role its tags name (agent, replay, ...), else
        what the machine itself is (an AMI's builder, a web box)."""
        return self.purpose or identity(self.tags)[1] or {"bake": "bake", "web": "web"}.get(self.role, "box")

    def _box_tags(self, now: float) -> dict[str, str]:
        run_id = identity(self.tags)[0]
        return {"Name": f"pickfit-{self.role}", "pickfit": "verify", "pickfit:role": self.role,
                EXPIRES_TAG: str(int(now + self.lifetime_s)), PURPOSE_TAG: self._purpose(),  # type: ignore[attr-defined]
                **({RUN_TAG: run_id[:256]} if run_id else {}), **self.tags}

    # -- the lane limit (MAX_BOXES) and the ledger's rows

    def reserve(self, wait: bool = False) -> bool:
        """Take one of the region's max_boxes() slots for this machine: now or not at all, or (wait) up to
        slot_wait_s(). True when the machine holds one."""
        if self.slot is not None and self.slot.held:
            return True
        self.slot = take_slot(self.region, wait_s=slot_wait_s() if wait else 0.0, log=self.log)  # type: ignore[attr-defined]
        if self.slot is not None:  # never held past the latest a machine started now can be up
            self.slot.expire_after(self.lifetime_s + QUOTA_WAIT_S + 2 * REAP_MARGIN_S)  # type: ignore[attr-defined]
        return self.slot is not None

    def release_slot(self) -> None:
        if self.slot is not None:
            self.slot.release()
            self.slot = None

    def _open_meter(self) -> None:
        try:
            name, _ = self._price()
            size = next(((vcpus, mib) for n, vcpus, mib in INSTANCE_SIZES if n == name), (None, None))
            source = (f"a price given for {name}" if self.usd_per_hour is not None else
                      f"AWS on-demand {name} ({self.platform}) in {self.region}, price list read {PRICES_READ}")
            self.meter = BoxMeter(
                "ec2", lane=self.lane, purpose=self._purpose(), run_id=identity(self.tags)[0], vcpu=size[0],
                memory_gb=size[1] / 1024 if size[1] else None, usd_per_hour=round(self.usd_per_second() * 3600, 6),
                rate_source=f"{source}; with a public IPv4 and {self._disk_gb()} GB gp3",
                lifetime_s=int(self.lifetime_s), min_billed_s=MIN_BILLED_S, log=self.log)  # type: ignore[attr-defined]
        except Exception as error:  # never the reason a box does not start
            self.log(f"box ledger: no row for {self.machine_id} ({type(error).__name__}: {error})")  # type: ignore[attr-defined]
            return
        self.meter.start(self.machine_id)  # type: ignore[attr-defined]

    def _close_meter(self) -> None:
        if self.meter is not None:
            self.meter.end()
            self.meter = None

    def _meter_warm(self, launched: Any, image: dict[str, Any]) -> None:
        """A pool member's row: it boots once and stops itself (warm_lifetime_s at the latest), so the row is left
        open and the next start closes it at that lifetime, an upper bound."""
        try:
            iid = launched["Instances"][0]["InstanceId"]
            name, usd = pick_type(*self._pool_size(), self.region, self.platform, reserve_mb=0)
            size = next(((vcpus, mib) for n, vcpus, mib in INSTANCE_SIZES if n == name), (None, None))
            disk = PRICES.get(self.region, PRICES[PRICE_REGION])["disk"] * self._disk_gb() / HOURS_PER_MONTH
            meter = BoxMeter(
                "ec2", lane=self.lane, purpose="warmup", vcpu=size[0], memory_gb=size[1] / 1024 if size[1] else None,
                usd_per_hour=round(usd + IPV4_USD_PER_HOUR + disk, 6),
                rate_source=f"AWS on-demand {name} ({self.platform}) in {self.region}, price list read {PRICES_READ}; "
                            f"a pool member of {image.get('Name') or image.get('ImageId')} warming up; its stopped "
                            "disk afterwards is not counted",
                lifetime_s=self.warm_lifetime_s, min_billed_s=MIN_BILLED_S, log=self.log)  # type: ignore[attr-defined]
        except Exception as error:  # never the reason the pool is not refilled
            self.log(f"box ledger: no row for a pool member ({type(error).__name__}: {error})")  # type: ignore[attr-defined]
            return
        meter.start(iid)

    def close(self) -> None:
        """Destroy the machine (the class that reaches it does), then close its row and give back its slot."""
        try:
            super().close()  # type: ignore[misc]
        finally:
            self._close_meter()
            self.release_slot()

    def run_kwargs(self, image: dict[str, Any], user_data: str, now: float) -> dict[str, Any]:
        """RunInstances arguments (separate so tests can check them)."""
        tags = self._box_tags(now)
        return {
            "ImageId": image["ImageId"], "InstanceType": self._price()[0], "MinCount": 1, "MaxCount": 1,
            "SecurityGroupIds": [self.groups["control"], self.groups["online"]], "UserData": user_data,
            "InstanceInitiatedShutdownBehavior": "terminate",
            # On for the boot only (the image's boot agent reads the keys); _seal turns it off. Tokens and one hop
            # meanwhile.
            "MetadataOptions": {"HttpEndpoint": "enabled", "HttpTokens": "required", "HttpPutResponseHopLimit": 1,
                                "HttpProtocolIpv6": "disabled", "InstanceMetadataTags": "disabled"},
            "BlockDeviceMappings": [{"DeviceName": image.get("RootDeviceName", "/dev/xvda"), "Ebs": {
                "VolumeSize": self._disk_gb(), "VolumeType": "gp3", "DeleteOnTermination": True}}],
            "TagSpecifications": [_tags("instance", tags), _tags("volume", tags)],
        }

    def warm_kwargs(self, image: dict[str, Any], now: float) -> dict[str, Any]:
        """RunInstances arguments for a pool member: the same instance with nobody's keys, no way in or out (the
        offline group alone), and a poweroff that stops it instead of ending it."""
        name = image.get("Name") or image["ImageId"]
        tags = {"Name": "pickfit-pool", "pickfit": "verify", "pickfit:role": "pool", POOL_TAG: name,
                EXPIRES_TAG: str(int(now + POOL_KEEP_S)), PURPOSE_TAG: "warmup"}
        return {**self.run_kwargs(image, self._warm_user_data(), now),
                "InstanceType": pick_type(*self._pool_size(), self.region, self.platform, reserve_mb=0)[0],
                "SecurityGroupIds": [self.groups["offline"]], "InstanceInitiatedShutdownBehavior": "stop",
                "TagSpecifications": [_tags("instance", tags), _tags("volume", tags)]}

    def _pool_size(self) -> tuple[float, int]:
        """(vCPUs, MiB) of a pool member while it warms up; a claim changes the type to the box's."""
        return 2, 4096

    def _wait_running(self) -> dict[str, Any]:
        state: dict[str, Any] = {}

        def running() -> bool:
            state.update(_instance(self.ec2, self.machine_id))  # type: ignore[attr-defined]
            name = state.get("State", {}).get("Name")
            if name in ("shutting-down", "terminated", "stopping", "stopped"):
                reason = state.get("StateReason", {}).get("Message", "")
                raise BoxError(f"EC2 instance {self.machine_id} went {name} while starting: {reason}")  # type: ignore[attr-defined]
            return name == "running" and bool(state.get("PublicIpAddress"))

        _wait(f"EC2 instance {self.machine_id} running with a public address", running, 180)  # type: ignore[attr-defined]
        return state

    def _holding(self) -> list[dict[str, Any]]:
        """pickfit's instances in this region that hold vCPUs now (pending or running), the newest first."""
        found = self.ec2.describe_instances(Filters=[{"Name": "tag:pickfit", "Values": ["verify"]},
                                                     {"Name": "instance-state-name", "Values": ["pending", "running"]}])
        live = [i for r in found.get("Reservations", []) for i in r.get("Instances", [])
                if i.get("State", {}).get("Name") in ("pending", "running") and _tag(i, "pickfit") == "verify"]
        return sorted(live, key=lambda i: str(i.get("LaunchTime", "")), reverse=True)

    def _make_room(self) -> bool:
        """End the newest pool member that is still warming up, so that a box can start: a member is a shortcut
        for a later start, and this start is now. False when none is warming."""
        try:
            warming = [i for i in self._holding() if _tag(i, POOL_TAG) and _tag(i, CLAIM_TAG) is None]
            if not warming:
                return False
            self.ec2.terminate_instances(InstanceIds=[warming[0]["InstanceId"]])
        except Exception as error:
            self.log(f"ec2 pool: no room made ({_code(error) or type(error).__name__})")  # type: ignore[attr-defined]
            return False
        self.log(f"ec2 pool: ended {warming[0]['InstanceId']}, which was warming up, to make room for this box")  # type: ignore[attr-defined]
        return True

    def _when_room(self, call: Callable[[], Any]) -> Any:
        """An EC2 call that needs vCPUs (RunInstances, StartInstances). When the account's quota refuses it, a
        warming pool member is ended for it and it is tried again; with none to end, other boxes hold the quota
        and it is tried every 15 s until QUOTA_WAIT_S after this start began."""
        while True:
            try:
                return call()
            except Exception as error:
                if _code(error) != "VcpuLimitExceeded" or _now() >= self._quota_deadline:
                    raise
                self._crowded = True
                if _now() - self._made_room_at >= EVICT_SETTLE_S and self._make_room():
                    self._made_room_at = _now()
                _sleep(5 if _now() - self._made_room_at < EVICT_SETTLE_S else 15)

    def _begin_start(self) -> None:
        self._crowded, self._quota_deadline, self._made_room_at = False, _now() + QUOTA_WAIT_S, float("-inf")

    def _launch(self, image: dict[str, Any], user_data: str) -> None:
        """A new instance (see _when_room for a launch the vCPU quota refuses)."""
        try:
            launched = self._when_room(
                lambda: self.ec2.run_instances(**self.run_kwargs(image, user_data, time.time())))
        except Exception as error:
            raise BoxError(f"EC2 RunInstances failed: {_code(error) or type(error).__name__}: {error}") from error
        self.machine_id = launched["Instances"][0]["InstanceId"]
        self.warm, self.boot_wait_s = False, type(self).boot_wait_s

    def _claim(self, image: dict[str, Any], user_data: str) -> bool:
        """Start a stopped pool member as this machine; False when there is none to take. The claim is a tag
        written, then read back after a moment: of two harnesses that pick the same member, the one whose tag was
        overwritten sees the other's and moves on. Should both go on anyway, the member boots with one's keys and
        the other's connection is refused by the pinned host key; _recreate then gives that one a new instance."""
        name = image.get("Name") or image["ImageId"]
        found = self.ec2.describe_instances(Filters=[{"Name": f"tag:{POOL_TAG}", "Values": [name]},
                                                     {"Name": "instance-state-name", "Values": ["stopped"]}])
        members = [i for r in found.get("Reservations", []) for i in r.get("Instances", [])
                   if i.get("State", {}).get("Name") == "stopped" and _tag(i, POOL_TAG) == name
                   and _tag(i, CLAIM_TAG) is None]
        for member in sorted(members, key=lambda i: str(i.get("LaunchTime", ""))):
            iid, nonce = member["InstanceId"], secrets.token_hex(8)
            try:
                # The claim and the box's own tags in one call: a member that carries a claim is a box (reap()
                # goes by the lifetime written here), whoever wins it.
                self.ec2.create_tags(Resources=[iid], Tags=[{"Key": k, "Value": v} for k, v in {
                    **self._box_tags(time.time()), CLAIM_TAG: nonce}.items()])
                _sleep(CLAIM_SETTLE_S)
                now = _instance(self.ec2, iid)
                if _tag(now, CLAIM_TAG) != nonce or now.get("State", {}).get("Name") != "stopped":
                    continue
                wanted = self._price()[0]
                changes: list[dict[str, Any]] = [
                    {"UserData": {"Value": user_data.encode()}},
                    {"InstanceInitiatedShutdownBehavior": {"Value": "terminate"}},
                    {"Groups": [self.groups["control"], self.groups["online"]]}]
                if now.get("InstanceType") not in (None, wanted):
                    changes.append({"InstanceType": {"Value": wanted}})
                with ThreadPoolExecutor(len(changes)) as pool:  # one attribute a call; none depends on another
                    for done in [pool.submit(self.ec2.modify_instance_attribute, InstanceId=iid, **change)
                                 for change in changes]:
                        done.result()
                self._when_room(lambda iid=iid: self.ec2.start_instances(InstanceIds=[iid]))
            except Exception as error:  # taken by another harness, or EC2 refused: a tagged member is reaped later
                self.log(f"ec2 pool: {iid} not taken ({_code(error) or type(error).__name__}); trying the next")  # type: ignore[attr-defined]
                continue
            self.machine_id = iid
            self.warm, self.boot_wait_s = True, self.warm_boot_wait_s
            return True
        return False

    def _refill(self, image: dict[str, Any]) -> None:
        """Launch pool members until the image has pool_size() of them, counting those still warming up, while
        pickfit's instances in the region stay within vcpu_budget(): members never take the room a box needs. A
        start that had to wait for the quota launches none. Never the reason a box does not start."""
        want = pool_size()
        if want <= 0:
            return
        if self._crowded:
            self.log("ec2 pool: no member added (this start waited for the account's vCPU quota)")  # type: ignore[attr-defined]
            return
        try:
            name = image.get("Name") or image["ImageId"]
            found = self.ec2.describe_instances(Filters=[{"Name": "tag:pickfit", "Values": ["verify"]},
                                                         {"Name": "instance-state-name", "Values": LIVE_STATES}])
            live = [i for r in found.get("Reservations", []) for i in r.get("Instances", [])
                    if _tag(i, "pickfit") == "verify" and i.get("State", {}).get("Name") in LIVE_STATES]
            spare = [i for i in live if _tag(i, POOL_TAG) == name and _tag(i, CLAIM_TAG) is None]
            held = sum(_vcpus(i) for i in live if i.get("State", {}).get("Name") in ("pending", "running"))
            kwargs = self.warm_kwargs(image, time.time())
            member = _vcpus(kwargs)
            for _ in range(want - len(spare)):
                if held + member > vcpu_budget():
                    self.log(f"ec2 pool: {len(spare)} of {want} members for {name}; pickfit holds {held} vCPUs "  # type: ignore[attr-defined]
                             f"({VCPUS_ENV}={vcpu_budget()}), so the next one waits for a later start")
                    break
                launched = self.ec2.run_instances(**self.warm_kwargs(image, time.time()))
                self._meter_warm(launched, image)
                held += member
                spare.append({})
        except Exception as error:
            if _code(error) == "VcpuLimitExceeded":  # an instance that just ended still counts for a moment
                self.log("ec2 pool: no member added (the account's vCPU quota is full right now)")  # type: ignore[attr-defined]
            else:
                self.log(f"ec2 pool: not refilled ({_code(error) or type(error).__name__}: {error})"[:300])  # type: ignore[attr-defined]

    def _create(self, user_data: str) -> str:
        self.ec2 = self.ec2 or ec2_client(self.region)
        self._begin_start()
        try:
            reap(self.ec2, self.log)  # type: ignore[attr-defined]
        except Exception as error:  # never the reason a box does not start
            self.log(f"ec2 reap: {type(error).__name__}: {error}")  # type: ignore[attr-defined]
        self.groups = ensure_groups(self.ec2, self.control or control_cidr())
        image = self.boot_image or self._ensure_image()  # a bake for it takes a slot of its own, so before this one's
        if not self.reserve(wait=True):
            raise BoxError(f"no room for another EC2 machine in {self.region}: {max_boxes()} of pickfit's ran for "
                           f"{slot_wait_s():.0f}s (the lane's limit, {MAX_BOXES_ENV})")
        assert self.slot is not None
        self._image = image.get("Name") or image["ImageId"]
        self._user_data, self._booted_image = user_data, image
        pooled = self.boot_image is None and pool_size() > 0
        claimed = False
        if pooled:
            try:
                claimed = self._claim(image, user_data)
            except Exception as error:  # the pool is a shortcut: without it the box starts as a new instance
                self.log(f"ec2 pool: not looked at ({_code(error) or type(error).__name__})")  # type: ignore[attr-defined]
        if not claimed:
            self._launch(image, user_data)
        # From the launch the machine's own poweroff ends it within its lifetime: the slot goes back by then anyway.
        self.slot.expire_after(self.lifetime_s + 2 * REAP_MARGIN_S)  # type: ignore[attr-defined]
        self._open_meter()
        if pooled:
            self._refill(image)
        return str(self._wait_running()["PublicIpAddress"])

    def prepare(self) -> dict[str, Any]:
        """The image and the pool for this kind of machine, without starting one (`pickfit verify --prepare-base`)."""
        self.ec2 = self.ec2 or ec2_client(self.region)
        self.groups = ensure_groups(self.ec2, self.control or control_cidr())
        image = self._ensure_image()
        self._refill(image)
        return image

    def _recreate(self) -> str | None:
        """A pool member that did not answer with this machine's keys is ended and a new instance takes its
        place; None when the machine already was a new instance."""
        if not self.warm:
            return None
        self.log(f"ec2 pool: {self.machine_id} did not answer as this machine; starting a new instance instead")  # type: ignore[attr-defined]
        self._destroy()
        self._close_meter()
        self._begin_start()
        self._launch(self._booted_image, self._user_data)  # in the slot the member had
        self._open_meter()
        return str(self._wait_running()["PublicIpAddress"])

    def _seal(self) -> None:
        self.ec2.modify_instance_metadata_options(InstanceId=self.machine_id, HttpEndpoint="disabled")  # type: ignore[attr-defined]
        answer = {"line": ""}

        def off() -> bool:
            answer["line"] = self._metadata_line()
            return " 200" not in answer["line"]

        _wait(f"turning off the metadata service of {self.machine_id}", off, 60, 1)  # type: ignore[attr-defined]
        self.metadata_answer = answer["line"] or "no answer"  # what a turned-off service says, for the record

    def _provider_egress(self, enabled: bool) -> None:
        wear = [self.groups["control"], self.groups["online" if enabled else "offline"]]
        try:
            self.ec2.modify_instance_attribute(InstanceId=self.machine_id, Groups=wear)  # type: ignore[attr-defined]
        except Exception as error:
            raise BoxError(f"EC2 security group change failed: {_code(error) or type(error).__name__}: {error}"
                           ) from error
        _wait(f"EC2 egress {'opening' if enabled else 'closing'} for {self.machine_id}",  # type: ignore[attr-defined]
              lambda: self._egress_open() == enabled, 45, 1)

    def _destroy(self) -> None:
        if self.machine_id is not None and self.ec2 is not None:  # type: ignore[attr-defined]
            self.ec2.terminate_instances(InstanceIds=[self.machine_id])  # type: ignore[attr-defined]

    # -- what the class that reaches the instance gives

    def _disk_gb(self) -> int:
        raise NotImplementedError

    def _ensure_image(self) -> dict[str, Any]:
        """pickfit's AMI for this machine, made if the account does not have it."""
        raise NotImplementedError

    def _warm_user_data(self) -> str:
        """The user data of a pool member's one boot: read the disk, forget the boot, power off."""
        raise NotImplementedError

    def _egress_open(self) -> bool:
        """As the machine's administrator: does a new connection to the internet open?"""
        raise NotImplementedError

    def _metadata_line(self) -> str:
        """As the machine's administrator: the status line of a metadata token request ('' for no answer)."""
        raise NotImplementedError


class Ec2Machine(Ec2Instance, SshMachine):
    """An EC2 instance from pickfit's Linux AMI, behind pickfit's security groups."""

    def __init__(self, *, cores: float, memory_mb: int, lifetime_s: int, recipe: ImageRecipe | None = None,
                 tags: dict[str, str] | None = None, region: str | None = None, ec2: Any = None,
                 instance_type: str | None = None, usd_per_hour: float | None = None, control: str | None = None,
                 boot_image: dict[str, Any] | None = None, role: str = "box",
                 container: ContainerImage | None = None,
                 log: Callable[[str], None] = print, popen: Callable[..., Any] = subprocess.Popen,
                 run: Callable[..., Any] = subprocess.run) -> None:
        SshMachine.__init__(self, cores=cores, memory_mb=memory_mb, lifetime_s=lifetime_s, log=log, popen=popen,
                            run=run)
        self.recipe = recipe or image_recipe("vm")
        self.container = container or box_image(self.recipe)  # what the VM's container runs (WebBox brings its own)
        self.container_image, self.image_name = self.container.tag, ami_name(self.container.tag)
        self._init_ec2(tags=tags, region=region, ec2=ec2, instance_type=instance_type, usd_per_hour=usd_per_hour,
                       control=control, boot_image=boot_image, role=role)
        self._price()  # an unknown type or region fails here, not after a run that then has no cost

    def _disk_gb(self) -> int:
        return self.container.disk_gb

    def _ensure_image(self) -> dict[str, Any]:
        return ensure_image(self.ec2, self.recipe, log=self.log, region=self.region, control=self.control,
                            container=self.container)

    def _warm_user_data(self) -> str:
        return warm_cloud_config(self.container_image)

    def _egress_open(self) -> bool:
        return "open" in self.host(["/usr/bin/bash", "-c", EGRESS_PROBE], 10)[1]

    def _metadata_line(self) -> str:
        return self.host(["/usr/bin/bash", "-c", IMDS_PROBE], 3)[1].strip()


# A pool member's one boot, as root in cloud-init's last stage: wait for dockerd, run the box image once, read
# every file on the disk (the blocks then are on the volume), and leave the rest to a unit of its own, since
# cloud-init cannot forget a boot it is still in: that unit waits for cloud-init to end, removes its record and
# the host keys this boot made, and powers off. The next boot is a first boot again, with the claimer's user data.
WARM_SCRIPT = r"""until /usr/bin/docker info > /dev/null 2>&1; do sleep 1; done
/usr/bin/docker run --rm --init --privileged --network host @IMAGE@ /usr/local/bin/python3 -c 'print(1)'
/usr/bin/find / -xdev -type f -print0 2> /dev/null | /usr/bin/xargs -0 -P 32 -n 32 /usr/bin/cat > /dev/null 2>&1
/usr/bin/systemd-run --unit pickfit-warm-done --on-active 2s /usr/bin/bash -c   '/usr/bin/cloud-init status --wait > /dev/null 2>&1; /usr/bin/cloud-init clean --logs; /usr/bin/rm -f /etc/ssh/ssh_host_* /root/.ssh/authorized_keys; /usr/bin/sync; /usr/bin/systemctl poweroff'
"""


def warm_cloud_config(container_image: str) -> str:
    """The cloud-init user data of a pool member: no user, no key, a poweroff armed as on every machine."""
    config = {"ssh_pwauth": False, "ssh_deletekeys": True, "users": [],
              "bootcmd": [lifetime_bootcmd(WARM_LIFETIME_S)],
              "runcmd": [["/usr/bin/bash", "-c", WARM_SCRIPT.replace("@IMAGE@", container_image)]]}
    return "#cloud-config\n" + json.dumps(config, indent=1) + "\n"


# -- the image


def bake_image(ec2: Any, recipe: ImageRecipe | None = None, *, log: Callable[[str], None] = print,
               region: str | None = None, control: str | None = None, container: ContainerImage | None = None,
               popen: Callable[..., Any] = subprocess.Popen, run: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    """Build the AMI for a kind of box (or for `container`) on a throwaway instance and return it as EC2
    describes it."""
    container = container or box_image(recipe or image_recipe("vm"))
    tag, name = container.tag, ami_name(container.tag)
    began = time.monotonic()
    builder = Ec2Machine(cores=2, memory_mb=2048, lifetime_s=BAKE_LIFETIME_S, recipe=recipe, region=region, ec2=ec2,
                         instance_type=BAKE_TYPE, control=control, boot_image=base_image(ec2), role="bake",
                         container=container, tags={"pickfit:image": name}, log=log, popen=popen, run=run)
    log(f"ec2: baking {name} from {builder.boot_image['Name']} (about ten minutes)")  # type: ignore[index]
    builder.boot()
    try:
        builder._host_checked(["/usr/bin/bash", "-s"], 900, "the host setup", stdin=HOST_SETUP.encode())
        builder._host_checked([DOCKER, "build", "--network", "host", "--tag", tag, "-"], 3600,
                              f"building {tag}", stdin=container.dockerfile.encode())
        builder._host_checked([DOCKER, "run", "--rm", "--init", "--privileged", "--network", "host", tag,
                               "/usr/local/bin/python3", "-c", "print('box image runs')"], 120, f"running {tag}")
        log(f"ec2: {tag} built on {builder.machine_id} in {time.monotonic() - began:.0f}s; making the AMI")
        builder._host_checked(["/usr/bin/bash", "-s"], 120, "sealing the image", stdin=HOST_SEAL.encode())
        ec2.stop_instances(InstanceIds=[builder.machine_id])
        builder_id = str(builder.machine_id)
        _wait(f"builder {builder_id} stopping",
              lambda: _instance(ec2, builder_id).get("State", {}).get("Name") == "stopped", 300, 5)
        try:
            made = ec2.create_image(InstanceId=builder.machine_id, Name=name,
                                    Description=f"pickfit box host: Debian, Docker, {tag}",
                                    TagSpecifications=[_tags("image", {"pickfit": "verify", "pickfit:image": tag}),
                                                       _tags("snapshot", {"pickfit": "verify", "pickfit:image": tag})])
        except Exception as error:
            if _code(error) != "InvalidAMIName.Duplicate":  # another harness baked it meanwhile
                raise
            made = {}
        if made:
            def ready() -> bool:
                state = ec2.describe_images(ImageIds=[made["ImageId"]])["Images"][0].get("State")
                if state == "failed":
                    raise BoxError(f"AMI {name} failed to build")
                return state == "available"

            _wait(f"AMI {name} becoming available", ready, 30 * 60, 10)
    finally:
        builder.close()
    image = find_image(ec2, name)
    if image is None:
        raise BoxError(f"AMI {name} is not there after baking it")
    log(f"ec2: AMI {name} ({image['ImageId']}) ready in {time.monotonic() - began:.0f}s")
    return image


def ensure_image(ec2: Any | None = None, recipe: ImageRecipe | None = None, *, log: Callable[[str], None] = print,
                 region: str | None = None, control: str | None = None,
                 container: ContainerImage | None = None) -> dict[str, Any]:
    """The AMI for a kind of box (or for `container`), baked if this account does not have it; call it before
    parallel boxes start."""
    ec2 = ec2 or ec2_client(region)
    container = container or box_image(recipe or image_recipe("vm"))
    return find_image(ec2, ami_name(container.tag)) or bake_image(ec2, recipe, log=log, region=region,
                                                                  control=control, container=container)


class Ec2Box(LinuxBox):
    """An EC2 instance driven like a DockerBox: LinuxBox on an Ec2Machine. Always a VM."""

    def __init__(self, *, limits: BoxLimits = BoxLimits(), tags: dict[str, str] | None = None,
                 display: bool = False, audio: bool = False, toolchain: bool = False, services: bool = False,
                 region: str | None = None,
                 ec2: Any = None, control: str | None = None, log: Callable[[str], None] = print) -> None:
        machine = Ec2Machine(cores=limits.cpus, memory_mb=limits.memory_mb, lifetime_s=limits.lifetime_s,
                             recipe=image_recipe("vm", display, audio, toolchain, services), tags=tags,
                             region=region, ec2=ec2,
                             control=control, log=lambda line: self.log(line))
        super().__init__(machine, limits=limits, display=display, audio=audio, toolchain=toolchain,
                         services=services, log=log)

    def _size(self) -> None:
        """The machine's size follows the box's limits, read when they are used."""
        lim = self.limits
        self.machine.cores, self.machine.memory_mb, self.machine.lifetime_s = lim.cpus, lim.memory_mb, lim.lifetime_s

    def start(self) -> None:
        if not self.started:
            self._size()
        super().start()

    def usd_per_second(self) -> float:
        self._size()
        return self.machine.usd_per_second()
