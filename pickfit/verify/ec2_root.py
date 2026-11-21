"""Ec2RootMachine: an EC2 instance handed over whole, as root_box.PrivilegedMachine. The first provider of the
full-privilege VM box (docs/proposals/privileges.md P6, docs/proposals/aws.md A3).

Ec2Machine (ec2_machine.py) puts the box user in a container on the VM and keeps root for pickfit. Here the box
user has sudo on the VM itself, so every rule Ec2Machine loads on the VM (the metadata route, the rule that cuts
open connections, the DNS rule) is one the software under test could remove. Everything that holds is therefore
outside the instance:

- Identity: no instance profile and no key pair, as on every pickfit instance. The metadata service is on while
  the instance boots (cloud-init reads this machine's keys from it; an instance launched with it off would have
  no keys at all) and is turned off with ModifyInstanceMetadataOptions before the box exists. That is a setting
  of the instance, not a route inside it: root cannot turn it back on. The start is refused unless EC2 itself
  says the endpoint is disabled.
- A network of its own (ensure_network): a VPC that holds nothing but these boxes, with the Amazon DNS server
  turned off (enableDnsSupport false). AWS filters traffic to its resolver with neither security groups nor
  network ACLs, so in the default VPC a name would still resolve after the cut, and a resolver is a way out. In
  this VPC the instance asks the public resolvers in RESOLVERS (a DHCP option set names them), and that traffic
  is a security group's to allow or refuse like any other.
- What may leave, online: TCP 80 and 443 to machine.ONLINE_CIDRS (public IPv4 only: no private range, no
  link-local, so no other instance), and DNS to RESOLVERS. Nothing else: no port 25, no SSH out. An instance wears
  the control group (SSH in from the harness; nothing out) and the two online groups; two, because 48 CIDRs times
  two ports is more than the 60 rules one group holds. No group allows anything in from another instance.
- The cut has two halves, both outside. The instance's groups are swapped for control and offline (no new
  connection leaves). AWS documents that a security group "continues to allow packets until existing connections
  time out", and here a connection may be root's own, so the box's subnet (one subnet per box) is also moved to a
  network ACL that allows only the harness's address: ACLs are stateless, "adding a network ACL that blocks
  traffic in either direction breaks existing connections". set_egress returns once EC2 describes both as asked.
- Inbound: SSH from the harness's address. An outside probe adds one rule for one port from that address and
  removes it (probe_ingress); the sweep removes one that was left.
- Lifetime: the instance's own poweroff timer is root's to stop, so ec2_reaper.reap_leaked ends instances by
  pickfit's tags and their age, at every start and from scripts/ec2_reap.py.
- The lane: these instances take the same slots as every pickfit machine on EC2 (ec2_machine.MAX_BOXES: two in a
  region from one host), so a third can never start; the lane runs one record at a time (lanes.root_vm_lane,
  the CLI's batch), since a record needs an agent's box and a replay's. No pool: a start is always a new instance.
- The ledger: a row per instance in lane "linux-root" with the purpose its tags name (agent, replay, limits, bake).
- The image (bake_root_image): Debian with Docker (compose, buildx), sudo, the tools a box's image has, and the
  box user with passwordless sudo in the docker group. One image is kept: prune_root_images removes the others
  and their snapshots after a bake and from the reaper.
- An extra blank volume on request (extra_disk_gb, privileges.md P8's fake disk), deleted with the instance.
- /dev/kvm on request (kvm=True): the instance is launched with CpuOptions NestedVirtualization=enabled, which
  AWS documents for C7i-flex and M7i-flex (the types used here) among others. Not tried on a real instance.
- Credentials are boto3's default chain, as for every pickfit instance. Beyond the calls ec2_machine.py names,
  this lane uses CreateVpc, ModifyVpcAttribute, DescribeVpcAttribute, CreateInternetGateway,
  AttachInternetGateway, DescribeRouteTables, CreateRoute, CreateDhcpOptions, AssociateDhcpOptions, CreateSubnet,
  DescribeSubnets, DeleteSubnet, CreateNetworkAcl, CreateNetworkAclEntry, DescribeNetworkAcls,
  ReplaceNetworkAclAssociation, DeleteNetworkAcl, DeregisterImage and DeleteSnapshot. The watch host's policy
  (deploy/watch/aws-watch-policy.json) allows none of these yet, which is one more reason the lane is not wired
  into the watch.

What AWS's documentation says, read 2026-11-21 (the behaviours this design rests on, none of them measured here):
security groups and network ACLs do not filter traffic to Amazon DNS, DHCP, instance metadata or the Time Sync
Service (VPC user guide, "Security group basics" and "Network ACL basics"); a VPC with enableDnsSupport false has
no working Amazon DNS server ("DNS attributes for your VPC"); a changed security group rule does not interrupt a
tracked connection, a network ACL does (EC2 user guide, "Security group connection tracking"); the metadata
options of a running instance can be changed, and with the endpoint disabled nothing on the instance reaches it
("Configure the Instance Metadata Service options").

Nothing in this file has run against AWS yet: tests/test_verify_ec2_root.py drives it against a fake EC2 and a
fake ssh. `pickfit verify --runner ec2 --runtime rootvm --limits-test` is the first thing to run on a real one.
"""

from __future__ import annotations

import datetime
import hashlib
import ipaddress
import os
import secrets
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.ec2_machine import (
    BAKE_LIFETIME_S,
    BAKE_TYPE,
    BASE_AMI_NAME,
    EGRESS_PROBE,
    HARNESS_RULE,
    HOST_SEAL,
    IMDS_PROBE,
    MAX_BOXES_ENV,
    REAP_MARGIN_S,
    Ec2Instance,
    Ec2Machine,
    _code,
    _instance,
    _rules,
    _stale_harness_rules,
    _tag,
    _tags,
    _wait,
    base_image,
    control_cidr,
    ec2_client,
    find_image,
    image_from_builder,
    max_boxes,
    slot_wait_s,
)
from pickfit.verify.machine import ONLINE_CIDRS
from pickfit.verify.meter import identity
from pickfit.verify.root_box import FULL, PrivilegedMachine, RootVmBox
from pickfit.verify.ssh_machine import SSH_GRACE_S, SshMachine, SshProcess

LANE = "linux-root"  # the ledger's lane, so this lane's spend can be told from the plain Linux boxes'
ROLE = "rootvm"
NET_TAG = "pickfit:net"  # on the VPC and everything made in it
NET_KIND = "rootvm"
CONTROL_TAG = "pickfit:control"  # on an offline ACL: the harness address it lets through
MADE_TAG = "pickfit:made"  # the day an offline ACL was made
MADE_AT_TAG = "pickfit:made-at"  # unix time a box's subnet was made
SUBNET_SETTLE_S = 600  # a subnet this new may have a box launching into it: the sweep leaves it
VPC_CIDR = "10.213.0.0/16"  # nothing routes to it: the VPC has no peering, no gateway but the internet's
SUBNET_PREFIX = 28  # one subnet a box: 4096 of them, 11 usable addresses each
SUBNET_TRIES = 8
AZ_ENV = "PICKFIT_EC2_ROOT_AZ"  # the availability zone of the boxes' subnets (EC2 chooses when unset)
# Public resolvers the instance asks, since the VPC's own is off. Cloudflare's and Google's.
RESOLVERS = ("1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4")
GROUPS = {"control": "pickfit-rootvm-control", "http": "pickfit-rootvm-online-http",
          "https": "pickfit-rootvm-online-https", "offline": "pickfit-rootvm-offline"}
GROUP_NOTES = {"control": "pickfit root VM: SSH in from the harness, nothing out",
               "http": "pickfit root VM online: TCP 80 to public IPv4, DNS to four resolvers",
               "https": "pickfit root VM online: TCP 443 to public IPv4",
               "offline": "pickfit root VM offline: nothing in or out"}
ONLINE_ROLES = ("http", "https")
GROUP_RULE_QUOTA = 60  # rules one security group holds in one direction, by default
PROBE_RULE = "pickfit probe "  # how an outside probe's inbound rule is described, with its instance and date
ACL_RULE = 100
EPHEMERAL = (1024, 65535)  # where the harness's own ports are: sshd's answers go there
DISK_GB = 24  # Debian, Docker and its images, and what a tool installs
EXTRA_DISK_DEVICE = "/dev/sdf"  # the blank volume's name to EC2; the VM sees an NVMe disk
EXTRA_DISK_MAX_GB = 64
IMAGE_KIND_TAG = "pickfit:image-kind"
BOOT_WAIT_S = 240

# Root on a fresh Debian: what a box's image has (sandbox.Dockerfile), as Debian's own packages, plus what this
# kind of box is for: Docker with compose and buildx (bridge networking on, as an install guide expects), sudo,
# FUSE and kmod, disk tools for the extra volume. The box user is uid 1000 with passwordless sudo, in the docker
# group, with a systemd user manager of its own (linger). uv is its project's release from PyPI, as in
# sandbox.Dockerfile. The two boot fixes are ec2_machine.HOST_SETUP's (measured there): cloud-init asks only the
# IPv4 metadata address, and a unit reads the container runtime's programs early in the boot.
ROOT_HOST_SETUP = r"""set -eu
export DEBIAN_FRONTEND=noninteractive
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service 2>/dev/null || true
apt-get -o DPkg::Lock::Timeout=180 update
apt-get -o DPkg::Lock::Timeout=180 install -y --no-install-recommends \
  docker.io docker-cli docker-compose docker-buildx sudo ca-certificates curl git unzip xz-utils zstd bzip2 file \
  procps iproute2 kmod fuse3 nftables iptables dbus-user-session parted e2fsprogs dosfstools \
  python3 python3-pip python3-venv pipx nodejs npm
PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install uv
useradd --uid 1000 --create-home --shell /bin/bash sbx
usermod -aG docker sbx
printf '%s\n' 'sbx ALL=(ALL:ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-pickfit-sbx
chmod 0440 /etc/sudoers.d/90-pickfit-sbx
visudo -c -q
loginctl enable-linger sbx
printf '%s\n' 'MaxSessions 64' 'MaxStartups 64:30:128' 'PasswordAuthentication no' \
  'KbdInteractiveAuthentication no' 'AllowUsers root' > /etc/ssh/sshd_config.d/60-pickfit.conf
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
runuser -u sbx -- sudo -n id -u
runuser -u sbx -- docker info --format 'docker {{.ServerVersion}} cgroup v{{.CgroupVersion}}'
docker compose version
uv --version
"""


def root_ami_name() -> str:
    """The AMI of the full-privilege box: named after a hash of what makes it, so a change bakes a new one."""
    made = hashlib.sha256((BASE_AMI_NAME + ROOT_HOST_SETUP + HOST_SEAL).encode()).hexdigest()[:12]
    return f"pickfit-rootvm-host-{made}"


# -- the network


@dataclass
class RootNet:
    """The lane's network in one region: the VPC, its security groups by role, its default ACL (allows all: the
    groups are the policy while online) and the offline ACL for this harness's address."""

    vpc: str
    groups: dict[str, str]
    online_acl: str
    offline_acl: str
    control: str
    wear: dict[bool, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        g = self.groups
        self.wear = {True: [g["control"], *(g[role] for role in ONLINE_ROLES)], False: [g["control"], g["offline"]]}


def online_egress() -> dict[str, list[dict[str, Any]]]:
    """The egress permissions of the two online groups: all that ever leaves a box."""
    public = [{"CidrIp": cidr} for cidr in ONLINE_CIDRS]
    resolvers = [{"CidrIp": f"{address}/32"} for address in RESOLVERS]
    return {"http": [{"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": public},
                     {"IpProtocol": "udp", "FromPort": 53, "ToPort": 53, "IpRanges": resolvers},
                     {"IpProtocol": "tcp", "FromPort": 53, "ToPort": 53, "IpRanges": resolvers}],
            "https": [{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": public}]}


def _net_tags(resource: str, **more: str) -> dict[str, Any]:
    return _tags(resource, {"Name": "pickfit-rootvm", "pickfit": "verify", NET_TAG: NET_KIND, **more})


def _check_groups(groups: dict[str, dict[str, Any]]) -> None:
    """The four groups are exactly what pickfit makes: BoxError names the one that is not. Nothing leaves but the
    online groups' rules; nothing comes in but TCP from single IPv4 addresses on the control group (the harness's
    SSH, and a probe's one port)."""
    want_out = {role: _rules(rules) for role, rules in online_egress().items()}
    for role, name in GROUPS.items():
        group = groups[role]
        got_in, got_out = _rules(group.get("IpPermissions", [])), _rules(group.get("IpPermissionsEgress", []))
        ingress_ok = not got_in if role != "control" else all(  # one TCP port from an IPv4 range that is not all
            rule[0] == "tcp" and rule[1] == rule[2] and "." in str(rule[3]) and not str(rule[3]).endswith("/0")
            for rule in got_in)
        if got_out != want_out.get(role, set()) or not ingress_ok:
            raise BoxError(f"security group {name} ({group['GroupId']}) is not as pickfit makes it; delete it "
                           "(pickfit makes it again) or restore its rules")


def _find_vpc(ec2: Any) -> str | None:
    found = ec2.describe_vpcs(Filters=[{"Name": f"tag:{NET_TAG}", "Values": [NET_KIND]}]).get("Vpcs", [])
    ours = sorted(v["VpcId"] for v in found if _tag(v, NET_TAG) == NET_KIND and _tag(v, "pickfit") == "verify")
    return ours[0] if ours else None


def _make_vpc(ec2: Any, log: Callable[[str], None]) -> str:
    """The lane's VPC: no Amazon DNS, an internet gateway and a default route to it, and a DHCP option set that
    names the public resolvers. Made once in a region."""
    vpc = ec2.create_vpc(CidrBlock=VPC_CIDR, TagSpecifications=[_net_tags("vpc")])["Vpc"]["VpcId"]
    ec2.modify_vpc_attribute(VpcId=vpc, EnableDnsSupport={"Value": False})
    gateway = ec2.create_internet_gateway(
        TagSpecifications=[_net_tags("internet-gateway")])["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=gateway, VpcId=vpc)
    tables = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc]},
                                                {"Name": "association.main", "Values": ["true"]}])["RouteTables"]
    ec2.create_route(RouteTableId=tables[0]["RouteTableId"], DestinationCidrBlock="0.0.0.0/0", GatewayId=gateway)
    options = ec2.create_dhcp_options(
        DhcpConfigurations=[{"Key": "domain-name-servers", "Values": list(RESOLVERS)}],
        TagSpecifications=[_net_tags("dhcp-options")])["DhcpOptions"]["DhcpOptionsId"]
    ec2.associate_dhcp_options(DhcpOptionsId=options, VpcId=vpc)
    log(f"ec2 root: made the lane's VPC {vpc} ({VPC_CIDR}, no Amazon DNS)")
    return vpc


def _ensure_groups(ec2: Any, vpc: str, control: str) -> dict[str, str]:
    def described() -> dict[str, dict[str, Any]]:
        found = ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc]},
                                                      {"Name": "group-name", "Values": list(GROUPS.values())}])
        by_name = {g["GroupName"]: g for g in found["SecurityGroups"]}
        return {role: by_name[name] for role, name in GROUPS.items() if name in by_name}

    have = described()
    egress = online_egress()
    for role, name in GROUPS.items():
        if role in have:
            continue
        try:
            made = ec2.create_security_group(GroupName=name, Description=GROUP_NOTES[role], VpcId=vpc,
                                             TagSpecifications=[_net_tags("security-group")])
        except Exception as error:
            if _code(error) != "InvalidGroup.Duplicate":  # another harness made it just now
                raise
            continue
        # A new group allows everything out; a box must never wear it like that.
        ec2.revoke_security_group_egress(GroupId=made["GroupId"], IpPermissions=[
            {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}])
        if role in egress:
            ec2.authorize_security_group_egress(GroupId=made["GroupId"], IpPermissions=egress[role])
    have = described()
    missing = [GROUPS[role] for role in GROUPS if role not in have]
    if missing:
        raise BoxError(f"security groups missing after making them: {missing}")
    _check_groups(have)
    group = have["control"]
    if ("tcp", 22, 22, control) not in _rules(group.get("IpPermissions", [])):
        try:
            ec2.authorize_security_group_ingress(GroupId=group["GroupId"], IpPermissions=[
                {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                 "IpRanges": [{"CidrIp": control, "Description": f"{HARNESS_RULE}{time.strftime('%Y-%m-%d')}"}]}])
        except Exception as error:
            if _code(error) != "InvalidPermission.Duplicate":
                raise
    stale = _stale_harness_rules(group, control, datetime.date.today())
    if stale:
        try:
            ec2.revoke_security_group_ingress(GroupId=group["GroupId"], IpPermissions=[
                {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": cidr} for cidr in stale]}])
        except Exception:  # another harness removed them just now, or may not: the rules are only old
            pass
    return {role: g["GroupId"] for role, g in have.items()}


def _acl_entries(acl: dict[str, Any]) -> set[tuple[bool, str, str, str, Any, Any]]:
    """An ACL's own entries (not the closing deny-all every ACL has): (egress, action, protocol, cidr, from, to)."""
    return {(bool(e.get("Egress")), str(e.get("RuleAction")), str(e.get("Protocol")), str(e.get("CidrBlock")),
             (e.get("PortRange") or {}).get("From"), (e.get("PortRange") or {}).get("To"))
            for e in acl.get("Entries", []) if e.get("RuleNumber", 32767) < 32767}


def offline_entries(control: str) -> set[tuple[bool, str, str, str, Any, Any]]:
    """What an offline ACL lets through, and nothing else: TCP from the harness's address (the control group says
    which ports), and TCP back to the harness's own ports."""
    return {(False, "allow", "6", control, 1, 65535), (True, "allow", "6", control, *EPHEMERAL)}


def _ensure_acls(ec2: Any, vpc: str, control: str) -> tuple[str, str]:
    """(the VPC's default ACL, the offline ACL for this harness address), the second made if missing and refused
    if it lets anything else through."""
    acls = ec2.describe_network_acls(Filters=[{"Name": "vpc-id", "Values": [vpc]}])["NetworkAcls"]
    default = next((a["NetworkAclId"] for a in acls if a.get("IsDefault")), None)
    if default is None:
        raise BoxError(f"VPC {vpc} has no default network ACL")
    ours = sorted((a for a in acls if not a.get("IsDefault") and _tag(a, NET_TAG) == NET_KIND
                   and _tag(a, CONTROL_TAG) == control), key=lambda a: a["NetworkAclId"])
    if ours:
        if _acl_entries(ours[0]) != offline_entries(control):
            raise BoxError(f"network ACL {ours[0]['NetworkAclId']} is not as pickfit makes it; delete it (pickfit "
                           "makes it again)")
        return default, ours[0]["NetworkAclId"]
    made = ec2.create_network_acl(VpcId=vpc, TagSpecifications=[_net_tags(
        "network-acl", **{CONTROL_TAG: control, MADE_TAG: time.strftime("%Y-%m-%d")})])["NetworkAcl"]["NetworkAclId"]
    for egress, action, protocol, cidr, low, high in sorted(offline_entries(control)):
        ec2.create_network_acl_entry(NetworkAclId=made, RuleNumber=ACL_RULE, Protocol=protocol, RuleAction=action,
                                     Egress=egress, CidrBlock=cidr, PortRange={"From": low, "To": high})
    return default, made


def ensure_network(ec2: Any, control: str, log: Callable[[str], None] = print) -> RootNet:
    """The lane's network, made if missing and checked every time: the VPC still has no Amazon DNS, the groups
    and the offline ACL are exactly pickfit's, and the harness's address is allowed in for SSH."""
    vpc = _find_vpc(ec2) or _make_vpc(ec2, log)
    dns = ec2.describe_vpc_attribute(VpcId=vpc, Attribute="enableDnsSupport").get("EnableDnsSupport", {})
    if dns.get("Value") is not False:
        raise BoxError(f"VPC {vpc} resolves names through Amazon's DNS server, which no firewall of AWS's filters; "
                       "turn enableDnsSupport off again, or delete the VPC (pickfit makes it again)")
    groups = _ensure_groups(ec2, vpc, control)
    online_acl, offline_acl = _ensure_acls(ec2, vpc, control)
    return RootNet(vpc, groups, online_acl, offline_acl, control)


def _subnet_association(ec2: Any, subnet: str) -> tuple[str, str]:
    """(the id of the subnet's ACL association, the ACL it names), as EC2 describes it now."""
    acls = ec2.describe_network_acls(Filters=[{"Name": "association.subnet-id", "Values": [subnet]}])["NetworkAcls"]
    for acl in acls:
        for association in acl.get("Associations", []):
            if association.get("SubnetId") == subnet:
                return association["NetworkAclAssociationId"], acl["NetworkAclId"]
    raise BoxError(f"subnet {subnet} has no network ACL association")


def make_subnet(ec2: Any, net: RootNet, tags: dict[str, str]) -> str:
    """A subnet for one box, at a random place in the VPC (another harness may be making one now)."""
    blocks = list(ipaddress.ip_network(VPC_CIDR).subnets(new_prefix=SUBNET_PREFIX))
    zone = os.environ.get(AZ_ENV, "").strip()
    error: Exception | None = None
    for _ in range(SUBNET_TRIES):
        cidr = str(blocks[secrets.randbelow(len(blocks))])
        try:
            made = ec2.create_subnet(VpcId=net.vpc, CidrBlock=cidr, **({"AvailabilityZone": zone} if zone else {}),
                                     TagSpecifications=[_tags("subnet", {
                                         **tags, NET_TAG: NET_KIND, MADE_AT_TAG: str(int(time.time()))})])
            return str(made["Subnet"]["SubnetId"])
        except Exception as err:
            if _code(err) != "InvalidSubnet.Conflict":
                raise BoxError(f"EC2 CreateSubnet failed: {_code(err) or type(err).__name__}: {err}") from err
            error = err
    raise BoxError(f"no free /{SUBNET_PREFIX} found in {VPC_CIDR} after {SUBNET_TRIES} tries: {error}")


def sweep_network(ec2: Any, control: str | None = None, log: Callable[[str], None] = print,
                  now: float | None = None, apply: bool = True) -> list[str]:
    """Remove what the lane's boxes left in its VPC: a subnet no instance lives in any more (a box's own close
    cannot delete it while the instance is still shutting down), a probe's inbound rule whose instance is gone,
    and an offline ACL for an address the harness had a week ago. What was removed (or, without `apply`, would be).
    Only things that carry the lane's own tag, in the lane's own VPC."""
    now = time.time() if now is None else now
    vpc = _find_vpc(ec2)
    removed: list[str] = []
    if vpc is None:
        return removed
    found = ec2.describe_instances(Filters=[{"Name": "vpc-id", "Values": [vpc]}])
    instances = [i for r in found.get("Reservations", []) for i in r.get("Instances", [])]
    live = {i["InstanceId"]: i for i in instances if i.get("State", {}).get("Name") != "terminated"}
    used = {i.get("SubnetId") for i in live.values()}
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc]},
                                            {"Name": f"tag:{NET_TAG}", "Values": [NET_KIND]}]).get("Subnets", [])
    for subnet in subnets:
        made = _tag(subnet, MADE_AT_TAG) or ""
        fresh = not made.isdigit() or int(made) + SUBNET_SETTLE_S > now  # its box may be launching into it now
        if _tag(subnet, NET_TAG) != NET_KIND or subnet["SubnetId"] in used or fresh:
            continue
        try:
            if apply:
                ec2.delete_subnet(SubnetId=subnet["SubnetId"])
            removed.append(subnet["SubnetId"])
        except Exception as error:  # a network interface is still going: the next sweep takes it
            log(f"ec2 root sweep: {subnet['SubnetId']} not deleted ({_code(error) or type(error).__name__})")
    groups = ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc]}, {
        "Name": "group-name", "Values": [GROUPS["control"]]}]).get("SecurityGroups", [])
    for group in groups:
        for permission in group.get("IpPermissions", []):
            gone = [r for r in permission.get("IpRanges", []) if str(r.get("Description", "")).startswith(PROBE_RULE)
                    and str(r.get("Description", ""))[len(PROBE_RULE):].split()[0] not in live]
            if not gone:
                continue
            if apply:
                ec2.revoke_security_group_ingress(GroupId=group["GroupId"], IpPermissions=[
                    {"IpProtocol": permission["IpProtocol"], "FromPort": permission["FromPort"],
                     "ToPort": permission["ToPort"], "IpRanges": [{"CidrIp": r["CidrIp"]} for r in gone]}])
            removed += [f"probe rule {permission.get('FromPort')} {r['CidrIp']}" for r in gone]
    today = datetime.date.today()
    for acl in ec2.describe_network_acls(Filters=[{"Name": "vpc-id", "Values": [vpc]}]).get("NetworkAcls", []):
        if acl.get("IsDefault") or _tag(acl, NET_TAG) != NET_KIND or acl.get("Associations"):
            continue
        try:
            age = (today - datetime.date.fromisoformat(_tag(acl, MADE_TAG) or "")).days
        except ValueError:
            continue
        if _tag(acl, CONTROL_TAG) != control and age >= 7:
            if apply:
                ec2.delete_network_acl(NetworkAclId=acl["NetworkAclId"])
            removed.append(acl["NetworkAclId"])
    if removed:
        log(f"ec2 root sweep: {'removed' if apply else 'would remove'} {', '.join(removed)}")
    return removed


# -- the machine


class Ec2RootMachine(Ec2Instance, SshMachine, PrivilegedMachine):
    """An EC2 instance from pickfit's root-VM image, alone in a subnet of the lane's VPC. Root commands run on the
    VM itself over SSH; there is no container."""

    lane = LANE
    capabilities = FULL
    cut = "stateless"
    boot_wait_s: float = BOOT_WAIT_S

    def __init__(self, *, cores: float, memory_mb: int, lifetime_s: int, tags: dict[str, str] | None = None,
                 region: str | None = None, ec2: Any = None, instance_type: str | None = None,
                 usd_per_hour: float | None = None, control: str | None = None,
                 boot_image: dict[str, Any] | None = None, extra_disk_gb: int = 0, kvm: bool = False,
                 log: Callable[[str], None] = print, popen: Callable[..., Any] = subprocess.Popen,
                 run: Callable[..., Any] = subprocess.run) -> None:
        if not 0 <= int(extra_disk_gb) <= EXTRA_DISK_MAX_GB:
            raise ValueError(f"the extra disk is 1 to {EXTRA_DISK_MAX_GB} GB, got {extra_disk_gb}")
        SshMachine.__init__(self, cores=cores, memory_mb=memory_mb, lifetime_s=lifetime_s, log=log, popen=popen,
                            run=run)
        self.extra_disk_gb = int(extra_disk_gb)
        self.kvm = kvm
        self.image_name = root_ami_name()
        self.net: RootNet | None = None
        self.subnet: str | None = None
        self._association: str | None = None
        self._init_ec2(tags=tags, region=region, ec2=ec2, instance_type=instance_type, usd_per_hour=usd_per_hour,
                       control=control, boot_image=boot_image, role=ROLE)
        self._price()  # an unknown type or region fails here, not after a run that then has no cost

    # -- what Ec2Instance asks

    def _size(self) -> tuple[float, int]:
        return self.cores, self.memory_mb  # the instance is the box: nothing of pickfit's runs next to it

    def _disk_gb(self) -> int:
        return DISK_GB + self.extra_disk_gb  # both are billed, and deleted, with the instance

    def _ensure_image(self) -> dict[str, Any]:
        return ensure_root_image(self.ec2, log=self.log, region=self.region, control=self.control)

    def _egress_open(self) -> bool:
        return "open" in self.host(["/usr/bin/bash", "-c", EGRESS_PROBE], 10)[1]

    def _metadata_line(self) -> str:
        return self.host(["/usr/bin/bash", "-c", IMDS_PROBE], 3)[1].strip()

    def run_kwargs(self, image: dict[str, Any], user_data: str, now: float) -> dict[str, Any]:
        """RunInstances arguments (separate so tests can check them): no profile, no key pair, one interface in
        the box's own subnet behind the lane's groups, every volume deleted with the instance."""
        assert self.net is not None and self.subnet is not None
        tags = self._box_tags(now)
        disks = [{"DeviceName": image.get("RootDeviceName", "/dev/xvda"), "Ebs": {
            "VolumeSize": DISK_GB, "VolumeType": "gp3", "DeleteOnTermination": True}}]
        if self.extra_disk_gb:  # blank: no snapshot behind it
            disks.append({"DeviceName": EXTRA_DISK_DEVICE, "Ebs": {
                "VolumeSize": self.extra_disk_gb, "VolumeType": "gp3", "DeleteOnTermination": True}})
        return {
            "ImageId": image["ImageId"], "InstanceType": self._price()[0], "MinCount": 1, "MaxCount": 1,
            "UserData": user_data, "InstanceInitiatedShutdownBehavior": "terminate",
            "NetworkInterfaces": [{"DeviceIndex": 0, "SubnetId": self.subnet, "Groups": list(self.net.wear[True]),
                                   "AssociatePublicIpAddress": True, "DeleteOnTermination": True}],
            # On for the boot only (cloud-init reads this machine's keys from it); _seal turns it off, and the
            # start is refused unless EC2 then says it is off. Tokens and one hop meanwhile.
            "MetadataOptions": {"HttpEndpoint": "enabled", "HttpTokens": "required", "HttpPutResponseHopLimit": 1,
                                "HttpProtocolIpv6": "disabled", "InstanceMetadataTags": "disabled"},
            "BlockDeviceMappings": disks,
            **({"CpuOptions": {"NestedVirtualization": "enabled"}} if self.kvm else {}),
            "TagSpecifications": [_tags("instance", tags), _tags("volume", tags), _tags("network-interface", tags)],
        }

    # -- lifecycle

    def _create(self, user_data: str) -> str:
        self.ec2 = self.ec2 or ec2_client(self.region)
        self._begin_start()
        self.control = self.control or control_cidr()
        try:  # what earlier boxes left; never the reason this one does not start
            from pickfit.verify.ec2_reaper import reap_leaked

            reap_leaked(self.ec2, self.log)
            sweep_network(self.ec2, self.control, self.log)
        except Exception as error:
            self.log(f"ec2 root reap: {type(error).__name__}: {error}"[:300])
        self.net = ensure_network(self.ec2, self.control, self.log)
        self.groups = self.net.groups
        image = self.boot_image or self._ensure_image()  # a bake takes a slot of its own, so before this one's
        if not self.reserve(wait=True):
            raise BoxError(f"no room for another EC2 machine in {self.region}: {max_boxes()} of pickfit's ran for "
                           f"{slot_wait_s():.0f}s (the lane's limit, {MAX_BOXES_ENV})")
        assert self.slot is not None
        self._image = image.get("Name") or image["ImageId"]
        self.subnet = make_subnet(self.ec2, self.net, self._box_tags(time.time()))
        self._launch(image, user_data)
        # The reaper ends the machine within its lifetime whatever root does to its timer: the slot goes back by then.
        self.slot.expire_after(self.lifetime_s + 2 * REAP_MARGIN_S)
        self._open_meter()
        return str(self._wait_running()["PublicIpAddress"])

    def prepare(self) -> dict[str, Any]:
        """The network and the image, without starting a box (`pickfit verify --prepare-base`); older images of
        this kind are removed."""
        self.ec2 = self.ec2 or ec2_client(self.region)
        self.control = self.control or control_cidr()
        self.net = ensure_network(self.ec2, self.control, self.log)
        image = self._ensure_image()
        prune_root_images(self.ec2, keep=image["ImageId"], log=self.log)
        return image

    def _seal(self) -> None:
        """Turn the metadata service off, wait until root on the VM gets no token from it, and then take EC2's own
        word for it: the VM's answer is one the software could later forge, the instance's setting is not."""
        super()._seal()
        options = _instance(self.ec2, str(self.machine_id)).get("MetadataOptions", {})
        if options.get("HttpEndpoint") != "disabled":
            raise BoxError(f"EC2 does not say the metadata service of {self.machine_id} is off: {options}")

    def start(self) -> None:
        self.boot()
        try:
            began = time.monotonic()
            self._seal()
            self._association = _subnet_association(self.ec2, str(self.subnet))[0]
            self.timings["seal_s"] = round(time.monotonic() - began, 1)
        except BaseException as error:
            self.close()
            if isinstance(error, BoxError) or not isinstance(error, Exception):
                raise
            raise BoxError(f"{self.provider} machine start failed: {type(error).__name__}: {error}") from error
        self.log(f"{self.provider} root machine {self.machine_id} up: " +
                 ", ".join(f"{name[:-2]} {seconds}s" for name, seconds in self.timings.items()))

    def spawn(self, argv: list[str], timeout_s: int, *, workdir: str | None = None) -> SshProcess:
        """argv as root on the VM itself."""
        where = ["/usr/bin/env", "--chdir", workdir] if workdir is not None else []
        return self._host_spawn([*where, "/usr/bin/timeout", "--signal=KILL", str(int(timeout_s)), *argv],
                                timeout_s + SSH_GRACE_S)

    def egress_view(self) -> dict[str, Any]:
        """The instance's security groups and its subnet's ACL, as EC2 describes them now."""
        instance = _instance(self.ec2, str(self.machine_id))
        groups = sorted(g.get("GroupId") for g in instance.get("SecurityGroups", []))
        self._association, acl = _subnet_association(self.ec2, str(self.subnet))
        return {"groups": groups, "acl": acl}

    def set_egress(self, enabled: bool) -> None:
        """Both halves are EC2's: nothing is asked of the VM, whose rules its root could remove."""
        self._provider_egress(enabled)

    def _provider_egress(self, enabled: bool) -> None:
        assert self.net is not None and self._association is not None
        wear, acl = self.net.wear[enabled], self.net.online_acl if enabled else self.net.offline_acl

        def groups() -> None:
            self.ec2.modify_instance_attribute(InstanceId=self.machine_id, Groups=wear)

        def subnet() -> None:
            self._association = self.ec2.replace_network_acl_association(
                AssociationId=self._association, NetworkAclId=acl)["NewAssociationId"]

        try:  # closing: the ACL first, which ends what is open; opening: the groups first, then the ACL lets it out
            for change in ((groups, subnet) if enabled else (subnet, groups)):
                change()
            view = self.egress_view()
        except BoxError:
            raise
        except Exception as error:
            raise BoxError(f"EC2 network change failed: {_code(error) or type(error).__name__}: {error}") from error
        if view != {"groups": sorted(wear), "acl": acl}:
            raise BoxError(f"EC2 does not describe {self.machine_id} as {'online' if enabled else 'offline'}: {view}")
        _wait(f"EC2 egress {'opening' if enabled else 'closing'} for {self.machine_id}",
              lambda: self._egress_open() == enabled, 45, 1)

    def probe_ingress(self, port: int, enabled: bool) -> None:
        assert self.net is not None
        if not 1 <= int(port) <= 65535 or int(port) == 22:
            raise BoxError(f"port {port} is not one an outside probe may open")
        rule = {"IpProtocol": "tcp", "FromPort": int(port), "ToPort": int(port)}
        try:
            if enabled:
                note = f"{PROBE_RULE}{self.machine_id} {time.strftime('%Y-%m-%d')}"
                self.ec2.authorize_security_group_ingress(GroupId=self.net.groups["control"], IpPermissions=[
                    {**rule, "IpRanges": [{"CidrIp": self.net.control, "Description": note}]}])
            else:
                self.ec2.revoke_security_group_ingress(GroupId=self.net.groups["control"], IpPermissions=[
                    {**rule, "IpRanges": [{"CidrIp": self.net.control}]}])
        except Exception as error:
            if _code(error) not in ("InvalidPermission.Duplicate", "InvalidPermission.NotFound"):
                raise BoxError(f"EC2 probe rule for port {port}: {_code(error) or type(error).__name__}") from error

    def probed_ports(self) -> list[int]:
        assert self.net is not None
        found = self.ec2.describe_security_groups(GroupIds=[self.net.groups["control"]])["SecurityGroups"]
        return sorted({int(rule[1]) for group in found for rule in _rules(group.get("IpPermissions", []))
                       if rule[1] != 22})

    def state(self) -> str:
        if self.machine_id is None or self.ec2 is None:
            return "never started"
        return str(_instance(self.ec2, str(self.machine_id)).get("State", {}).get("Name") or "gone")

    def outside_view(self) -> dict[str, Any]:
        instance = _instance(self.ec2, str(self.machine_id))
        metadata = instance.get("MetadataOptions", {})
        volumes = [m.get("Ebs", {}) for m in instance.get("BlockDeviceMappings", [])]
        base = ipaddress.ip_network(VPC_CIDR).network_address
        return {"instance": self.machine_id, "type": instance.get("InstanceType"), "image": self.image,
                "instance_profile": instance.get("IamInstanceProfile"), "key_pair": instance.get("KeyName"),
                "metadata_endpoint": metadata.get("HttpEndpoint"), "metadata_state": metadata.get("State"),
                "address": instance.get("PublicIpAddress"), "private_address": instance.get("PrivateIpAddress"),
                "subnet": instance.get("SubnetId"), "vpc": instance.get("VpcId"),
                "vpc_router": str(base + 1), "vpc_resolver": str(base + 2),  # where a VPC's own services answer
                "volumes_deleted_with_it": bool(volumes) and all(v.get("DeleteOnTermination") for v in volumes),
                **self.egress_view()}

    def _destroy(self) -> None:
        if self.ec2 is None:
            return
        try:
            if self.machine_id is not None:
                self.ec2.terminate_instances(InstanceIds=[self.machine_id])
        finally:
            if self.subnet is not None:  # nearly always still in use while the instance shuts down: the sweep's then
                try:
                    self.ec2.delete_subnet(SubnetId=self.subnet)
                except Exception:
                    pass


# -- the image


def bake_root_image(ec2: Any, *, log: Callable[[str], None] = print, region: str | None = None,
                    control: str | None = None, popen: Callable[..., Any] = subprocess.Popen,
                    run: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    """Build the root-VM AMI on a throwaway instance and return it as EC2 describes it. The builder is an ordinary
    pickfit instance (Ec2Machine in the default VPC, never a box): it needs nothing this lane's network gives."""
    name = root_ami_name()
    began = time.monotonic()
    builder = Ec2Machine(cores=2, memory_mb=2048, lifetime_s=BAKE_LIFETIME_S, region=region, ec2=ec2,
                         instance_type=BAKE_TYPE, control=control, boot_image=base_image(ec2), role="bake",
                         tags={"pickfit:image": name}, log=log, popen=popen, run=run)
    builder.lane = LANE
    log(f"ec2: baking {name} from {builder.boot_image['Name']} (about ten minutes)")  # type: ignore[index]
    builder.boot()
    try:
        builder._host_checked(["/usr/bin/bash", "-s"], 1500, "the root VM's setup", stdin=ROOT_HOST_SETUP.encode())
        builder._host_checked(["/usr/bin/bash", "-s"], 120, "sealing the image", stdin=HOST_SEAL.encode())
        image_from_builder(ec2, builder, name, "pickfit full-privilege VM box: Debian, Docker, sudo for the box user",
                           {"pickfit": "verify", "pickfit:image": name, IMAGE_KIND_TAG: NET_KIND})
    finally:
        builder.close()
    image = find_image(ec2, name)
    if image is None:
        raise BoxError(f"AMI {name} is not there after baking it")
    log(f"ec2: AMI {name} ({image['ImageId']}) ready in {time.monotonic() - began:.0f}s")
    try:
        prune_root_images(ec2, keep=image["ImageId"], log=log)
    except Exception as error:  # the reaper removes them later
        log(f"ec2: older root-VM images not removed ({_code(error) or type(error).__name__})")
    return image


def ensure_root_image(ec2: Any | None = None, *, log: Callable[[str], None] = print, region: str | None = None,
                      control: str | None = None) -> dict[str, Any]:
    """The root-VM AMI, baked if this account does not have it; call it before a box starts."""
    ec2 = ec2 or ec2_client(region)
    return find_image(ec2, root_ami_name()) or bake_root_image(ec2, log=log, region=region, control=control)


def prune_root_images(ec2: Any, keep: str | None = None, log: Callable[[str], None] = print,
                      apply: bool = True) -> list[str]:
    """Keep one root-VM image: `keep`, else the one the code names now, else the newest. Every other AMI of this
    account that carries the lane's own image tag is deregistered and its snapshots are deleted. The ids removed
    (or, without `apply`, that would be). An image without pickfit's tags is never touched."""
    images = [i for i in ec2.describe_images(Owners=["self"], Filters=[
        {"Name": f"tag:{IMAGE_KIND_TAG}", "Values": [NET_KIND]}]).get("Images", [])
        if _tag(i, IMAGE_KIND_TAG) == NET_KIND and _tag(i, "pickfit") == "verify"]
    if not images:
        return []
    if keep is None:
        current = next((i["ImageId"] for i in images if i.get("Name") == root_ami_name()), None)
        keep = current or max(images, key=lambda i: str(i.get("CreationDate", "")))["ImageId"]
    removed: list[str] = []
    for image in images:
        if image["ImageId"] == keep or image.get("State") == "pending":
            continue
        snapshots = [m["Ebs"]["SnapshotId"] for m in image.get("BlockDeviceMappings", [])
                     if m.get("Ebs", {}).get("SnapshotId")]
        if apply:
            ec2.deregister_image(ImageId=image["ImageId"])
            for snapshot in snapshots:
                try:
                    ec2.delete_snapshot(SnapshotId=snapshot)
                except Exception as error:
                    log(f"ec2: snapshot {snapshot} not deleted ({_code(error) or type(error).__name__})")
        removed += [image["ImageId"], *snapshots]
    if removed:
        log(f"ec2: {'removed' if apply else 'would remove'} older root-VM images: {' '.join(removed)}")
    return removed


# -- the box


class Ec2RootBox(RootVmBox):
    """A full-privilege VM box on EC2: RootVmBox on an Ec2RootMachine."""

    def __init__(self, *, limits: BoxLimits = BoxLimits(), tags: dict[str, str] | None = None,
                 region: str | None = None, ec2: Any = None, control: str | None = None, extra_disk_gb: int = 0,
                 kvm: bool = False, cap_usd: float | None = None, log: Callable[[str], None] = print,
                 **box_kwargs: Any) -> None:
        machine = Ec2RootMachine(cores=limits.cpus, memory_mb=limits.memory_mb, lifetime_s=limits.lifetime_s,
                                 tags=tags, region=region, ec2=ec2, control=control, extra_disk_gb=extra_disk_gb,
                                 kvm=kvm, log=lambda line: self.log(line))
        super().__init__(machine, limits=limits, run_id=identity(tags)[0], cap_usd=cap_usd, log=log, **box_kwargs)

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
