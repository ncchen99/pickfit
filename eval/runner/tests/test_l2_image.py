"""Tests for eval/runner/l2_image.py with a fake modal module (nothing is built or started)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import l2_image  # noqa: E402

DIGEST = "sha256:" + "a" * 64


class FakeStream:
    def __init__(self, text: str = ""):
        self.text, self.written = text, b""

    def read(self) -> str:
        return self.text

    def write(self, data: bytes) -> None:
        self.written += data

    def write_eof(self) -> None:
        pass

    def drain(self) -> None:
        pass


class FakeProc:
    def __init__(self, args):
        self.args = args
        self.stdout = FakeStream("python3 /usr/bin/python3\n" if "command -v" in args[-1] else "out\n")
        self.stdin = FakeStream()
        self.returncode = 0

    def wait(self) -> int:
        return 0


class FakeModal:
    def __init__(self):
        self.calls: list = []
        outer = self

        class Image:
            def __init__(self, desc):
                self.desc, self.object_id = desc, "im-123"

            @staticmethod
            def from_registry(tag, add_python="unset"):
                outer.calls.append(("from_registry", tag, add_python))
                return Image([tag])

            @staticmethod
            def from_name(name):
                return Image([name])

            def run_commands(self, *commands):
                outer.calls.append(("run_commands", commands))
                return Image(self.desc + list(commands))

            def build(self, app):
                outer.calls.append(("build", tuple(self.desc)))

            def publish(self, name, client=None):
                outer.calls.append(("publish", name))

        class Sandbox:
            object_id = "sb-1"

            @staticmethod
            def create(*args, **kw):
                outer.calls.append(("sandbox", args, kw.get("cpu")))
                return Sandbox()

            def exec(self, *args):
                proc = FakeProc(args)
                outer.calls.append(("exec", args))
                outer.procs.append(proc)
                return proc

            def terminate(self):
                outer.calls.append(("terminate",))

        class App:
            @staticmethod
            def lookup(name, create_if_missing=False, client=None):
                return "app"

        self.Image, self.Sandbox, self.App, self.procs = Image, Sandbox, App, []


def test_the_dev_variant_is_exactly_the_proposed_packages() -> None:
    assert l2_image.VARIANTS["dev"]["packages"] == ["python3", "git", "ca-certificates", "curl", "strace"]
    assert l2_image.VARIANTS["base"]["packages"] == [] and l2_image.VARIANTS["base-git"]["packages"] == ["git"]


def test_plan_needs_no_network_and_names_change_with_content() -> None:
    p = l2_image.plan("dev", DIGEST)
    assert p["dockerfile"].splitlines()[0] == f"FROM ubuntu:24.04@{DIGEST}"
    assert "--no-install-recommends python3 git ca-certificates curl strace" in p["dockerfile"]
    assert l2_image.plan("base", DIGEST)["dockerfile"] == f"FROM ubuntu:24.04@{DIGEST}"
    names = {l2_image.image_name(v, DIGEST, None) for v in l2_image.VARIANTS}
    assert len(names) == 3
    assert l2_image.image_name("dev", DIGEST, "20261101T000000Z") != l2_image.image_name("dev", DIGEST, None)
    assert "--snapshot 20261101T000000Z" in l2_image.plan("dev", DIGEST, "20261101T000000Z")["dockerfile"]


def test_build_pins_the_digest_adds_no_python_and_records(tmp_path: Path) -> None:
    fake = FakeModal()
    entry = l2_image.build("base", DIGEST, None, modal=fake, client="c", record_path=tmp_path / "r.json", log=lambda *_: None)
    assert ("from_registry", f"ubuntu:24.04@{DIGEST}", None) in fake.calls
    assert not any(c[0] == "run_commands" for c in fake.calls)  # base: nothing added
    assert entry["image_id"] == "im-123" and entry["name"].startswith("pickfit-eval-l2-base:")
    assert json.loads((tmp_path / "r.json").read_text())["images"]["base"]["base"] == f"ubuntu:24.04@{DIGEST}"


def test_build_refuses_an_unpinned_base(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        l2_image.build("dev", "latest", None, modal=FakeModal(), client="c", record_path=tmp_path / "r.json")


def test_inspect_records_what_is_inside_and_runs_the_egress_selftest_on_dev(tmp_path: Path) -> None:
    fake = FakeModal()
    record = tmp_path / "r.json"
    l2_image.build("dev", DIGEST, None, modal=fake, client="c", record_path=record, log=lambda *_: None)
    seen = l2_image.inspect("dev", modal=fake, client="c", record_path=record, log=lambda *_: None)
    assert set(seen) >= {"os_release", "arch", "dpkg", "runtimes", "versions", "dpkg_sha256", "egress_selftest"}
    uploaded = [p for p in fake.procs if p.stdin.written]
    assert uploaded and uploaded[0].stdin.written == (l2_image.SHARED / "egress.py").read_bytes()
    assert fake.calls[-1] == ("terminate",)


def test_build_and_inspect_need_an_explicit_go_ahead(capsys) -> None:
    assert l2_image.main(["build", "--variant", "dev", "--base-digest", DIGEST]) == 2
    assert "confirm-spend" in capsys.readouterr().out
