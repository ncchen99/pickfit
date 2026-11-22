"""The full-privilege VM box on EC2 (ec2_root.py), its reaper (ec2_reaper.py) and its lane, against a fake EC2
API and a fake ssh. Nothing leaves the process: no AWS call, no connection."""

from __future__ import annotations

import datetime
import re
import shlex
import time
from pathlib import Path
from typing import Any

import pytest

from pickfit import sbom
from pickfit.verify import ec2_machine as e
from pickfit.verify import ec2_reaper as reaper
from pickfit.verify import ec2_root as r
from pickfit.verify import root_box as rb
from pickfit.verify import ssh_machine as s
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.machine import BLOCKED_NETS, ONLINE_CIDRS
from test_verify_ec2 import CONTROL, AwsError, FakeEc2, FakeSsh, no_waiting  # noqa: F401 (the fixture applies here)

ROOT_AMI = {"ImageId": "ami-root", "Name": r.root_ami_name(), "State": "available", "RootDeviceName": "/dev/xvda",
            "CreationDate": "2026-11-21", "Tags": [{"Key": "pickfit", "Value": "verify"},
                                                   {"Key": r.IMAGE_KIND_TAG, "Value": r.NET_KIND}],
            "BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-root"}}]}
READY = b"sudo_uid 0\ninit systemd\nsystemd running\ndocker 26.1.5\n"


def _tags(spec: list[dict[str, Any]] | None, resource: str) -> list[dict[str, str]]:
    return next((t["Tags"] for t in spec or [] if t["ResourceType"] == resource), [])


class FakeRootEc2(FakeEc2):
    """FakeEc2 plus what the lane's own network needs: VPCs, subnets, network ACLs, and instances that live in a
    subnet behind the groups of a network interface."""

    def __init__(self, images: list[dict[str, Any]] | None = None) -> None:
        super().__init__(images if images is not None else [dict(ROOT_AMI)])
        self.vpcs: dict[str, dict[str, Any]] = {}
        self.subnets: dict[str, dict[str, Any]] = {}
        self.acls: dict[str, dict[str, Any]] = {}
        self.snapshots_deleted: list[str] = []
        self.taken_cidrs: set[str] = set()  # a subnet there is refused as a conflict
        self.groups_stuck = False  # a group change EC2 accepts and does not apply

    # -- the VPC

    def describe_vpcs(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_vpcs", kw)
        filters = {f["Name"]: f["Values"] for f in kw.get("Filters", [])}
        if "is-default" in filters:
            return {"Vpcs": [{"VpcId": "vpc-1"}]}
        return {"Vpcs": [v for v in self.vpcs.values()
                         if all(e._tag(v, name[4:]) in values for name, values in filters.items()
                                if name.startswith("tag:"))]}

    def create_vpc(self, **kw: Any) -> dict[str, Any]:
        self._call("create_vpc", kw)
        vid = f"vpc-root{len(self.vpcs) + 1}"
        self.vpcs[vid] = {"VpcId": vid, "CidrBlock": kw["CidrBlock"], "Tags": _tags(kw.get("TagSpecifications"), "vpc"),
                          "dns": True}
        self.acls[f"acl-default-{vid}"] = {"NetworkAclId": f"acl-default-{vid}", "VpcId": vid, "IsDefault": True,
                                           "Tags": [], "Associations": [], "Entries": [
                                               {"RuleNumber": 100, "Egress": eg, "RuleAction": "allow", "Protocol": "-1",
                                                "CidrBlock": "0.0.0.0/0"} for eg in (False, True)]}
        return {"Vpc": {"VpcId": vid}}

    def modify_vpc_attribute(self, **kw: Any) -> None:
        self._call("modify_vpc_attribute", kw)
        if "EnableDnsSupport" in kw:
            self.vpcs[kw["VpcId"]]["dns"] = kw["EnableDnsSupport"]["Value"]

    def describe_vpc_attribute(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_vpc_attribute", kw)
        return {"EnableDnsSupport": {"Value": self.vpcs[kw["VpcId"]]["dns"]}}

    def create_internet_gateway(self, **kw: Any) -> dict[str, Any]:
        self._call("create_internet_gateway", kw)
        return {"InternetGateway": {"InternetGatewayId": "igw-1"}}

    def attach_internet_gateway(self, **kw: Any) -> None:
        self._call("attach_internet_gateway", kw)

    def describe_route_tables(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_route_tables", kw)
        return {"RouteTables": [{"RouteTableId": "rtb-main"}]}

    def create_route(self, **kw: Any) -> None:
        self._call("create_route", kw)

    def create_dhcp_options(self, **kw: Any) -> dict[str, Any]:
        self._call("create_dhcp_options", kw)
        return {"DhcpOptions": {"DhcpOptionsId": "dopt-1"}}

    def associate_dhcp_options(self, **kw: Any) -> None:
        self._call("associate_dhcp_options", kw)

    # -- security groups, where a rule is one port

    def describe_security_groups(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_security_groups", kw)
        ids = kw.get("GroupIds")
        names = next((f["Values"] for f in kw.get("Filters", []) if f["Name"] == "group-name"), None)
        return {"SecurityGroups": [g for g in self.groups.values() if (ids is None or g["GroupId"] in ids)
                                   and (names is None or g["GroupName"] in names)]}

    def revoke_security_group_ingress(self, **kw: Any) -> None:
        self._call("revoke_security_group_ingress", kw)
        group = self.groups[kw["GroupId"]]
        for gone in kw["IpPermissions"]:
            cidrs = {x["CidrIp"] for x in gone["IpRanges"]}
            for permission in group["IpPermissions"]:
                if (permission["IpProtocol"], permission.get("FromPort"), permission.get("ToPort")) == (
                        gone["IpProtocol"], gone.get("FromPort"), gone.get("ToPort")):
                    permission["IpRanges"] = [x for x in permission["IpRanges"] if x["CidrIp"] not in cidrs]
        group["IpPermissions"] = [p for p in group["IpPermissions"] if p["IpRanges"]]

    # -- subnets and network ACLs

    def create_subnet(self, **kw: Any) -> dict[str, Any]:
        self._call("create_subnet", kw)
        if kw["CidrBlock"] in self.taken_cidrs or any(x["CidrBlock"] == kw["CidrBlock"] for x in self.subnets.values()):
            raise AwsError("InvalidSubnet.Conflict")
        sid = f"subnet-{len(self.subnets) + 1}"
        self.subnets[sid] = {"SubnetId": sid, "VpcId": kw["VpcId"], "CidrBlock": kw["CidrBlock"],
                             "Tags": _tags(kw.get("TagSpecifications"), "subnet")}
        default = next(a for a in self.acls.values() if a["IsDefault"] and a["VpcId"] == kw["VpcId"])
        default["Associations"].append({"NetworkAclAssociationId": f"aclassoc-{sid}-0", "SubnetId": sid})
        return {"Subnet": {"SubnetId": sid}}

    def describe_subnets(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_subnets", kw)
        filters = {f["Name"]: f["Values"] for f in kw.get("Filters", [])}
        return {"Subnets": [x for x in self.subnets.values() if x["VpcId"] in filters.get("vpc-id", [x["VpcId"]])
                            and all(e._tag(x, name[4:]) in values for name, values in filters.items()
                                    if name.startswith("tag:"))]}

    def delete_subnet(self, **kw: Any) -> None:
        self._call("delete_subnet", kw)
        sid = kw["SubnetId"]
        if any(i.get("SubnetId") == sid and i["State"]["Name"] != "terminated" for i in self.instances.values()):
            raise AwsError("DependencyViolation")
        self.subnets.pop(sid)
        for acl in self.acls.values():
            acl["Associations"] = [a for a in acl["Associations"] if a["SubnetId"] != sid]

    def describe_network_acls(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_network_acls", kw)
        filters = {f["Name"]: f["Values"] for f in kw.get("Filters", [])}
        found = [a for a in self.acls.values() if a["VpcId"] in filters.get("vpc-id", [a["VpcId"]])]
        if "association.subnet-id" in filters:
            found = [a for a in found if any(x["SubnetId"] in filters["association.subnet-id"]
                                             for x in a["Associations"])]
        return {"NetworkAcls": found}

    def create_network_acl(self, **kw: Any) -> dict[str, Any]:
        self._call("create_network_acl", kw)
        aid = f"acl-{len(self.acls) + 1}"
        deny = [{"RuleNumber": 32767, "Egress": eg, "RuleAction": "deny", "Protocol": "-1", "CidrBlock": "0.0.0.0/0"}
                for eg in (False, True)]
        self.acls[aid] = {"NetworkAclId": aid, "VpcId": kw["VpcId"], "IsDefault": False, "Associations": [],
                          "Tags": _tags(kw.get("TagSpecifications"), "network-acl"), "Entries": deny}
        return {"NetworkAcl": {"NetworkAclId": aid}}

    def create_network_acl_entry(self, **kw: Any) -> None:
        self._call("create_network_acl_entry", kw)
        self.acls[kw["NetworkAclId"]]["Entries"].append({k: v for k, v in kw.items() if k != "NetworkAclId"})

    def replace_network_acl_association(self, **kw: Any) -> dict[str, Any]:
        self._call("replace_network_acl_association", kw)
        for acl in self.acls.values():
            for association in list(acl["Associations"]):
                if association["NetworkAclAssociationId"] == kw["AssociationId"]:
                    acl["Associations"].remove(association)
                    base, n = association["NetworkAclAssociationId"].rsplit("-", 1)
                    new = {"NetworkAclAssociationId": f"{base}-{int(n) + 1}", "SubnetId": association["SubnetId"]}
                    self.acls[kw["NetworkAclId"]]["Associations"].append(new)
                    return {"NewAssociationId": new["NetworkAclAssociationId"]}
        raise AwsError("InvalidAssociationID.NotFound")

    def delete_network_acl(self, **kw: Any) -> None:
        self._call("delete_network_acl", kw)
        self.acls.pop(kw["NetworkAclId"])

    def acl_of(self, subnet: str) -> str:
        return next(a["NetworkAclId"] for a in self.acls.values()
                    if any(x["SubnetId"] == subnet for x in a["Associations"]))

    # -- instances behind a network interface

    def run_instances(self, **kw: Any) -> dict[str, Any]:
        if "NetworkInterfaces" not in kw:  # a builder: an ordinary instance in the default VPC
            return super().run_instances(**kw)
        self._call("run_instances", kw)
        iid = f"i-{len(self.instances) + 1}"
        nic = kw["NetworkInterfaces"][0]
        self.instances[iid] = {
            "InstanceId": iid, "State": {"Name": "running"}, "PublicIpAddress": f"198.51.100.{len(self.instances) + 9}",
            "PrivateIpAddress": f"10.213.0.{len(self.instances) + 4}", "Groups": list(nic["Groups"]),
            "SubnetId": nic["SubnetId"], "VpcId": self.subnets[nic["SubnetId"]]["VpcId"],
            "Tags": _tags(kw["TagSpecifications"], "instance"), "InstanceType": kw["InstanceType"],
            "UserData": kw["UserData"], "LaunchTime": datetime.datetime.now(datetime.UTC),
            "BlockDeviceMappings": [{"DeviceName": m["DeviceName"], "Ebs": {
                "DeleteOnTermination": m["Ebs"]["DeleteOnTermination"]}} for m in kw["BlockDeviceMappings"]]}
        return {"Instances": [{"InstanceId": iid}]}

    def describe_instances(self, **kw: Any) -> dict[str, Any]:
        found = super().describe_instances(**kw)["Reservations"][0]["Instances"]
        for f in kw.get("Filters", []):
            if f["Name"] in ("vpc-id", "subnet-id"):
                key = "VpcId" if f["Name"] == "vpc-id" else "SubnetId"
                found = [i for i in found if i.get(key) in f["Values"]]
        described = [{**i, "SecurityGroups": [{"GroupId": g} for g in i.get("Groups", [])],
                      "MetadataOptions": {"HttpEndpoint": self.imds, "State": "applied"}} for i in found]
        return {"Reservations": [{"Instances": described}]}

    def modify_instance_attribute(self, **kw: Any) -> None:
        if self.groups_stuck and "Groups" in kw:
            self._call("modify_instance_attribute", kw)
            return
        super().modify_instance_attribute(**kw)

    # -- images

    def describe_images(self, **kw: Any) -> dict[str, Any]:
        tags = {f["Name"][4:]: f["Values"] for f in kw.get("Filters", []) if f["Name"].startswith("tag:")}
        plain = {**kw, "Filters": [f for f in kw.get("Filters", []) if not f["Name"].startswith("tag:")]}
        found = super().describe_images(**plain)["Images"]
        return {"Images": [i for i in found if all(e._tag(i, key) in values for key, values in tags.items())]}

    def create_image(self, **kw: Any) -> dict[str, Any]:
        self._call("create_image", kw)
        self.images.append({"ImageId": "ami-baked", "Name": kw["Name"], "State": "available",
                            "RootDeviceName": "/dev/xvda", "CreationDate": "2026-11-22",
                            "Tags": _tags(kw.get("TagSpecifications"), "image"),
                            "BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-baked"}}]})
        return {"ImageId": "ami-baked"}

    def deregister_image(self, **kw: Any) -> None:
        self._call("deregister_image", kw)
        self.images = [i for i in self.images if i["ImageId"] != kw["ImageId"]]

    def delete_snapshot(self, **kw: Any) -> None:
        self._call("delete_snapshot", kw)
        self.snapshots_deleted.append(kw["SnapshotId"])


class FakeRootSsh(FakeSsh):
    """FakeSsh whose egress probe answers from the lane's network: a new connection opens while the instance wears
    the online groups and its subnet is not behind an offline ACL."""

    def __init__(self, ec2: FakeRootEc2) -> None:
        super().__init__(ec2)
        self.replies["sudo_uid"] = (0, READY, b"")
        self.replies["lsblk"] = (0, b"/dev/nvme1n1 8589934592\n", b"")
        self.vm_says: bytes | None = None  # what the VM answers a metadata request, whatever EC2's setting is

    def popen(self, argv: list[str], **kw: Any) -> Any:
        proc = super().popen(argv, **kw)
        remote = shlex.split(argv[-1])
        if e.EGRESS_PROBE in remote:
            ec2 = self.ec2
            assert isinstance(ec2, FakeRootEc2)
            box = ec2.instances[self.box or next(iter(ec2.instances))]
            online = {g["GroupId"] for g in ec2.groups.values() if g["GroupName"] == r.GROUPS["https"]}
            behind_default = ec2.acls[ec2.acl_of(box["SubnetId"])]["IsDefault"]
            is_open = bool(set(box["Groups"]) & online and behind_default) or self.stuck_open
            proc.stdout.data = b"open\n" if is_open else b""
        if e.IMDS_PROBE in remote and self.vm_says is not None:
            proc.stdout.data = self.vm_says
        return proc


def machine(ec2: FakeRootEc2 | None = None, ssh: FakeRootSsh | None = None,
            **kw: Any) -> tuple[r.Ec2RootMachine, FakeRootEc2, FakeRootSsh]:
    ec2 = ec2 or FakeRootEc2()
    ssh = ssh or FakeRootSsh(ec2)
    made = r.Ec2RootMachine(**{"cores": 2, "memory_mb": 2048, "lifetime_s": 1200, "ec2": ec2, "control": CONTROL,
                               "popen": ssh.popen, "run": ssh.run, "log": lambda line: None, **kw})
    return made, ec2, ssh


def box(ec2: FakeRootEc2 | None = None, **kw: Any) -> tuple[r.Ec2RootBox, FakeRootEc2, FakeRootSsh]:
    ec2 = ec2 or FakeRootEc2()
    ssh = FakeRootSsh(ec2)
    made = r.Ec2RootBox(ec2=ec2, control=CONTROL, log=lambda line: None, **kw)
    made.machine.popen, made.machine.run_local = ssh.popen, ssh.run
    return made, ec2, ssh


def group(ec2: FakeRootEc2, role: str) -> dict[str, Any]:
    return next(g for g in ec2.groups.values() if g["GroupName"] == r.GROUPS[role])


def launch(ec2: FakeRootEc2) -> dict[str, Any]:
    return next(k for n, k in ec2.calls if n == "run_instances")


# -- the launch


def test_an_instance_has_no_identity_and_is_alone_in_a_subnet_behind_the_lanes_groups():
    m, ec2, _ = machine(tags={"pickfit.run": "verify-hal0-20261121-101500-ab12", "pickfit.role": "agent"})
    m.start()
    kw = launch(ec2)
    assert "IamInstanceProfile" not in kw and "KeyName" not in kw  # no AWS identity, no key pair
    assert "SecurityGroupIds" not in kw and "SubnetId" not in kw  # both are the interface's
    [nic] = kw["NetworkInterfaces"]
    control, http, https = (group(ec2, role)["GroupId"] for role in ("control", "http", "https"))
    assert nic["Groups"] == [control, http, https] and nic["AssociatePublicIpAddress"] is True
    assert nic["SubnetId"] == "subnet-1" and ec2.subnets["subnet-1"]["VpcId"] == "vpc-root1"  # never the default VPC
    assert nic["DeleteOnTermination"] is True and kw["InstanceInitiatedShutdownBehavior"] == "terminate"
    assert all(d["Ebs"]["DeleteOnTermination"] for d in kw["BlockDeviceMappings"]) and len(kw["BlockDeviceMappings"]) == 1
    assert kw["ImageId"] == "ami-root" and kw["InstanceType"] == "c7i-flex.large" and "CpuOptions" not in kw
    # The service is on only for the boot, with a token and one hop; _seal turns it off (the next test).
    assert kw["MetadataOptions"] == {"HttpEndpoint": "enabled", "HttpTokens": "required", "HttpPutResponseHopLimit": 1,
                                     "HttpProtocolIpv6": "disabled", "InstanceMetadataTags": "disabled"}
    for resource in ("instance", "volume", "network-interface"):
        tags = {t["Key"]: t["Value"] for t in _tags(kw["TagSpecifications"], resource)}
        assert tags["pickfit"] == "verify" and tags["pickfit:role"] == "rootvm"  # what the reaper knows it by
        assert tags[e.RUN_TAG] == "verify-hal0-20261121-101500-ab12" and tags[e.PURPOSE_TAG] == "agent"
        assert tags[e.EXPIRES_TAG].isdigit()
    assert "ssh_authorized_keys" in kw["UserData"] and m.machine_id == "i-1" and m.image == ROOT_AMI["Name"]
    assert m.capabilities == rb.FULL and m.cut == "stateless" and m.lane == "linux-root"


def test_kvm_is_asked_for_with_the_cpu_option_aws_documents():
    m, ec2, _ = machine(kvm=True)
    m.start()
    assert launch(ec2)["CpuOptions"] == {"NestedVirtualization": "enabled"}


def test_the_metadata_service_is_off_at_the_instance_before_anything_runs_and_ec2_says_so():
    m, ec2, ssh = machine()
    m.start()
    assert ("modify_instance_metadata_options", {"InstanceId": "i-1", "HttpEndpoint": "disabled"}) in ec2.calls
    assert m.metadata_answer == "HTTP/1.1 403"  # what root on the VM got
    assert m.outside_view()["metadata_endpoint"] == "disabled"  # what EC2 says
    # Nothing of pickfit's holds it inside: no container, no rule on the VM that root could remove.
    assert not any(remote[3:5] == [s.DOCKER, "run"] or s.NFT in remote for remote in ssh.remote)


def test_a_start_is_refused_unless_ec2_itself_says_the_service_is_off():
    m, ec2, ssh = machine()
    ec2.modify_instance_metadata_options = lambda **kw: None  # type: ignore[method-assign]  (accepted, not applied)
    ssh.vm_says = b"HTTP/1.1 403"  # the VM's own answer looks right: it is not what the start goes by
    with pytest.raises(BoxError, match="does not say the metadata service"):
        m.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    m2, ec2, _ = machine()
    ec2.modify_instance_metadata_options = lambda **kw: None  # type: ignore[method-assign]  (never turned off)
    with pytest.raises(BoxError, match="metadata service"):
        m2.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_root_commands_run_on_the_vm_itself():
    m, _, ssh = machine()
    m.start()
    m.spawn(["/usr/bin/id", "-u"], 30, workdir="/home/sbx")
    assert ssh.remote[-1] == ["/usr/bin/env", "--chdir", "/home/sbx", "/usr/bin/timeout", "--signal=KILL", "30",
                              "/usr/bin/id", "-u"]


# -- the network


def test_the_lanes_network_is_made_once_with_no_amazon_dns_and_only_dns_http_and_https_out():
    ec2 = FakeRootEc2()
    net = r.ensure_network(ec2, CONTROL, lambda line: None)
    assert net.vpc == "vpc-root1" and ec2.vpcs[net.vpc]["dns"] is False  # the resolver no firewall filters is off
    dhcp = next(k for n, k in ec2.calls if n == "create_dhcp_options")
    assert dhcp["DhcpConfigurations"] == [{"Key": "domain-name-servers", "Values": list(r.RESOLVERS)}]
    assert ("create_route", {"RouteTableId": "rtb-main", "DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-1"}
            ) in ec2.calls
    out = {role: e._rules(group(ec2, role)["IpPermissionsEgress"]) for role in r.GROUPS}
    assert out["control"] == set() and out["offline"] == set()
    resolvers = {f"{a}/32" for a in r.RESOLVERS}
    assert out["http"] == ({("tcp", 80, 80, c) for c in ONLINE_CIDRS}
                           | {(p, 53, 53, a) for p in ("tcp", "udp") for a in resolvers})
    assert out["https"] == {("tcp", 443, 443, c) for c in ONLINE_CIDRS}
    every = out["http"] | out["https"]
    assert {(rule[0], rule[1]) for rule in every} == {("tcp", 80), ("tcp", 443), ("tcp", 53), ("udp", 53)}
    assert not any(rule[1] <= 25 <= rule[2] for rule in every)  # no SMTP
    assert all(len(rules) <= r.GROUP_RULE_QUOTA for rules in out.values())  # why online is two groups
    # No private range, no link-local, no other instance: every destination is public IPv4.
    import ipaddress

    blocked = [ipaddress.ip_network(n) for n in BLOCKED_NETS]
    assert not any(ipaddress.ip_network(rule[3]).overlaps(b) for rule in every for b in blocked)
    # In: SSH from the harness on the control group, and nothing at all on the others (not even from each other).
    assert e._rules(group(ec2, "control")["IpPermissions"]) == {("tcp", 22, 22, CONTROL)}
    assert all(group(ec2, role)["IpPermissions"] == [] for role in ("http", "https", "offline"))
    assert net.wear[True] == [net.groups["control"], net.groups["http"], net.groups["https"]]
    assert net.wear[False] == [net.groups["control"], net.groups["offline"]]
    # The offline ACL lets only the harness's address through; the online one is the VPC's own, which allows all.
    assert ec2.acls[net.online_acl]["IsDefault"] and not ec2.acls[net.offline_acl]["IsDefault"]
    assert r._acl_entries(ec2.acls[net.offline_acl]) == {(False, "allow", "6", CONTROL, 1, 65535),
                                                         (True, "allow", "6", CONTROL, 1024, 65535)}
    ec2.calls.clear()
    again = r.ensure_network(ec2, CONTROL, lambda line: None)
    assert (again.vpc, again.groups, again.offline_acl) == (net.vpc, net.groups, net.offline_acl)
    assert not {n for n in ec2.names() if n.startswith(("create_", "authorize_", "modify_"))}


def test_a_network_someone_widened_is_refused():
    def fresh() -> tuple[FakeRootEc2, r.RootNet]:
        ec2 = FakeRootEc2()
        return ec2, r.ensure_network(ec2, CONTROL, lambda line: None)

    ec2, net = fresh()
    ec2.vpcs[net.vpc]["dns"] = True  # Amazon's resolver is back: a way out no group or ACL closes
    with pytest.raises(BoxError, match="Amazon's DNS"):
        r.ensure_network(ec2, CONTROL)
    ec2, net = fresh()
    group(ec2, "https")["IpPermissionsEgress"].append(
        {"IpProtocol": "tcp", "FromPort": 25, "ToPort": 25, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]})
    with pytest.raises(BoxError, match=r.GROUPS["https"]):
        r.ensure_network(ec2, CONTROL)
    ec2, net = fresh()
    group(ec2, "offline")["IpPermissionsEgress"] = [{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]
    with pytest.raises(BoxError, match=r.GROUPS["offline"]):
        r.ensure_network(ec2, CONTROL)
    ec2, net = fresh()
    group(ec2, "control")["IpPermissions"].append(
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]})
    with pytest.raises(BoxError, match=r.GROUPS["control"]):
        r.ensure_network(ec2, CONTROL)
    ec2, net = fresh()
    group(ec2, "http")["IpPermissions"].append(  # the boxes could reach each other
        {"IpProtocol": "-1", "UserIdGroupPairs": [{"GroupId": net.groups["http"]}]})
    with pytest.raises(BoxError, match=r.GROUPS["http"]):
        r.ensure_network(ec2, CONTROL)
    ec2, net = fresh()
    ec2.acls[net.offline_acl]["Entries"].append({"RuleNumber": 90, "Egress": True, "RuleAction": "allow",
                                                 "Protocol": "-1", "CidrBlock": "0.0.0.0/0"})
    with pytest.raises(BoxError, match="network ACL"):
        r.ensure_network(ec2, CONTROL)


def test_a_subnet_is_made_for_each_box_at_a_free_place():
    ec2 = FakeRootEc2()
    net = r.ensure_network(ec2, CONTROL, lambda line: None)
    real, tries = ec2.create_subnet, []

    def taken_twice(**kw: Any) -> dict[str, Any]:
        tries.append(kw["CidrBlock"])
        if len(tries) < 3:
            raise AwsError("InvalidSubnet.Conflict")
        return real(**kw)

    ec2.create_subnet = taken_twice  # type: ignore[method-assign]
    subnet = r.make_subnet(ec2, net, {"pickfit": "verify"})
    assert len(tries) == 3 and tries[-1].endswith("/28") and tries[-1].startswith("10.213.")
    tags = {t["Key"]: t["Value"] for t in ec2.subnets[subnet]["Tags"]}
    assert tags[r.NET_TAG] == r.NET_KIND and tags[r.MADE_AT_TAG].isdigit()
    ec2.create_subnet = lambda **kw: (_ for _ in ()).throw(AwsError("InvalidSubnet.Conflict"))  # type: ignore[method-assign]
    with pytest.raises(BoxError, match="no free"):
        r.make_subnet(ec2, net, {})


# -- the cut


def test_the_cut_moves_the_subnet_to_the_offline_acl_and_swaps_the_groups_all_outside_the_vm():
    m, ec2, ssh = machine()
    m.start()
    net = m.net
    assert net is not None
    before = len(ssh.remote)
    ec2.calls.clear()
    m.set_egress(False)
    changes = [n for n in ec2.names() if n in ("replace_network_acl_association", "modify_instance_attribute")]
    assert changes == ["replace_network_acl_association", "modify_instance_attribute"]  # the ACL first: it is stateless
    assert ec2.instances["i-1"]["Groups"] == [net.groups["control"], net.groups["offline"]]
    assert ec2.acl_of("subnet-1") == net.offline_acl
    assert m.egress_view() == {"groups": sorted([net.groups["control"], net.groups["offline"]]), "acl": net.offline_acl}
    ran = ssh.remote[before:]
    assert all(remote[3:] == ["/usr/bin/bash", "-c", e.EGRESS_PROBE] for remote in ran)  # the VM is only asked
    assert not any(s.CUT_TABLE in " ".join(remote) for remote in ran)  # no rule of the VM's own is part of the cut
    ec2.calls.clear()
    m.set_egress(True)
    changes = [n for n in ec2.names() if n in ("replace_network_acl_association", "modify_instance_attribute")]
    assert changes == ["modify_instance_attribute", "replace_network_acl_association"]
    assert ec2.instances["i-1"]["Groups"] == net.wear[True] and ec2.acl_of("subnet-1") == net.online_acl
    m.set_egress(False)  # the association's id changed with each swap, and the next one still finds it
    assert ec2.acl_of("subnet-1") == net.offline_acl


def test_a_cut_that_is_not_made_is_an_error():
    m, ec2, _ = machine()
    m.start()
    ec2.fail["replace_network_acl_association"] = AwsError("UnauthorizedOperation")
    with pytest.raises(BoxError, match="UnauthorizedOperation"):
        m.set_egress(False)
    ec2.fail.clear()
    m.close()
    m2, ec2, _ = machine()
    m2.start()
    ec2.groups_stuck = True  # EC2 takes the call and the instance still wears the online groups
    with pytest.raises(BoxError, match="does not describe i-1 as offline"):
        m2.set_egress(False)
    m2.close()
    m3, ec2, ssh = machine()
    m3.start()
    ssh.stuck_open = True  # EC2 describes it as cut, and root on the VM still opens a connection
    with pytest.raises(BoxError, match="closing"):
        m3.set_egress(False)


# -- teardown


def test_close_terminates_the_instance_closes_its_row_and_gives_its_slot_back():
    from pickfit.ledger import box_ledger

    m, ec2, _ = machine(tags={"pickfit.run": "verify-hal0-20261121-101500-ab12", "pickfit.role": "replay"})
    m.start()
    assert m.state() == "running" and m.slot is not None and m.slot.held
    held = m.slot
    m.close()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated" and m.state() == "terminated"
    assert not held.held and m.slot is None
    [row] = box_ledger().boxes()
    assert row["end_note"] == "closed" and row["est_usd"] > 0
    m.close()  # twice is fine
    assert ec2.names().count("terminate_instances") == 1
    # The subnet could not go while its instance was shutting down in the real EC2; here it went at once. Either
    # way the sweep finds what is left (test_the_sweep_...).
    assert "delete_subnet" in ec2.names()


def test_a_start_that_fails_leaves_no_instance_behind():
    b, ec2, ssh = box()
    ssh.replies["sudo_uid"] = (0, b"sudo_uid 1000\ninit systemd\nsystemd running\ndocker 26.1.5\n", b"")
    with pytest.raises(BoxError, match="the box user's sudo"):
        b.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated" and b.ended == "terminated"
    m, ec2, ssh = machine()
    ssh.replies["is-active pickfit-lifetime.timer"] = (3, b"inactive\n", b"")
    with pytest.raises(BoxError, match="poweroff is not armed"):
        m.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    m2, ec2, _ = machine()
    ec2.fail["run_instances"] = AwsError("InsufficientInstanceCapacity")
    with pytest.raises(BoxError, match="InsufficientInstanceCapacity"):
        m2.start()
    assert ec2.instances == {} and ec2.subnets == {}  # the subnet made for it is gone too
    assert m2.slot is None  # and its slot is free again
    m3, _, _ = machine()
    assert m3.reserve() and m3.release_slot() is None


# -- the reaper


def instance(ec2: FakeEc2, iid: str, *, tags: dict[str, str], state: str = "running", age_s: float = 0.0) -> None:
    born = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_s)
    ec2.instances[iid] = {"InstanceId": iid, "State": {"Name": state}, "LaunchTime": born,
                          "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}


def test_the_reaper_never_touches_an_instance_without_pickfits_own_tags():
    ec2 = FakeRootEc2()
    now = time.time()
    ours = {"pickfit": "verify", "pickfit:role": "rootvm"}
    week = 7 * 24 * 3600
    # Another project's, however old and whatever it is called or half-tagged with.
    instance(ec2, "i-theirs", tags={"Name": "taigi-api"}, age_s=90 * 24 * 3600)
    instance(ec2, "i-theirs-untagged", tags={}, age_s=90 * 24 * 3600)
    instance(ec2, "i-lookalike-name", tags={"Name": "pickfit-rootvm"}, age_s=week)
    instance(ec2, "i-lookalike-role", tags={"pickfit:role": "rootvm", e.EXPIRES_TAG: "1"}, age_s=week)
    instance(ec2, "i-lookalike-mark", tags={"pickfit": "verify", e.EXPIRES_TAG: "1"}, age_s=week)
    instance(ec2, "i-lookalike-value", tags={"pickfit": "production", "pickfit:role": "box", e.EXPIRES_TAG: "1"},
             age_s=week)
    # pickfit's own.
    instance(ec2, "i-late", tags={**ours, e.EXPIRES_TAG: str(int(now - e.REAP_MARGIN_S - 60))})
    instance(ec2, "i-running", tags={**ours, e.EXPIRES_TAG: str(int(now + 600))})
    instance(ec2, "i-just-over", tags={**ours, e.EXPIRES_TAG: str(int(now - 10))})  # inside the margin
    instance(ec2, "i-no-lifetime-old", tags=ours, age_s=reaper.MAX_AGE_S + 60)
    instance(ec2, "i-no-lifetime-new", tags=ours, age_s=600)
    instance(ec2, "i-pool", tags={"pickfit": "verify", "pickfit:role": "pool", e.EXPIRES_TAG: str(int(now + week))},
             state="stopped", age_s=3 * 24 * 3600)
    instance(ec2, "i-gone", tags={**ours, e.EXPIRES_TAG: "1"}, state="terminated")
    theirs = [i for i in ec2.instances if i.startswith(("i-theirs", "i-lookalike"))]
    assert not any(reaper.ours(ec2.instances[i]) for i in theirs)

    would = reaper.reap_leaked(ec2, lambda line: None, now=now, apply=False)  # a dry run ends nothing
    assert sorted(i for i, _ in would) == ["i-late", "i-no-lifetime-old"] and "terminate_instances" not in ec2.names()
    lines: list[str] = []
    done = reaper.reap_leaked(ec2, lines.append, now=now)
    assert sorted(i for i, _ in done) == ["i-late", "i-no-lifetime-old"]
    [ended] = [k["InstanceIds"] for n, k in ec2.calls if n == "terminate_instances"]
    assert sorted(ended) == ["i-late", "i-no-lifetime-old"]
    states = {i: v["State"]["Name"] for i, v in ec2.instances.items()}
    assert all(states[i] == "running" for i in theirs)  # exactly as they were
    assert states["i-running"] == states["i-just-over"] == states["i-no-lifetime-new"] == "running"
    assert states["i-pool"] == "stopped"
    assert any("past its lifetime" in line for line in lines) and any("no lifetime tag" in line for line in lines)
    # Even if EC2's own filter returned everything, the tags are checked again on what came back.
    ec2.describe_instances = lambda **kw: {"Reservations": [{"Instances": list(ec2.instances.values())}]}  # type: ignore[method-assign]
    ec2.calls.clear()
    assert reaper.reap_leaked(ec2, lambda line: None, now=now) == [] and "terminate_instances" not in ec2.names()


def test_every_start_reaps_what_earlier_boxes_left_and_a_reaper_that_fails_does_not_stop_it():
    m, ec2, _ = machine()
    instance(ec2, "i-leaked", tags={"pickfit": "verify", "pickfit:role": "rootvm", e.EXPIRES_TAG: "1"})
    instance(ec2, "i-theirs", tags={"Name": "taigi-api"}, age_s=10**7)
    m.start()
    assert ec2.instances["i-leaked"]["State"]["Name"] == "terminated"
    assert ec2.instances["i-theirs"]["State"]["Name"] == "running"
    m.close()
    lines: list[str] = []
    m2, ec2, _ = machine(log=lines.append)
    ec2.fail["describe_subnets"] = AwsError("RequestLimitExceeded")
    ec2.vpcs["vpc-root1"] = {"VpcId": "vpc-root1", "dns": False, "Tags": [
        {"Key": "pickfit", "Value": "verify"}, {"Key": r.NET_TAG, "Value": r.NET_KIND}]}
    ec2.acls["acl-default"] = {"NetworkAclId": "acl-default", "VpcId": "vpc-root1", "IsDefault": True, "Tags": [],
                               "Associations": [], "Entries": []}
    m2.start()
    assert m2.machine_id is not None and any("ec2 root reap" in line for line in lines)


def test_the_sweep_removes_what_boxes_left_in_the_lanes_network_and_nothing_else():
    m, ec2, _ = machine()
    m.start()
    net = m.net
    assert net is not None
    old = str(int(time.time() - r.SUBNET_SETTLE_S - 60))
    lane = [{"Key": "pickfit", "Value": "verify"}, {"Key": r.NET_TAG, "Value": r.NET_KIND}]
    ec2.subnets["subnet-1"]["Tags"] = [*lane, {"Key": r.MADE_AT_TAG, "Value": old}]  # in use by the running box
    ec2.subnets["subnet-left"] = {"SubnetId": "subnet-left", "VpcId": net.vpc, "CidrBlock": "10.213.9.0/28",
                                  "Tags": [*lane, {"Key": r.MADE_AT_TAG, "Value": old}]}
    ec2.subnets["subnet-new"] = {"SubnetId": "subnet-new", "VpcId": net.vpc, "CidrBlock": "10.213.9.16/28",
                                 "Tags": [*lane, {"Key": r.MADE_AT_TAG, "Value": str(int(time.time()))}]}
    ec2.subnets["subnet-theirs"] = {"SubnetId": "subnet-theirs", "VpcId": net.vpc, "CidrBlock": "10.213.9.32/28",
                                    "Tags": []}
    m.probe_ingress(8080, True)  # this box's own probe, still open
    ec2.authorize_security_group_ingress(GroupId=net.groups["control"], IpPermissions=[
        {"IpProtocol": "tcp", "FromPort": 9000, "ToPort": 9000,
         "IpRanges": [{"CidrIp": CONTROL, "Description": f"{r.PROBE_RULE}i-gone 2026-11-20"}]}])
    week_ago = (datetime.date.today() - datetime.timedelta(days=8)).isoformat()
    for aid, control, made in (("acl-old", "198.51.100.1/32", week_ago), ("acl-recent", "198.51.100.2/32",
                                                                         datetime.date.today().isoformat())):
        ec2.acls[aid] = {"NetworkAclId": aid, "VpcId": net.vpc, "IsDefault": False, "Associations": [], "Entries": [],
                         "Tags": [*lane, {"Key": r.CONTROL_TAG, "Value": control}, {"Key": r.MADE_TAG, "Value": made}]}
    ec2.acls["acl-theirs"] = {"NetworkAclId": "acl-theirs", "VpcId": net.vpc, "IsDefault": False, "Associations": [],
                              "Entries": [], "Tags": []}
    would = r.sweep_network(ec2, CONTROL, lambda line: None, apply=False)
    assert "subnet-left" in ec2.subnets and "acl-old" in ec2.acls and len(would) == 3
    removed = r.sweep_network(ec2, CONTROL, lambda line: None)
    assert removed == would == ["subnet-left", f"probe rule 9000 {CONTROL}", "acl-old"]
    assert set(ec2.subnets) == {"subnet-1", "subnet-new", "subnet-theirs"}
    assert {"acl-recent", "acl-theirs", net.offline_acl, net.online_acl} <= set(ec2.acls) and "acl-old" not in ec2.acls
    assert m.probed_ports() == [8080]  # the live box's probe rule stayed, and SSH with it
    assert ("tcp", 22, 22, CONTROL) in e._rules(group(ec2, "control")["IpPermissions"])
    m.close()
    assert r.sweep_network(FakeRootEc2(), CONTROL, lambda line: None) == []  # a region the lane never ran in


# -- the lane limit


def test_a_third_instance_never_starts(monkeypatch):
    lines: list[str] = []
    first, _, _ = machine()
    second, _, _ = machine()
    first.start()
    second.start()
    third, ec2, _ = machine(log=lines.append)
    assert not third.reserve()  # now or not at all
    monkeypatch.setenv(e.SLOT_WAIT_ENV, "30")
    with pytest.raises(BoxError, match="no room for another EC2 machine"):
        third.start()
    assert "run_instances" not in ec2.names() and ec2.subnets == {}  # nothing of it was ever launched
    assert any("waiting for one to end" in line for line in lines)
    first.close()
    third, ec2, _ = machine()
    third.start()  # a record's replay starts once its agent's VM is gone
    assert ec2.instances["i-1"]["State"]["Name"] == "running"
    second.close()
    third.close()


def test_the_lanes_instances_share_the_two_slots_with_every_other_pickfit_machine_on_ec2(monkeypatch):
    from test_verify_ec2 import machine as plain_machine

    plain, _, _ = plain_machine()  # an ordinary EC2 box of another lane
    plain.start()
    root, _, _ = machine()
    root.start()
    monkeypatch.setenv(e.SLOT_WAIT_ENV, "5")
    another, ec2, _ = machine()
    with pytest.raises(BoxError, match="no room"):
        another.start()
    assert "run_instances" not in ec2.names()
    plain.close()
    root.close()


def test_the_lane_takes_one_record_at_a_time_and_nothing_routes_to_it_yet():
    from pathlib import Path

    from pickfit import lanes
    from pickfit.verify import cli

    lane = lanes.root_vm_lane(model=None)
    assert lane.concurrency == 1 == cli.ROOT_VM_CONCURRENCY and lane.name == "linux-root" and lane.os == "linux"
    assert lane.display is False and lane.name not in lanes.BOX_LANES and lane.name not in lanes.ALL_LANES
    made = lane.make_box(False)("run-1", "agent")
    assert isinstance(made, r.Ec2RootBox)
    # A human runs the limits test on a real instance before anything is sent here automatically.
    watch = (Path(lanes.__file__).parent / "watch.py").read_text(encoding="utf-8")
    assert "root_vm_lane" not in watch and "rootvm" not in watch and "ec2_root" not in watch


# -- the ledger and the price


def test_each_instance_has_a_row_in_the_lanes_own_ledger_lane_with_its_purpose():
    from pickfit.ledger import box_ledger

    run_id = "verify-hal0-20261121-101500-ab12"
    agent, ec2, _ = machine(tags={"pickfit.run": run_id, "pickfit.role": "agent"})
    agent.start()
    agent.close()
    replay, _, _ = machine(ec2=ec2, tags={"pickfit.run": run_id, "pickfit.role": "replay"})
    replay.start()
    rows = sorted(box_ledger().boxes(run_id=run_id), key=lambda row: row["provider_ref"])
    assert [(row["provider"], row["lane"], row["purpose"], row["provider_ref"]) for row in rows] == [
        ("ec2", "linux-root", "agent", "i-1"), ("ec2", "linux-root", "replay", "i-2")]
    assert rows[0]["slug"] == "hal0" and rows[0]["ended_at"] and rows[1]["ended_at"] is None
    assert rows[0]["vcpu"] == 2 and rows[0]["memory_gb"] == 4.0 and rows[0]["min_billed_s"] == e.MIN_BILLED_S
    assert rows[0]["rate_usd_per_hour"] == pytest.approx(agent.usd_per_second() * 3600, abs=1e-6)
    assert f"{r.DISK_GB} GB gp3" in rows[0]["rate_source"] and "c7i-flex.large" in rows[0]["rate_source"]
    assert rows[0]["est_usd"] == pytest.approx(agent.usd_per_second() * 60, rel=1e-3)  # billed a minute at least
    replay.close()
    assert box_ledger().run_usd(run_id) == pytest.approx(2 * agent.usd_per_second() * 60, rel=1e-3)


def test_the_instance_is_the_box_so_its_memory_is_the_types_own():
    m, _, _ = machine()
    assert m._price() == ("c7i-flex.large", 0.09606) and m._size() == (2, 2048)  # no host to reserve memory for
    assert machine(memory_mb=4096)[0]._price()[0] == "c7i-flex.large"  # 4 GiB fits a 4 GiB type whole
    assert machine(memory_mb=8192)[0]._price()[0] == "m7i-flex.large"
    assert 0.09606 < m.usd_per_second() * 3600 < 0.11  # the instance, its address and its disk
    with pytest.raises(ValueError, match="price"):
        machine(region="eu-west-3")


# -- the extra disk


def test_an_extra_blank_volume_is_attached_on_request_and_deleted_with_the_instance():
    b, ec2, ssh = box(extra_disk_gb=8)
    b.start()
    root, extra = launch(ec2)["BlockDeviceMappings"]
    assert extra == {"DeviceName": r.EXTRA_DISK_DEVICE, "Ebs": {"VolumeSize": 8, "VolumeType": "gp3",
                                                               "DeleteOnTermination": True}}
    assert "SnapshotId" not in extra["Ebs"] and root["Ebs"]["VolumeSize"] == r.DISK_GB  # blank: nothing behind it
    assert b.extra_disk == "/dev/nvme1n1" and "blank 8 GB disk at /dev/nvme1n1" in b.describe()
    assert b.machine.outside_view()["volumes_deleted_with_it"] is True
    plain, _, _ = machine()
    assert b.usd_per_second() > plain.usd_per_second() and b.machine._disk_gb() == r.DISK_GB + 8  # it is billed
    assert b.evidence()["extra_disk"] == "/dev/nvme1n1"
    b.close()
    none, ec2, ssh = box(extra_disk_gb=8)
    ssh.replies["lsblk"] = (0, b"", b"")  # asked for and not there: the box cannot say which disk is safe to wipe
    with pytest.raises(BoxError, match="extra disk"):
        none.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    with pytest.raises(ValueError, match="extra disk"):
        machine(extra_disk_gb=r.EXTRA_DISK_MAX_GB + 1)
    b2, ec2, _ = box()
    b2.start()
    assert len(launch(ec2)["BlockDeviceMappings"]) == 1 and b2.extra_disk is None and "blank" not in b2.describe()


# -- the outside probe's rule


def test_a_probe_opens_one_port_to_the_harness_alone_and_closes_it_again():
    m, ec2, _ = machine()
    m.start()
    m.probe_ingress(8080, True)
    rules = e._rules(group(ec2, "control")["IpPermissions"])
    assert rules == {("tcp", 22, 22, CONTROL), ("tcp", 8080, 8080, CONTROL)} and m.probed_ports() == [8080]
    note = next(p for p in group(ec2, "control")["IpPermissions"] if p["FromPort"] == 8080)["IpRanges"][0]["Description"]
    assert note.startswith(f"{r.PROBE_RULE}i-1 ")
    r._check_groups({role: group(ec2, role) for role in r.GROUPS})  # still a network pickfit accepts
    m.probe_ingress(8080, True)  # twice is fine
    m.probe_ingress(8080, False)
    assert e._rules(group(ec2, "control")["IpPermissions"]) == {("tcp", 22, 22, CONTROL)} and m.probed_ports() == []
    for port in (22, 0, 70000):
        with pytest.raises(BoxError, match="not one an outside probe may open"):
            m.probe_ingress(port, True)
    ec2.fail["authorize_security_group_ingress"] = AwsError("UnauthorizedOperation")
    with pytest.raises(BoxError, match="UnauthorizedOperation"):
        m.probe_ingress(8081, True)


# -- the image


def test_the_image_is_baked_on_an_ordinary_builder_and_older_ones_are_removed_with_their_snapshots():
    debian = {"ImageId": "ami-debian", "Name": "debian-13-amd64-20261111-2659", "State": "available",
              "RootDeviceName": "/dev/xvda", "CreationDate": "2026-11-11"}
    lane = [{"Key": "pickfit", "Value": "verify"}, {"Key": r.IMAGE_KIND_TAG, "Value": r.NET_KIND}]
    old = {"ImageId": "ami-old", "Name": "pickfit-rootvm-host-000000000000", "State": "available", "Tags": lane,
           "CreationDate": "2026-11-01", "BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-old"}}]}
    box_image = {"ImageId": "ami-box", "Name": "pickfit-sbx-vm-abc-host-1", "State": "available",
                 "Tags": [{"Key": "pickfit", "Value": "verify"}], "BlockDeviceMappings": [
                     {"Ebs": {"SnapshotId": "snap-box"}}]}  # another lane's image
    theirs = {"ImageId": "ami-theirs", "Name": "taigi-base", "State": "available", "Tags": [],
              "BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-theirs"}}]}
    ec2 = FakeRootEc2(images=[debian, old, box_image, theirs])
    ssh = FakeRootSsh(ec2)
    image = r.bake_root_image(ec2, log=lambda line: None, control=CONTROL, popen=ssh.popen, run=ssh.run)
    assert image["Name"] == r.root_ami_name() and image["ImageId"] == "ami-baked"
    built = launch(ec2)
    assert built["ImageId"] == "ami-debian" and "NetworkInterfaces" not in built  # a builder is never a box
    stdin = [p.stdin.data.decode() for p in ssh.procs]
    assert stdin.index(r.ROOT_HOST_SETUP) < stdin.index(e.HOST_SEAL)
    made = next(k for n, k in ec2.calls if n == "create_image")
    assert {t["Key"]: t["Value"] for t in _tags(made["TagSpecifications"], "image")} == {
        "pickfit": "verify", "pickfit:image": r.root_ami_name(), r.IMAGE_KIND_TAG: r.NET_KIND}
    order = [n for n in ec2.names() if n in ("run_instances", "stop_instances", "create_image", "terminate_instances",
                                             "deregister_image")]
    assert order == ["run_instances", "stop_instances", "create_image", "terminate_instances", "deregister_image"]
    # Only the newest image of this kind is left; nothing of another lane's or another project's was touched.
    assert {i["ImageId"] for i in ec2.images} == {"ami-debian", "ami-box", "ami-theirs", "ami-baked"}
    assert ec2.snapshots_deleted == ["snap-old"]
    assert r.ensure_root_image(ec2, control=CONTROL)["ImageId"] == "ami-baked" and ec2.names().count("create_image") == 1
    # What the setup gives the box user, and what it must not hold.
    setup = r.ROOT_HOST_SETUP
    for needed in ("docker.io", "docker-compose", "sudo", "useradd --uid 1000", "usermod -aG docker sbx",
                   "NOPASSWD:ALL", "loginctl enable-linger sbx"):
        assert needed in setup
    assert "AKIA" not in setup and "aws" not in setup.lower().replace("ec2", "")
    # What pickfit/sbom.py runs in a replay box is here by the Dockerfile's releases and sums, at sbom.py's paths.
    dockerfile = (Path(r.__file__).with_name("sandbox.Dockerfile")).read_text(encoding="utf-8")
    sums = re.findall(r"echo '([0-9a-f]{64})  /tmp/(?:syft|cargo-audit|go)\.tgz'", dockerfile)
    assert len(sums) == 3 and all(f"echo '{digest}  /tmp/" in setup for digest in sums)
    assert "govulncheck@v1.9.0" in setup and "govulncheck@v1.9.0" in dockerfile
    for path in (sbom.SYFT, sbom.CARGO_AUDIT, sbom.PYTHON, sbom.NPM):
        assert path in setup
    assert "GOBIN=/usr/local/bin" in setup and sbom.GOVULNCHECK == "/usr/local/bin/govulncheck"
    assert r.root_ami_name().startswith("pickfit-rootvm-host-") and ":" not in r.root_ami_name()


def test_pruning_keeps_the_image_the_code_names_and_says_what_a_dry_run_would_remove():
    lane = [{"Key": "pickfit", "Value": "verify"}, {"Key": r.IMAGE_KIND_TAG, "Value": r.NET_KIND}]
    newer = {"ImageId": "ami-newer", "Name": "pickfit-rootvm-host-ffffffffffff", "State": "available", "Tags": lane,
             "CreationDate": "2026-12-01", "BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-newer"}}]}
    baking = {"ImageId": "ami-baking", "Name": "pickfit-rootvm-host-aaaaaaaaaaaa", "State": "pending", "Tags": lane,
              "CreationDate": "2026-12-02", "BlockDeviceMappings": []}
    ec2 = FakeRootEc2(images=[dict(ROOT_AMI), newer, baking])
    assert r.prune_root_images(ec2, log=lambda line: None, apply=False) == ["ami-newer", "snap-newer"]
    assert len(ec2.images) == 3 and ec2.snapshots_deleted == []
    assert r.prune_root_images(ec2, log=lambda line: None) == ["ami-newer", "snap-newer"]
    assert {i["ImageId"] for i in ec2.images} == {"ami-root", "ami-baking"}  # the current one, and one being made
    ec2 = FakeRootEc2(images=[newer, {**newer, "ImageId": "ami-older", "CreationDate": "2026-10-01",
                                      "BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-older"}}]}])
    assert r.prune_root_images(ec2, log=lambda line: None) == ["ami-older", "snap-older"]  # else the newest stays
    assert r.prune_root_images(FakeRootEc2(images=[]), log=lambda line: None) == []


def test_prepare_base_makes_the_network_and_the_image_without_starting_a_box():
    m, ec2, _ = machine()
    image = m.prepare()
    assert image["ImageId"] == "ami-root" and "run_instances" not in ec2.names()
    assert ec2.vpcs and len(ec2.groups) == 4


# -- the box, the CLI and the script


def test_an_ec2_root_box_is_a_full_privilege_box_and_says_so():
    b, ec2, ssh = box(tags={"pickfit.run": "verify-hal0-20261121-101500-ab12", "pickfit.role": "agent"},
                      limits=BoxLimits(memory_mb=8192, lifetime_s=900))
    assert b.runner == "ec2-rootvm" and b.capabilities.full_privilege and b.run_id.startswith("verify-hal0-")
    assert b.capabilities.granted() == ["root", "systemd", "container_engine", "kernel_modules"]
    b.start()
    assert launch(ec2)["InstanceType"] == "m7i-flex.large" and b.machine.lifetime_s == 900
    b.exec("sudo systemctl start docker", 30)
    ran = ssh.remote[-1]
    assert ran[3:7] == [rb.RUNUSER, "-u", "sbx", "--"] and "setpriv" not in " ".join(ran)  # sudo must work
    b.set_network(False)
    assert ec2.acl_of("subnet-1") == b.machine.net.offline_acl
    seen = b.evidence()
    assert seen["full_privilege"] is True and seen["offline_cut"] == "stateless" and seen["runner"] == "ec2-rootvm"
    assert seen["provider_view"]["metadata_endpoint"] == "disabled" and seen["provider_view"]["key_pair"] is None
    assert seen["provider_view"]["instance_profile"] is None
    b.close()
    assert b.ended == "terminated" and b.evidence()["ended"] == "terminated"


def test_the_cli_reaches_the_box_with_a_runtime_name_on_the_ec2_runner():
    from pickfit.verify.cli import ROOT_VM, box_factory

    made = box_factory("ec2", 900, runtime=ROOT_VM, memory_mb=4096, extra_disk_gb=8, kvm=True)("run-1", "agent")
    assert isinstance(made, r.Ec2RootBox) and made.limits.memory_mb == 4096 and made.limits.lifetime_s == 900
    assert made.machine.tags == {"pickfit.run": "run-1", "pickfit.role": "agent"}
    assert made.machine.extra_disk_gb == 8 and made.machine.kvm
    assert not isinstance(box_factory("ec2", 900)("run-1", "agent"), r.Ec2RootBox)  # the default is as before
    for wrong in ({"runner": "modal"}, {"runner": "docker"}, {"display": True}, {"toolchain": True},
                  {"services": True}, {"audio": True}, {"gpu": "T4"}):
        with pytest.raises(ValueError, match="rootvm"):
            box_factory(**{"runner": "ec2", "lifetime_s": 900, "runtime": ROOT_VM, **wrong})
    with pytest.raises(ValueError, match="rootvm"):
        box_factory("ec2", 900, extra_disk_gb=8)  # an option of the full-privilege box only
    with pytest.raises(ValueError, match="rootvm"):
        box_factory("modal", 900, kvm=True)


def test_the_cli_refuses_wrong_combinations_before_anything_starts_and_holds_a_batch_to_one(capsys, monkeypatch):
    import argparse

    from pickfit.verify import cli

    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    assert cli.run(parser.parse_args(["verify", "--runner", "modal", "--runtime", "rootvm", "--fixture", "x"])) == 2
    assert cli.run(parser.parse_args(["verify", "--runner", "ec2", "--extra-disk-gb", "8", "--fixture", "x"])) == 2
    assert cli.run(parser.parse_args(["verify", "--runner", "ec2", "--runtime", "rootvm", "--display",
                                      "--fixture", "x"])) == 2
    assert capsys.readouterr().out.count("rootvm") >= 3
    seen: dict[str, Any] = {}
    monkeypatch.setattr(cli, "_batch", lambda args, make_box, limits: seen.update(n=args.concurrency) or 0)
    args = parser.parse_args(["verify", "--runner", "ec2", "--runtime", "rootvm", "--batch", "3", "--concurrency", "4"])
    assert cli.run(args) == 0 and seen["n"] == 1
    assert "one record at a time" in capsys.readouterr().out


def test_the_reap_script_lists_by_default_and_removes_only_when_told(capsys):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("ec2_reap", Path(__file__).parent.parent / "scripts" / "ec2_reap.py")
    script = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(script)  # type: ignore[union-attr]
    lane = [{"Key": "pickfit", "Value": "verify"}, {"Key": r.IMAGE_KIND_TAG, "Value": r.NET_KIND}]
    old = {"ImageId": "ami-old", "Name": "pickfit-rootvm-host-000000000000", "State": "available", "Tags": lane,
           "CreationDate": "2026-11-01", "BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-old"}}]}
    ec2 = FakeRootEc2(images=[dict(ROOT_AMI), old])
    instance(ec2, "i-leaked", tags={"pickfit": "verify", "pickfit:role": "rootvm", e.EXPIRES_TAG: "1"})
    instance(ec2, "i-theirs", tags={"Name": "taigi-api"}, age_s=10**7)
    assert script.main(["--region", "ap-east-2"], ec2=ec2) == 0
    assert "would be removed" in capsys.readouterr().out
    assert not {"terminate_instances", "deregister_image", "delete_snapshot", "delete_subnet"} & set(ec2.names())
    assert script.main(["--region", "ap-east-2", "--apply"], ec2=ec2) == 0
    assert ec2.instances["i-leaked"]["State"]["Name"] == "terminated"
    assert ec2.instances["i-theirs"]["State"]["Name"] == "running"
    assert {i["ImageId"] for i in ec2.images} == {"ami-root"} and ec2.snapshots_deleted == ["snap-old"]
