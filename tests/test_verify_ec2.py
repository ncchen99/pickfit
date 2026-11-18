"""The EC2 provider (ec2_machine.py) and the VM-over-SSH part under it (ssh_machine.py), against a fake EC2
API and a fake ssh. Nothing leaves the process: no AWS call, no connection."""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from pickfit.verify import ec2_machine as e
from pickfit.verify import linux_box as lb
from pickfit.verify import ssh_machine as s
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.machine import ONLINE_CIDRS

CONTROL = "203.0.113.7/32"
AMI = {"ImageId": "ami-box", "Name": e.image_names(lb.image_recipe("vm"))[1], "State": "available",
       "RootDeviceName": "/dev/xvda"}


class AwsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeEc2:
    """Enough of EC2 to hold security groups, images and instances, and a record of every call."""

    def __init__(self, images: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.groups: dict[str, dict[str, Any]] = {}
        self.images = list(images if images is not None else [AMI])
        self.instances: dict[str, dict[str, Any]] = {}
        self.fail: dict[str, Exception] = {}
        self.imds = "enabled"

    def _call(self, name: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((name, kwargs))
        if name in self.fail:
            raise self.fail[name]

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def describe_vpcs(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_vpcs", kw)
        return {"Vpcs": [{"VpcId": "vpc-1"}]}

    def describe_security_groups(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_security_groups", kw)
        return {"SecurityGroups": list(self.groups.values())}

    def create_security_group(self, **kw: Any) -> dict[str, Any]:
        self._call("create_security_group", kw)
        gid = f"sg-{len(self.groups) + 1}"
        self.groups[gid] = {"GroupId": gid, "GroupName": kw["GroupName"], "IpPermissions": [], "IpPermissionsEgress": [
            {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]}
        return {"GroupId": gid}

    def revoke_security_group_egress(self, **kw: Any) -> None:
        self._call("revoke_security_group_egress", kw)
        self.groups[kw["GroupId"]]["IpPermissionsEgress"] = []

    def authorize_security_group_egress(self, **kw: Any) -> None:
        self._call("authorize_security_group_egress", kw)
        self.groups[kw["GroupId"]]["IpPermissionsEgress"] += kw["IpPermissions"]

    def authorize_security_group_ingress(self, **kw: Any) -> None:
        self._call("authorize_security_group_ingress", kw)
        self.groups[kw["GroupId"]]["IpPermissions"] += kw["IpPermissions"]

    def describe_images(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_images", kw)
        names = next((f["Values"] for f in kw.get("Filters", []) if f["Name"] == "name"), None)
        ids = kw.get("ImageIds")
        return {"Images": [i for i in self.images if (ids is None or i["ImageId"] in ids)
                           and (names is None or i["Name"] in names or names == [e.BASE_AMI_NAME])
                           and (kw.get("Owners") != [e.BASE_AMI_OWNER] or i["ImageId"].startswith("ami-debian"))
                           and (kw.get("Owners") != ["self"] or not i["ImageId"].startswith("ami-debian"))]}

    def run_instances(self, **kw: Any) -> dict[str, Any]:
        self._call("run_instances", kw)
        iid = f"i-{len(self.instances) + 1}"
        tags = next(t["Tags"] for t in kw["TagSpecifications"] if t["ResourceType"] == "instance")
        self.instances[iid] = {"InstanceId": iid, "State": {"Name": "running"}, "PublicIpAddress": "198.51.100.9",
                               "Groups": list(kw["SecurityGroupIds"]), "Tags": tags, "InstanceType": kw["InstanceType"],
                               "UserData": kw["UserData"], "LaunchTime": f"t{len(self.instances):03d}",
                               "InstanceInitiatedShutdownBehavior": kw["InstanceInitiatedShutdownBehavior"]}
        return {"Instances": [{"InstanceId": iid}]}

    def describe_instances(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_instances", kw)
        ids = kw.get("InstanceIds")
        found = [i for iid, i in self.instances.items() if ids is None or iid in ids]
        for f in kw.get("Filters", []):
            if f["Name"] == "instance-state-name":
                found = [i for i in found if i["State"]["Name"] in f["Values"]]
            elif f["Name"].startswith("tag:"):
                key = f["Name"][4:]
                found = [i for i in found if any(t["Key"] == key and t["Value"] in f["Values"] for t in i["Tags"])]
        return {"Reservations": [{"Instances": found}]}

    def modify_instance_metadata_options(self, **kw: Any) -> None:
        self._call("modify_instance_metadata_options", kw)
        self.imds = kw["HttpEndpoint"]

    def modify_instance_attribute(self, **kw: Any) -> None:
        self._call("modify_instance_attribute", kw)
        instance = self.instances[kw["InstanceId"]]
        if "Groups" in kw:
            instance["Groups"] = list(kw["Groups"])
        for name in ("UserData", "InstanceType", "InstanceInitiatedShutdownBehavior"):
            if name in kw:
                instance[name] = kw[name]["Value"]

    def create_tags(self, **kw: Any) -> None:
        self._call("create_tags", kw)
        for iid in kw["Resources"]:
            tags = {t["Key"]: t["Value"] for t in self.instances[iid]["Tags"]} | {t["Key"]: t["Value"] for t in kw["Tags"]}
            self.instances[iid]["Tags"] = [{"Key": k, "Value": v} for k, v in tags.items()]

    def start_instances(self, **kw: Any) -> None:
        self._call("start_instances", kw)
        for iid in kw["InstanceIds"]:
            self.instances[iid]["State"] = {"Name": "running"}

    def revoke_security_group_ingress(self, **kw: Any) -> None:
        self._call("revoke_security_group_ingress", kw)
        gone = {r["CidrIp"] for p in kw["IpPermissions"] for r in p["IpRanges"]}
        for permission in self.groups[kw["GroupId"]]["IpPermissions"]:
            permission["IpRanges"] = [r for r in permission["IpRanges"] if r["CidrIp"] not in gone]

    def terminate_instances(self, **kw: Any) -> None:
        self._call("terminate_instances", kw)
        for iid in kw["InstanceIds"]:
            self.instances[iid]["State"] = {"Name": "terminated"}

    def stop_instances(self, **kw: Any) -> None:
        self._call("stop_instances", kw)
        for iid in kw["InstanceIds"]:
            self.instances[iid]["State"] = {"Name": "stopped"}

    def create_image(self, **kw: Any) -> dict[str, Any]:
        self._call("create_image", kw)
        self.images.append({"ImageId": "ami-baked", "Name": kw["Name"], "State": "available",
                            "RootDeviceName": "/dev/xvda"})
        return {"ImageId": "ami-baked"}


class Pipe:
    """A local process's stdin: keeps what was written, and whether it was closed."""

    def __init__(self) -> None:
        self.data, self.closed = b"", False

    def write(self, data: bytes) -> None:
        self.data += data

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class Out:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read1(self, n: int) -> bytes:
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk


class FakeSsh:
    """The local ssh and ssh-keygen. A command on the machine answers what `reply` says for its remote argv; the
    egress and metadata probes answer from the fake EC2's state, as the real machine would."""

    def __init__(self, ec2: FakeEc2 | None = None) -> None:
        self.ec2 = ec2
        self.local: list[list[str]] = []  # ssh-keygen and ssh's own control commands
        self.remote: list[list[str]] = []  # argv run as root on the machine, in order
        self.procs: list[Any] = []
        self.replies: dict[str, tuple[int, bytes, bytes]] = {}  # a word in the remote command -> its answer
        self.stuck_open = False  # the provider's cut that does not take
        self.box: str | None = None  # the instance the probes answer for (the first, unless a test says)
        self.refuse: set[str] = set()  # addresses whose machine does not answer with this harness's keys

    def run(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
        self.local.append(list(argv))
        if argv[0] == s.SSH_KEYGEN:
            path = Path(argv[argv.index("-f") + 1])
            path.write_text(f"-----PRIVATE {path.name}-----\n")
            Path(f"{path}.pub").write_text(f"ssh-ed25519 PUBLIC{path.name} pickfit\n")
        elif "ControlMaster=yes" in argv:
            if argv[-1].split("@")[-1] in self.refuse:
                return subprocess.CompletedProcess(argv, 255, "", "Host key verification failed.")
            Path(next(a for a in argv if a.startswith("ControlPath=")).split("=", 1)[1]).write_text("")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def popen(self, argv: list[str], **kw: Any) -> Any:
        remote = shlex.split(argv[-1])
        self.remote.append(remote)
        text = " ".join(remote)
        code, out, err = next((r for word, r in self.replies.items() if word in text), (0, b"", b""))
        if e.EGRESS_PROBE in remote and self.ec2 is not None:
            online = {g["GroupId"] for g in self.ec2.groups.values() if g["GroupName"] == e.GROUPS["online"]}
            box = self.box or next(iter(self.ec2.instances))
            wearing = set(self.ec2.instances[box]["Groups"])
            out = b"open\n" if (wearing & online or self.stuck_open) else b""
        if e.IMDS_PROBE in remote and self.ec2 is not None:
            out = b"HTTP/1.1 200" if self.ec2.imds == "enabled" else b"HTTP/1.1 403"

        class Proc:
            stdin, stdout, stderr = Pipe(), Out(out), Out(err)

            def wait(self) -> int:
                return code

            def poll(self) -> int:
                return code

            def kill(self) -> None:
                pass

        proc = Proc()
        proc.argv = argv  # type: ignore[attr-defined]
        self.procs.append(proc)
        return proc


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "0")  # the pool has its own tests
    clock = Clock()
    monkeypatch.setattr(e, "_now", clock.now)
    monkeypatch.setattr(e, "_sleep", clock.sleep)
    monkeypatch.setattr(s, "_now", clock.now)
    monkeypatch.setattr(s, "_sleep", clock.sleep)


def machine(ec2: FakeEc2 | None = None, ssh: FakeSsh | None = None, **kw: Any) -> tuple[e.Ec2Machine, FakeEc2, FakeSsh]:
    ec2 = ec2 or FakeEc2()
    ssh = ssh or FakeSsh(ec2)
    made = e.Ec2Machine(**{"cores": 2, "memory_mb": 2048, "lifetime_s": 1200, "ec2": ec2, "control": CONTROL,
                           "popen": ssh.popen, "run": ssh.run, "log": lambda line: None, **kw})
    return made, ec2, ssh


def in_box(remote: list[str]) -> list[str] | None:
    """The argv a remote command runs inside the box's container, or None for one on the VM itself."""
    if remote[:3] != [s.DOCKER, "exec", "--interactive"]:
        return None
    return remote[remote.index(s.CONTAINER) + 4:]  # past the name, timeout, --signal=KILL and the seconds


# -- the VM over SSH


def test_a_machine_is_reached_with_its_own_keys_and_nothing_of_the_users():
    m, _, ssh = machine()
    m.start()
    argv = ssh.procs[0].argv
    assert argv[:3] == [s.SSH, "-F", "/dev/null"]
    for option in ("IdentitiesOnly=yes", "IdentityAgent=none", "GlobalKnownHostsFile=/dev/null",
                   "StrictHostKeyChecking=yes", "BatchMode=yes"):
        assert option in argv
    assert "root@198.51.100.9" in argv
    keys = Path(argv[argv.index("-i") + 1]).parent
    assert (keys / "known_hosts").read_text() == "198.51.100.9 ssh-ed25519 PUBLIChost\n"  # the key it handed over
    m.close()
    assert not keys.exists()  # no key outlives the machine


def test_the_user_data_gives_root_this_key_only_and_arms_the_poweroff():
    config = s.cloud_config("ssh-ed25519 LOGIN pickfit", "PRIVATE\n", "ssh-ed25519 HOST pickfit", 1250)
    assert config.startswith("#cloud-config\n")
    import json

    data = json.loads(config.split("\n", 1)[1])
    assert data["users"] == [{"name": "root", "ssh_authorized_keys": ["ssh-ed25519 LOGIN pickfit"]}]  # no default user
    assert data["ssh_pwauth"] is False and data["disable_root"] is False
    assert data["ssh_keys"] == {"ed25519_private": "PRIVATE\n", "ed25519_public": "ssh-ed25519 HOST pickfit"}
    arm = data["bootcmd"][0]
    assert arm[:3] == ["/usr/bin/timeout", "20", "/usr/bin/systemd-run"]
    assert arm[-2:] == ["/usr/bin/systemctl", "poweroff"]
    assert arm[arm.index("--on-active") + 1] == "1250s" and arm[arm.index("--unit") + 1] == "pickfit-lifetime"
    assert arm.count("DefaultDependencies=no") == 2  # the timer and its service: neither waits for the boot to end
    assert "runcmd" not in data  # armed early in the boot, not at the end of cloud-init


def test_a_machine_whose_poweroff_is_not_armed_or_whose_kernel_has_vsock_does_not_start():
    m, ec2, ssh = machine()
    ssh.replies["is-active pickfit-lifetime.timer"] = (3, b"inactive\n", b"")
    with pytest.raises(BoxError, match="poweroff is not armed"):
        m.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    assert not any(r[3:5] == [s.DOCKER, "run"] for r in ssh.remote)
    m, ec2, ssh = machine()
    ssh.replies["/sys/module/vsock"] = (1, b"", b"")
    with pytest.raises(BoxError, match="vsock"):
        m.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    assert not any(r[3:5] == [s.DOCKER, "run"] for r in ssh.remote)


def test_a_box_command_runs_in_the_container_under_its_timeout():
    m, _, ssh = machine()
    m.start()
    m.spawn(["/usr/bin/id", "-u"], 30, workdir="/home/sbx")
    assert ssh.remote[-1] == [s.DOCKER, "exec", "--interactive", "--workdir", "/home/sbx", s.CONTAINER,
                              "/usr/bin/timeout", "--signal=KILL", "30", "/usr/bin/id", "-u"]
    m.spawn(["/usr/bin/bash", "-c", "echo 'a b' > \"$HOME/x\""], 5)
    assert in_box(ssh.remote[-1]) == ["/usr/bin/bash", "-c", "echo 'a b' > \"$HOME/x\""]  # quoting survives ssh


def test_the_box_is_a_container_with_the_boxs_memory_and_no_swap():
    m, _, ssh = machine(memory_mb=3000, cores=2)
    m.start()
    run = next(r for r in ssh.remote if r[3:5] == [s.DOCKER, "run"])
    assert run[:3] == ["/usr/bin/timeout", "--signal=KILL", "120"]
    for flag, value in (("--memory", "3000m"), ("--memory-swap", "3000m"), ("--cpus", "2"), ("--network", "host"),
                        ("--volume", f"{s.RESOLV_CONF}:/etc/resolv.conf:ro")):  # the provider's resolver, not the stub
        assert run[run.index(flag) + 1] == value
    assert "--privileged" in run and "--init" in run
    assert run[-3:] == [e.image_names(lb.image_recipe("vm"))[0], "/usr/bin/sleep", "infinity"]


def test_the_vms_own_rules_are_loaded_before_the_box_exists():
    m, _, ssh = machine()
    m.start()
    guard = next(i for i, r in enumerate(ssh.remote) if r[3:] == [s.NFT, "-f", "-"])
    box = next(i for i, r in enumerate(ssh.remote) if r[3:5] == [s.DOCKER, "run"])
    assert guard < box
    rules = ssh.procs[guard].stdin.data.decode()
    assert "meta skuid != 0 ip daddr 169.254.0.0/16 drop" in rules  # metadata and link-local, for every uid but root
    assert "fib daddr type local tcp dport 22 reject" in rules  # the VM's sshd is closed to the box


def test_a_process_reads_one_stream_to_its_end_before_the_other():
    real = subprocess.Popen(["/bin/sh", "-c", "head -c 300000 /dev/zero >&2; echo done"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc = s.SshProcess(real, 30)
    assert b"".join(proc.stdout) == b"done\n"  # stderr is past a pipe's 64 KB; it did not block the command
    assert len(b"".join(proc.stderr)) == 300000
    assert proc.wait() == 0


def test_a_client_left_hanging_is_killed_and_reports_a_timeout():
    real = subprocess.Popen(["/bin/sleep", "30"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    assert s.SshProcess(real, 0.2).wait() == 124


def test_a_lost_connection_is_an_error_not_an_exit_code():
    real = subprocess.Popen(["/bin/sh", "-c", "exit 255"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    with pytest.raises(ConnectionError):
        s.SshProcess(real, 30, lost=lambda: True).wait()
    real = subprocess.Popen(["/bin/sh", "-c", "exit 255"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    assert s.SshProcess(real, 30, lost=lambda: False).wait() == 255  # the command's own 255
    m, _, _ = machine()
    assert "stopped answering" in m.explain(ConnectionError("gone"))


# -- EC2


def test_an_instance_has_no_aws_identity_and_dies_with_its_poweroff():
    m, ec2, _ = machine(tags={"pickfit.run": "r1"})
    m.start()
    kw = next(k for name, k in ec2.calls if name == "run_instances")
    assert "KeyName" not in kw and "IamInstanceProfile" not in kw
    assert kw["InstanceInitiatedShutdownBehavior"] == "terminate"
    assert kw["BlockDeviceMappings"][0]["Ebs"]["DeleteOnTermination"] is True
    assert kw["ImageId"] == "ami-box" and kw["InstanceType"] == "c7i-flex.large"
    control, online = (next(g["GroupId"] for g in ec2.groups.values() if g["GroupName"] == e.GROUPS[role])
                       for role in ("control", "online"))
    assert kw["SecurityGroupIds"] == [control, online]
    assert kw["MetadataOptions"]["HttpTokens"] == "required" and kw["MetadataOptions"]["HttpPutResponseHopLimit"] == 1
    tags = {t["Key"]: t["Value"] for t in kw["TagSpecifications"][0]["Tags"]}
    assert tags["pickfit.run"] == "r1" and tags[e.EXPIRES_TAG].isdigit()
    assert kw["UserData"].startswith("#cloud-config\n") and "PRIVATE host" in kw["UserData"]
    assert m.machine_id == "i-1" and m.image == AMI["Name"]


def test_the_metadata_service_is_off_before_the_box_exists():
    m, ec2, ssh = machine()
    m.start()
    assert ("modify_instance_metadata_options", {"InstanceId": "i-1", "HttpEndpoint": "disabled"}) in ec2.calls
    probe = next(i for i, r in enumerate(ssh.remote) if e.IMDS_PROBE in r)
    box = next(i for i, r in enumerate(ssh.remote) if r[3:5] == [s.DOCKER, "run"])
    assert probe < box and m.metadata_answer == "HTTP/1.1 403"


def test_a_metadata_service_that_stays_on_is_a_failed_start():
    m, ec2, _ = machine()
    ec2.modify_instance_metadata_options = lambda **kw: None  # type: ignore[method-assign]  (accepted, not applied)
    with pytest.raises(BoxError, match="metadata service"):
        m.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_the_cut_ends_open_connections_on_the_vm_then_closes_the_security_group():
    m, ec2, ssh = machine()
    m.start()
    before = len(ssh.remote)
    ec2.calls.clear()
    m.set_egress(False)
    assert ssh.remote[before][3:] == ["/usr/bin/bash", "-c", s.CUT_ON]  # first: the rule on the VM
    offline = next(g["GroupId"] for g in ec2.groups.values() if g["GroupName"] == e.GROUPS["offline"])
    assert ec2.calls[0][0] == "modify_instance_attribute" and ec2.calls[0][1]["Groups"][1] == offline
    assert ssh.remote[-1][3:] == ["/usr/bin/bash", "-c", e.EGRESS_PROBE]  # and root on the VM saw it closed
    before = len(ssh.remote)
    m.set_egress(True)
    assert ssh.remote[before][3:] == ["/usr/bin/bash", "-c", e.EGRESS_PROBE]  # open outside first
    assert ssh.remote[-1][3:] == ["/usr/bin/bash", "-c", s.CUT_OFF]
    assert "drop" in s.CUT_ON and 'oifname != "lo"' in s.CUT_ON and "skuid != 0" in s.CUT_ON


def test_a_cut_that_does_not_take_is_an_error():
    m, ec2, ssh = machine()
    m.start()
    ssh.stuck_open = True  # the security group changed, a new connection still opens
    with pytest.raises(BoxError, match="closing"):
        m.set_egress(False)
    m2, ec2, ssh = machine()
    m2.start()
    ec2.fail["modify_instance_attribute"] = AwsError("UnauthorizedOperation")
    with pytest.raises(BoxError, match="UnauthorizedOperation"):
        m2.set_egress(False)
    m3, _, ssh = machine()
    m3.start()
    ssh.replies[s.CUT_TABLE] = (1, b"", b"nft: no such table")
    with pytest.raises(BoxError, match="offline rule"):
        m3.set_egress(False)


def test_a_failed_start_terminates_the_instance():
    m, ec2, ssh = machine()
    ssh.replies["docker run"] = (125, b"", b"docker: no such image")
    with pytest.raises(BoxError, match="container"):
        m.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    m.close()  # twice is fine
    assert ec2.names().count("terminate_instances") == 1
    m2, ec2, _ = machine()
    ec2.fail["run_instances"] = AwsError("InsufficientInstanceCapacity")
    with pytest.raises(BoxError, match="InsufficientInstanceCapacity"):
        m2.start()


def test_the_groups_are_made_once_with_nothing_allowed_out_by_default():
    ec2 = FakeEc2()
    ids = e.ensure_groups(ec2, CONTROL)
    assert sorted(g["GroupName"] for g in ec2.groups.values()) == sorted(e.GROUPS.values())
    assert ec2.names().count("revoke_security_group_egress") == 3  # each new group's allow-all
    out = {role: e._rules(ec2.groups[ids[role]]["IpPermissionsEgress"]) for role in e.GROUPS}
    assert out["control"] == set() and out["offline"] == set()
    assert {rule[3] for rule in out["online"]} == set(ONLINE_CIDRS) and len(ONLINE_CIDRS) <= 60  # the rule quota
    assert e._rules(ec2.groups[ids["control"]]["IpPermissions"]) == {("tcp", 22, 22, CONTROL)}
    assert e._rules(ec2.groups[ids["online"]]["IpPermissions"]) == set()
    ec2.calls.clear()
    assert e.ensure_groups(ec2, CONTROL) == ids
    assert not {"create_security_group", "authorize_security_group_ingress"} & set(ec2.names())


def test_a_group_someone_widened_is_refused():
    ec2 = FakeEc2()
    ids = e.ensure_groups(ec2, CONTROL)
    ec2.groups[ids["offline"]]["IpPermissionsEgress"] = [{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]
    with pytest.raises(BoxError, match=e.GROUPS["offline"]):
        e.ensure_groups(ec2, CONTROL)
    ec2 = FakeEc2()
    ids = e.ensure_groups(ec2, CONTROL)
    ec2.groups[ids["online"]]["IpPermissionsEgress"].append(
        {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "10.0.0.0/8"}]})
    with pytest.raises(BoxError, match=e.GROUPS["online"]):
        e.ensure_groups(ec2, CONTROL)
    ec2 = FakeEc2()
    ids = e.ensure_groups(ec2, CONTROL)
    ec2.groups[ids["control"]]["IpPermissions"].append(
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]})
    with pytest.raises(BoxError, match=e.GROUPS["control"]):
        e.ensure_groups(ec2, CONTROL)


def test_instances_past_their_lifetime_are_reaped():
    ec2 = FakeEc2()
    ec2.instances = {"i-old": {"InstanceId": "i-old", "State": {"Name": "running"},
                               "Tags": [{"Key": e.EXPIRES_TAG, "Value": "1000"}]},
                     "i-new": {"InstanceId": "i-new", "State": {"Name": "running"},
                               "Tags": [{"Key": e.EXPIRES_TAG, "Value": "5000"}]}}
    assert e.reap(ec2, lambda line: None, now=1000 + e.REAP_MARGIN_S + 1) == ["i-old"]
    assert ec2.instances["i-new"]["State"]["Name"] == "running"
    m, ec2, _ = machine()
    ec2.fail["describe_instances"] = AwsError("RequestLimitExceeded")  # the reap fails; the start goes on to...
    with pytest.raises(BoxError):  # ...the wait for the instance, which needs the same call
        m.start()
    assert "run_instances" in ec2.names()


def test_the_type_holds_the_box_and_the_host_and_has_a_price():
    assert e.pick_type(2, 2048)[0] == "c7i-flex.large"
    assert e.pick_type(2, 4096)[0] == "m7i-flex.large"  # 4 GiB for the box leaves the host none on a 4 GiB type
    assert e.pick_type(4, 6144)[0] == "c7i-flex.xlarge"
    with pytest.raises(ValueError):
        e.pick_type(64, 2048)
    m, _, _ = machine()
    hourly = m.usd_per_second() * 3600
    assert m.region == e.DEFAULT_REGION == "ap-east-2" and m._price() == ("c7i-flex.large", 0.09606)
    assert 0.09606 < hourly < 0.11  # the instance, its address and its disk
    with pytest.raises(ValueError, match="price"):
        machine(region="eu-west-3")  # no price on file there
    assert machine(region="eu-west-3", usd_per_hour=0.12)[0].usd_per_second() > hourly / 3600
    far = machine(region="us-east-1")[0]  # a region with prices of its own
    assert far._price() == ("c7i-flex.large", 0.08479) and far.usd_per_second() < hourly / 3600
    assert e.pick_type(2, 6144, "ap-east-2", "windows", reserve_mb=0) == ("m7i-flex.large", 0.19872)
    assert e.hourly_usd("c7i-flex.large", "us-east-1", "windows") > e.hourly_usd("c7i-flex.large", "us-east-1")


def test_the_image_follows_the_dockerfile_the_recipe_and_the_host_setup(monkeypatch):
    plain, build = lb.image_recipe("vm"), lb.image_recipe("vm", toolchain=True)
    tag, name = e.image_names(plain)
    assert tag == plain.tag(e.sandbox_image_tag())
    assert ":" not in name and name.startswith(tag.replace(":", "-"))  # an AMI name takes no colon
    assert e.image_names(build)[1] != name
    monkeypatch.setattr(e, "HOST_SETUP", e.HOST_SETUP + "\n# changed")
    assert e.image_names(plain)[1] != name and e.image_names(plain)[0] == tag
    text = e.dockerfile(build)
    assert text.startswith(e.SANDBOX_DOCKERFILE.read_text())
    assert "apt-get install -y nftables build-essential" in text
    assert text.rstrip().splitlines()[-1].startswith('RUN ["/bin/sh", "-c", ') and "rustc --version" in text
    assert e.disk_gb(build) > e.disk_gb(plain)
    assert "'install vsock /bin/false'" in e.HOST_SETUP and "update-initramfs -u" in e.HOST_SETUP


def test_baking_builds_the_image_on_a_throwaway_instance_and_leaves_nothing_of_its_boot():
    debian = {"ImageId": "ami-debian", "Name": "debian-13-amd64-20261111-2659", "State": "available",
              "RootDeviceName": "/dev/xvda", "CreationDate": "2026-11-11"}
    ec2 = FakeEc2(images=[debian])
    ssh = FakeSsh(ec2)
    recipe = lb.image_recipe("vm")
    tag, name = e.image_names(recipe)
    image = e.bake_image(ec2, recipe, log=lambda line: None, control=CONTROL, popen=ssh.popen, run=ssh.run)
    assert image["Name"] == name and image["ImageId"] == "ami-baked"
    launch = next(k for n, k in ec2.calls if n == "run_instances")
    assert launch["ImageId"] == "ami-debian"
    stdin = {tuple(r[3:6]): p.stdin.data.decode() for r, p in zip(ssh.remote, ssh.procs)}
    build = next(r for r in ssh.remote if r[3:5] == [s.DOCKER, "build"])
    assert build[build.index("--tag") + 1] == tag and build[-1] == "-"
    assert stdin[(s.DOCKER, "build", "--network")] == e.dockerfile(recipe)
    order = [n for n in ec2.names() if n in ("run_instances", "stop_instances", "create_image", "terminate_instances")]
    assert order == ["run_instances", "stop_instances", "create_image", "terminate_instances"]
    sealed = ssh.procs[-1].stdin.data.decode()  # the last command on the builder
    assert sealed == e.HOST_SEAL and "authorized_keys" in sealed and "ssh_host_" in sealed
    assert not any(r[3:5] == [s.DOCKER, "run"] and "--detach" in r for r in ssh.remote)  # a builder has no box
    assert e.ensure_image(ec2, recipe, control=CONTROL)["ImageId"] == "ami-baked"  # found now, not baked again
    assert ec2.names().count("create_image") == 1


def test_a_failed_bake_terminates_the_builder():
    debian = {"ImageId": "ami-debian", "Name": "debian-13-amd64-x", "State": "available", "CreationDate": "2026"}
    ec2 = FakeEc2(images=[debian])
    ssh = FakeSsh(ec2)
    ssh.replies["docker build"] = (1, b"", b"toomanyrequests")
    with pytest.raises(BoxError, match="toomanyrequests"):
        e.bake_image(ec2, lb.image_recipe("vm"), log=lambda line: None, control=CONTROL, popen=ssh.popen, run=ssh.run)
    assert "create_image" not in ec2.names() and ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_a_machine_can_carry_another_image_than_a_boxs(monkeypatch):
    from pickfit.verify import web_box as w

    container = w.ec2_container()
    assert container.tag.startswith("pickfit-web:") and container.dockerfile.startswith("FROM python:3.12-slim\n")
    for needed in (*w.APT_PACKAGES, w.BROWSER_USE, *w.GUARD_PACKAGES, f"useradd -u {w.WEB_UID}", f"useradd -u {w.GUARD_UID}"):
        assert needed in container.dockerfile  # what publish_image() tells Modal's builder
    name = e.ami_name(container.tag)
    assert ":" not in name and name != AMI["Name"]
    debian = {"ImageId": "ami-debian", "Name": "debian-13-amd64-x", "State": "available", "CreationDate": "2026"}
    ec2 = FakeEc2(images=[debian])
    ssh = FakeSsh(ec2)
    image = e.bake_image(ec2, container=container, log=lambda line: None, control=CONTROL, popen=ssh.popen, run=ssh.run)
    assert image["Name"] == name
    build = next(i for i, r in enumerate(ssh.remote) if r[3:5] == [s.DOCKER, "build"])
    assert ssh.remote[build][ssh.remote[build].index("--tag") + 1] == container.tag
    assert ssh.procs[build].stdin.data.decode() == container.dockerfile
    box = w.on_ec2(site="example.com", tags={"run": "r1"})
    m = box.machine
    assert isinstance(m, e.Ec2Machine) and m.image == name and m.container_image == container.tag
    assert m.tags == {"pickfit.kind": "web-verify", "pickfit.site": "example.com", "pickfit.run": "r1"}
    assert (m.cores, m.memory_mb, m._disk_gb(), m.role) == (w.CPUS, w.MEMORY_MB, w.WEB_DISK_GB, "web")
    assert m._price()[0] == "m7i-flex.large"  # 4 GiB for the browser and the host next to it
    ec2 = FakeEc2(images=[{**AMI, "Name": name}])
    ssh = FakeSsh(ec2)
    m.ec2, m.control, m.popen, m.run_local = ec2, CONTROL, ssh.popen, ssh.run
    m.start()  # a visit's browser has a deadline: its files are read before the machine is handed over
    read = ssh.remote[-1]
    assert read[3:6] == [s.DOCKER, "exec", s.CONTAINER] and "/usr/lib/chromium" in read[-1] and "xargs" in read[-1]
    assert "-P 32 " in read[-1]  # many readers at once: a new volume answers each first read slowly
    assert "read_s" in m.timings and not e.Ec2Machine.preread  # a box's machine reads nothing ahead
    # A pool member read its whole disk at its one boot: a visit that starts on one does not read again.
    monkeypatch.setenv(e.POOL_ENV, "1")
    ec2 = FakeEc2(images=[{**AMI, "Name": name}])
    ssh = FakeSsh(ec2)
    member(ec2)["Tags"][0]["Value"] = name
    ssh.box = "i-pool"
    warm = w.on_ec2(site="example.com", tags={"run": "r2"}).machine
    warm.ec2, warm.control, warm.popen, warm.run_local = ec2, CONTROL, ssh.popen, ssh.run
    warm.start()
    assert warm.warm and "read_s" not in warm.timings and not any("xargs" in r[-1] for r in ssh.remote)
    monkeypatch.setenv(e.POOL_ENV, "0")
    monkeypatch.setattr(w, "BROWSER_USE", "browser-use==9.9.9")
    assert w.ec2_container().tag != container.tag  # another Dockerfile, another image, another AMI


# -- the pool


def member(ec2: FakeEc2, iid: str = "i-pool", address: str = "198.51.100.20", **over: Any) -> dict[str, Any]:
    """A pool member as EC2 lists it: an instance of the box's image that booted once and stopped."""
    ec2.instances[iid] = {"InstanceId": iid, "State": {"Name": "stopped"}, "PublicIpAddress": address,
                          "Groups": ["sg-offline"], "InstanceType": "c7i-flex.large", "LaunchTime": "t000",
                          "Tags": [{"Key": e.POOL_TAG, "Value": AMI["Name"]}, {"Key": "pickfit", "Value": "verify"},
                                   {"Key": e.EXPIRES_TAG, "Value": str(int(time.time()) + 3600)}],
                          **over}
    return ec2.instances[iid]


def tags_of(instance: dict[str, Any]) -> dict[str, str]:
    return {t["Key"]: t["Value"] for t in instance["Tags"]}


def test_a_start_takes_a_pool_member_and_boots_it_with_this_machines_keys(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "2")
    m, ec2, ssh = machine(tags={"pickfit.run": "r1"})
    taken = member(ec2)
    ssh.box = "i-pool"
    m.start()
    assert m.machine_id == "i-pool" and m.warm and m.address == "198.51.100.20"
    assert taken["State"]["Name"] == "running"
    assert taken["UserData"].startswith(b"#cloud-config") and b"PRIVATE host" in taken["UserData"]
    assert taken["InstanceInitiatedShutdownBehavior"] == "terminate"  # as a box, its poweroff ends it
    control, online, offline = (next(g["GroupId"] for g in ec2.groups.values() if g["GroupName"] == e.GROUPS[role])
                                for role in ("control", "online", "offline"))
    assert taken["Groups"] == [control, online]
    tags = tags_of(taken)
    assert tags[e.CLAIM_TAG] and tags["pickfit.run"] == "r1" and tags["pickfit:role"] == "box"
    assert int(tags[e.EXPIRES_TAG]) > 1_000_000  # the box's own lifetime, not the pool's
    # The pool is filled again: two members, with nobody's keys, no way in or out, and a poweroff that stops them.
    launches = [k for n, k in ec2.calls if n == "run_instances"]
    assert len(launches) == 2 and ec2.names().index("start_instances") < ec2.names().index("run_instances")
    for kw in launches:
        assert kw["SecurityGroupIds"] == [offline] and kw["InstanceInitiatedShutdownBehavior"] == "stop"
        assert "PRIVATE" not in kw["UserData"] and "ssh_authorized_keys" not in kw["UserData"]
        assert "cloud-init clean" in kw["UserData"] and "systemctl poweroff" in kw["UserData"]
        assert s.LIFETIME_UNIT in kw["UserData"]  # a member that hangs stops anyway
        made = {t["Key"]: t["Value"] for t in kw["TagSpecifications"][0]["Tags"]}
        assert made[e.POOL_TAG] == AMI["Name"] and e.CLAIM_TAG not in made
    m.close()
    assert taken["State"]["Name"] == "terminated"


def test_without_a_member_the_box_is_a_new_instance_and_the_pool_is_filled(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "2")
    m, ec2, _ = machine()
    member(ec2, "i-other")["Tags"][0]["Value"] = "another image"
    member(ec2, "i-taken")["Tags"].append({"Key": e.CLAIM_TAG, "Value": "x"})
    m.start()
    assert m.machine_id == "i-3" and not m.warm
    assert ec2.names().count("run_instances") == 3 and "start_instances" not in ec2.names()
    assert ec2.instances["i-other"]["State"]["Name"] == "stopped"
    # A second box finds the two that are warming up: they are not ready to take, and the pool needs no more.
    m2, _, _ = machine(ec2=ec2)
    m2.start()
    assert not m2.warm and ec2.names().count("run_instances") == 4


def test_a_member_another_harness_claims_is_left_to_it(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "1")
    m, ec2, ssh = machine()
    first, second = member(ec2, "i-a"), member(ec2, "i-b", "198.51.100.21", LaunchTime="t001")
    settle = e._sleep

    def other_harness(seconds: float) -> None:  # writes its own claim on the first member while this one waits
        if seconds == e.CLAIM_SETTLE_S and e.CLAIM_TAG in tags_of(first) and first["State"]["Name"] == "stopped":
            ec2.create_tags(Resources=["i-a"], Tags=[{"Key": e.CLAIM_TAG, "Value": "theirs"}])
        settle(seconds)

    monkeypatch.setattr(e, "_sleep", other_harness)
    ssh.box = "i-b"
    m.start()
    assert m.machine_id == "i-b" and first["State"]["Name"] == "stopped" and tags_of(first)[e.CLAIM_TAG] == "theirs"
    assert second["State"]["Name"] == "running"


def test_a_member_that_boots_with_other_keys_is_replaced_by_a_new_instance(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "1")
    m, ec2, ssh = machine()
    taken = member(ec2)
    ssh.refuse = {"198.51.100.20"}  # the pinned host key does not match what it answers with
    ssh.box = "i-3"  # i-2 is the member launched in the taken one's place
    m.start()
    assert taken["State"]["Name"] == "terminated" and m.machine_id == "i-3" and not m.warm
    assert m.address == "198.51.100.9" and m.boot_wait_s == e.Ec2Machine.boot_wait_s
    box = next(k for n, k in ec2.calls if n == "run_instances" and k["InstanceInitiatedShutdownBehavior"] == "terminate")
    assert box["UserData"] == taken["UserData"].decode()  # the same keys: the harness pinned them already


def test_a_member_is_resized_to_the_box_and_a_pool_of_none_is_never_looked_at(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "1")
    m, ec2, ssh = machine(memory_mb=6144)
    taken = member(ec2)
    ssh.box = "i-pool"
    m.start()
    assert taken["InstanceType"] == "m7i-flex.large" and m.warm
    monkeypatch.setenv(e.POOL_ENV, "0")
    m2, ec2, _ = machine()
    spare = member(ec2)
    m2.start()
    assert spare["State"]["Name"] == "stopped" and not m2.warm and ec2.names().count("run_instances") == 1
    assert e.pool_size() == 0
    monkeypatch.delenv(e.POOL_ENV)
    assert e.pool_size() == e.POOL_DEFAULT


def test_a_pool_that_cannot_be_read_or_filled_does_not_stop_the_box(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "2")
    m, ec2, _ = machine()
    real = ec2.run_instances
    seen: list[str] = []

    def refuse_members(**kw: Any) -> dict[str, Any]:
        if kw["InstanceInitiatedShutdownBehavior"] == "stop":
            seen.append("member")
            raise AwsError("VcpuLimitExceeded")
        return real(**kw)

    ec2.run_instances = refuse_members  # type: ignore[method-assign]
    m.start()
    assert m.machine_id == "i-1" and seen == ["member"]  # one refusal ends the refill


def test_a_launch_the_quota_refuses_waits_for_room():
    m, ec2, _ = machine()
    real, tries = ec2.run_instances, []

    def full_twice(**kw: Any) -> dict[str, Any]:
        tries.append(1)
        if len(tries) < 3:
            raise AwsError("VcpuLimitExceeded")
        return real(**kw)

    ec2.run_instances = full_twice  # type: ignore[method-assign]
    m.start()
    assert len(tries) == 3 and m.machine_id == "i-1"
    m2, ec2, _ = machine()
    ec2.fail["run_instances"] = AwsError("VcpuLimitExceeded")  # never any room
    with pytest.raises(BoxError, match="VcpuLimitExceeded"):
        m2.start()


def quota(ec2: FakeEc2, vcpus: int) -> None:
    """Give the fake account a vCPU quota: a launch or a start past it is refused, as EC2 refuses it."""
    launch, start = ec2.run_instances, ec2.start_instances

    def held() -> int:
        return sum(e._vcpus(i) for i in ec2.instances.values() if i["State"]["Name"] in ("pending", "running"))

    def run_instances(**kw: Any) -> dict[str, Any]:
        if held() + e._vcpus(kw) > vcpus:
            ec2.calls.append(("refused", kw))
            raise AwsError("VcpuLimitExceeded")
        return launch(**kw)

    def start_instances(**kw: Any) -> None:
        if held() + sum(e._vcpus(ec2.instances[iid]) for iid in kw["InstanceIds"]) > vcpus:
            ec2.calls.append(("refused", kw))
            raise AwsError("VcpuLimitExceeded")
        start(**kw)

    ec2.run_instances, ec2.start_instances = run_instances, start_instances  # type: ignore[method-assign]


def test_a_box_the_quota_refuses_takes_the_room_of_the_newest_warming_member(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "2")
    lines: list[str] = []
    m, ec2, _ = machine(log=lines.append)
    another = e.image_names(lb.image_recipe("vm", display=True))[1]
    old = member(ec2, "i-w1", State={"Name": "running"}, LaunchTime="t001")
    old["Tags"][0]["Value"] = another  # a member of any image holds the same vCPUs
    new = member(ec2, "i-w2", State={"Name": "running"}, LaunchTime="t002")
    quota(ec2, 4)
    m.start()
    assert new["State"]["Name"] == "terminated" and old["State"]["Name"] == "running"  # one, the newest
    assert not m.warm and ec2.instances[m.machine_id]["State"]["Name"] == "running"
    assert ec2.names().count("refused") == 1 and ec2.names().count("run_instances") == 1  # and no member added
    assert any("to make room for this box" in line for line in lines)
    assert any("no member added" in line for line in lines)


def test_a_claimed_member_the_quota_refuses_to_start_takes_room_too(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "1")
    m, ec2, ssh = machine()
    taken = member(ec2)
    warming = member(ec2, "i-w1", State={"Name": "running"}, LaunchTime="t005")
    box = member(ec2, "i-box", State={"Name": "running"}, LaunchTime="t006")
    box["Tags"].append({"Key": e.CLAIM_TAG, "Value": "another harness's box"})  # a box is never ended for a box
    quota(ec2, 4)
    ssh.box = "i-pool"
    m.start()
    assert m.warm and taken["State"]["Name"] == "running"
    assert warming["State"]["Name"] == "terminated" and box["State"]["Name"] == "running"


def test_with_nothing_to_end_a_box_waits_for_another_box_to_finish(monkeypatch):
    m, ec2, _ = machine()
    other = member(ec2, "i-box", State={"Name": "running"})
    other["Tags"].append({"Key": e.CLAIM_TAG, "Value": "x"})
    quota(ec2, 2)
    waited: list[float] = []
    sleep = e._sleep

    def finishes(seconds: float) -> None:
        waited.append(seconds)
        if len(waited) == 3:
            other["State"] = {"Name": "terminated"}
        sleep(seconds)

    monkeypatch.setattr(e, "_sleep", finishes)
    m.start()
    assert waited[:3] == [15, 15, 15] and other["State"]["Name"] == "terminated" and m.machine_id == "i-2"
    m2, ec2, _ = machine()
    member(ec2, "i-box", State={"Name": "running"})["Tags"].append({"Key": e.CLAIM_TAG, "Value": "x"})
    quota(ec2, 2)
    with pytest.raises(BoxError, match="VcpuLimitExceeded"):  # QUOTA_WAIT_S later it gives up
        m2.start()
    assert e.QUOTA_WAIT_S >= 600


def test_members_are_added_only_while_pickfit_stays_within_its_vcpus(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "2")
    assert e.vcpu_budget() == e.VCPUS_DEFAULT == 6  # two boxes and one member warming
    lines: list[str] = []
    m, ec2, _ = machine(log=lines.append)
    member(ec2, "i-box", State={"Name": "running"})["Tags"].append({"Key": e.CLAIM_TAG, "Value": "x"})
    m.start()  # another box runs: this box and one member make six
    assert [k["InstanceInitiatedShutdownBehavior"] for n, k in ec2.calls if n == "run_instances"] == ["terminate", "stop"]
    assert any(f"{e.VCPUS_ENV}=6" in line and "1 of 2 members" in line for line in lines)
    m2, ec2, _ = machine(cores=4, memory_mb=6144)  # a four-vCPU box alone leaves room for one member
    m2.start()
    assert ec2.names().count("run_instances") == 2
    monkeypatch.setenv(e.VCPUS_ENV, "8")
    m3, ec2, _ = machine(cores=4, memory_mb=6144)
    m3.start()
    assert ec2.names().count("run_instances") == 3
    monkeypatch.setenv(e.VCPUS_ENV, "2")  # only the box
    m4, ec2, _ = machine()
    assert m4.prepare()["Name"] == AMI["Name"] and ec2.names().count("run_instances") == 1  # with nothing running, one
    m4.start()
    assert ec2.names().count("run_instances") == 2  # the box; the member already holds what is allowed


def test_old_addresses_of_the_harness_are_taken_off_the_control_group():
    import datetime

    ec2 = FakeEc2()
    ids = e.ensure_groups(ec2, CONTROL)
    old = (datetime.date.today() - datetime.timedelta(days=e.HARNESS_RULE_DAYS + 1)).isoformat()
    ec2.groups[ids["control"]]["IpPermissions"] += [
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [
            {"CidrIp": "198.51.100.1/32", "Description": e.HARNESS_RULE + old},
            {"CidrIp": "198.51.100.2/32", "Description": e.HARNESS_RULE + datetime.date.today().isoformat()},
            {"CidrIp": "198.51.100.3/32", "Description": "someone's own rule"}]}]
    e.ensure_groups(ec2, CONTROL)
    left = {rule[3] for rule in e._rules(ec2.groups[ids["control"]]["IpPermissions"])}
    assert left == {CONTROL, "198.51.100.2/32", "198.51.100.3/32"}


# -- the box


def box(**kw: Any) -> tuple[e.Ec2Box, FakeEc2, FakeSsh]:
    ec2 = FakeEc2()
    ssh = FakeSsh(ec2)
    made = e.Ec2Box(ec2=ec2, control=CONTROL, log=lambda line: None, **kw)
    made.machine.popen, made.machine.run_local = ssh.popen, ssh.run
    return made, ec2, ssh


def test_an_ec2_box_is_the_same_linux_box_on_another_provider():
    b, ec2, ssh = box(tags={"pickfit.run": "r1"}, limits=BoxLimits(memory_mb=3584, lifetime_s=900))
    assert isinstance(b, lb.LinuxBox) and b.runner == "ec2-vm" and b.runtime == "vm" and b.gpu is None
    b.start()
    assert b.image == AMI["Name"] and b.machine.memory_mb == 3584
    assert next(k for n, k in ec2.calls if n == "run_instances")["InstanceType"] == "m7i-flex.large"
    hardening = [in_box(r) for r in ssh.remote if in_box(r) and in_box(r)[-1] == lb.VM_HARDEN]
    assert hardening, "LinuxBox hardens the VM through the container"
    b.exec("echo hi", 20)
    user = in_box(ssh.remote[-1])
    assert user[:3] == lb._drop_to(lb.BOX_UID)[:3] and lb.NO_VSOCK in user  # the box user, under the seccomp filter
    before = len(ssh.remote)
    b.set_network(False)
    ran = ssh.remote[before:]
    assert ran[0][3:] == ["/usr/bin/bash", "-c", s.CUT_ON]
    assert in_box(ran[-1]) == ["/usr/bin/bash", "-c", lb.DNS_BLOCK]  # LinuxBox's own DNS rule, as on any VM
    b.close()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_the_cli_makes_ec2_boxes():
    from pickfit.verify.cli import box_factory

    made = box_factory("ec2", 900, toolchain=True, memory_mb=4096)("run-1", "agent")
    assert isinstance(made, e.Ec2Box) and made.toolchain and made.limits.memory_mb == 4096
    assert made.machine.tags == {"pickfit.run": "run-1", "pickfit.role": "agent"}
    assert made.machine.recipe == lb.image_recipe("vm", toolchain=True)
    with pytest.raises(ValueError, match="gpu"):
        box_factory("ec2", 900, gpu="T4")
    with pytest.raises(ValueError):
        box_factory("docker", 900, toolchain=True)  # still modal's or ec2's
