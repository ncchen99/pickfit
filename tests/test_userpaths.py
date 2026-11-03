"""Install commands as users run them: pickfit's sandbox home written as $HOME (pickfit/userpaths.py, index._user_guide).

The verified commands stay exactly as the run executed them; the index adds a user's copy beside them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pickfit.index import build_index
from pickfit.userpaths import SANDBOX_HOMES, WORKDIR, expected_for_user, for_user, names_workdir

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "worker" / "test" / "fixtures" / "software"
SHELLS = [s for s in ("/bin/bash", "/bin/zsh", "/bin/sh") if Path(s).exists()]


def test_the_sandbox_homes_are_the_boxes_own():
    from pickfit.verify.box import BOX_HOME, BOX_WORKDIR
    from pickfit.verify.tart_box import MAC_HOME, MAC_WORKDIR
    from pickfit.verify.vbox_box import WIN_HOME

    assert SANDBOX_HOMES == {"linux": BOX_HOME, "macos": MAC_HOME, "windows": WIN_HOME}
    assert BOX_WORKDIR == f"{BOX_HOME}/{WORKDIR}" and MAC_WORKDIR == f"{MAC_HOME}/{WORKDIR}"


def test_the_home_becomes_quoted_home_unquoted_and_plain_home_in_double_quotes():
    assert for_user("open /Users/sbx/Applications/openpets.app", "macos").command == \
        'open "$HOME"/Applications/openpets.app'
    assert for_user("AOCI=/home/sbx/work/aoci && $AOCI --help", "linux").command == 'AOCI="$HOME"/work/aoci && $AOCI --help'
    inside = for_user("""node -p "require('/home/sbx/.local/lib/x/package.json').version" """, "linux")
    assert inside.command == """node -p "require('$HOME/.local/lib/x/package.json').version" """ and inside.changed
    escaped = for_user('echo "a \\" /home/sbx/b"', "linux")  # an escaped quote does not close the string
    assert escaped.command == 'echo "a \\" $HOME/b"'


def test_inside_single_quotes_the_command_stays_as_run_and_is_not_portable():
    out = for_user("""printf '%s' 'export P="/home/sbx/work/a"' > f""", "linux")
    assert out.command == """printf '%s' 'export P="/home/sbx/work/a"' > f""" and not out.portable and not out.changed


def test_only_the_home_itself_counts_and_other_systems_are_left_alone():
    for same in ["cat /tmp/home/sbx/x /home/sbxfoo /home/sbx.bak", "echo ~/x", "ls /home/other"]:
        assert for_user(same, "linux") == for_user(same, "linux").__class__(same, changed=False, portable=True)
    assert for_user("open /Users/sbx/X.app", "linux").command == "open /Users/sbx/X.app"  # not the Linux box's home
    win = for_user(r"C:\Users\sbx\bin\tool.exe --help", "windows")
    assert win.command == r"C:\Users\sbx\bin\tool.exe --help" and not win.portable
    assert for_user("open /Users/sbx/X.app", None).command == "open /Users/sbx/X.app"


def test_expected_output_keeps_what_follows_the_home_and_the_work_folder_is_named():
    assert expected_for_user("/home/sbx/.local/bin/oweka", "linux") == "/.local/bin/oweka"
    assert expected_for_user("0.2.0", "linux") == "0.2.0"
    assert names_workdir("cd /home/sbx/work/repo && make", "linux")
    assert names_workdir("ls /Users/sbx/work", "macos")
    assert not names_workdir("ls /home/sbx/workspace", "linux") and not names_workdir("ls /home/sbx/.local", "linux")


@pytest.mark.parametrize("shell", SHELLS)
def test_a_users_copy_runs_in_a_home_with_spaces_and_no_sandbox_user(tmp_path: Path, shell: str):
    """The rewritten commands, run by a real shell for a user whose home is not /Users/sbx and holds spaces."""
    home = tmp_path / "Jane Q User"
    home.mkdir()
    verified = [
        "mkdir -p /Users/sbx/mnt/app /Users/sbx/Applications",
        "touch /Users/sbx/mnt/app/Thing.app && cp -R /Users/sbx/mnt/app/Thing.app /Users/sbx/Applications/",
        """test -e "/Users/sbx/Applications/Thing.app" && echo "found /Users/sbx/Applications" """,
    ]
    for command in verified:
        user = for_user(command, "macos")
        assert user.changed and "sbx" not in user.command
        done = subprocess.run([shell, "-c", user.command], env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True, timeout=20)
        assert done.returncode == 0, (shell, user.command, done.stderr)
    assert (home / "Applications" / "Thing.app").exists()
    assert done.stdout.strip() == f"found {home}/Applications"


def _with_sandbox_paths(tmp_path: Path) -> Path:
    """fixture-chat-tui whose run (and so its guide) names the Linux box's home, as real runs do."""
    data = tmp_path / "software"
    data.mkdir()
    for p in FIXTURES.glob("*.json"):
        shutil.copy(p, data / p.name)
    path = data / "fixture-chat-tui.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    step = "cargo install --root /home/sbx/.local fixture-chat-tui"
    rec["verification"]["runs"][0]["steps"][0]["command"] = step
    guide = rec["install"]["linux"]
    guide["steps"][0]["command"] = step
    guide["check"] = {"command": "/home/sbx/.local/bin/fixture-chat-tui --version", "expected_signal": "0.2.0"}
    guide["first_task"] = "cd /home/sbx/work && fixture-chat-tui --endpoint http://127.0.0.1:8080/v1"
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def test_the_index_publishes_the_runs_commands_unchanged_and_a_users_copy_beside_them(tmp_path: Path):
    data = _with_sandbox_paths(tmp_path)
    before = (data / "fixture-chat-tui.json").read_text(encoding="utf-8")
    entry = next(e for e in build_index(data).index["entries"] if e["slug"] == "fixture-chat-tui")
    assert (data / "fixture-chat-tui.json").read_text(encoding="utf-8") == before  # the record is not touched
    guide = entry["install"]["linux"]
    assert guide["steps"][0]["command"] == "cargo install --root /home/sbx/.local fixture-chat-tui"  # as run
    assert guide["check"]["command"] == "/home/sbx/.local/bin/fixture-chat-tui --version"
    user = guide["user"]
    assert user["steps"] == [{"command": 'cargo install --root "$HOME"/.local fixture-chat-tui',
                              "purpose": guide["steps"][0]["purpose"]}]
    assert user["check"] == {"command": '"$HOME"/.local/bin/fixture-chat-tui --version', "expected_signal": "0.2.0"}
    assert user["first_task"] == 'cd "$HOME"/work && fixture-chat-tui --endpoint http://127.0.0.1:8080/v1'
    assert user["changed"] and user["needs_workdir"] and user["not_portable"] == []
    assert user["sandbox_home"] == "/home/sbx"
    plain = next(e for e in build_index(FIXTURES).index["entries"] if e["slug"] == "fixture-json-query")
    for g in plain["install"].values():  # a guide naming no sandbox path: the same commands, nothing flagged
        assert [s["command"] for s in g["user"]["steps"]] == [s["command"] for s in g["steps"]]
        assert not g["user"]["changed"] and g["user"]["sandbox_home"] is None


@pytest.fixture(scope="module")
def real_index() -> dict:
    return build_index(REPO / "data" / "software").index


def _user_commands(guide: dict) -> dict[str, str]:
    u = guide["user"]
    out = {f"step {i}": s["command"] for i, s in enumerate(u["steps"], start=1)}
    out |= {f"setup {i}": s["command"] for i, s in enumerate(u["first_task_setup"], start=1)}
    if u["first_task"]:
        out["first task"] = u["first_task"]
    if u["check"]:
        out["check"] = u["check"]["command"]
    return out


def test_no_published_users_command_names_a_sandbox_home_unless_flagged(real_index: dict):
    for entry in real_index["entries"]:
        for os_name, guide in entry["install"].items():
            home = SANDBOX_HOMES[guide["run"]["os"]]
            for label, command in _user_commands(guide).items():
                if home in command and not for_user(command, guide["run"]["os"]).changed:
                    assert label in guide["user"]["not_portable"], (entry["slug"], os_name, label, command)


def test_the_published_verified_commands_are_the_records_own(real_index: dict):
    records = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (REPO / "data" / "software").glob("*.json")}
    for entry in real_index["entries"]:
        for os_name, guide in entry["install"].items():
            mine = records[entry["slug"]]["install"][os_name]
            assert [s["command"] for s in guide["steps"]] == [s["command"] for s in mine["steps"]]
            assert guide["first_task"] == mine["first_task"] and guide["check"] == mine["check"]


@pytest.mark.parametrize("shell", SHELLS)
def test_every_published_users_command_is_valid_shell(real_index: dict, shell: str):
    """The rewrite never breaks a command's syntax: each user's command parses where its verified one did."""
    def parses(command: str) -> bool:
        return subprocess.run([shell, "-n", "-c", command], capture_output=True, timeout=10).returncode == 0

    for entry in real_index["entries"]:
        for os_name, guide in entry["install"].items():
            if guide["run"]["os"] == "windows":
                continue
            ran = {f"step {i}": s["command"] for i, s in enumerate(guide["steps"], start=1)}
            ran |= {"first task": guide["first_task"]} if guide["first_task"] else {}
            for label, command in _user_commands(guide).items():
                if label in ran and command != ran[label] and parses(ran[label]):
                    assert parses(command), (entry["slug"], os_name, label, command)


def test_openpets_on_a_mac_installs_and_opens_from_the_users_home(real_index: dict):
    guide = next(e for e in real_index["entries"] if e["slug"] == "openpets")["install"]["macos"]
    assert [s["command"] for s in guide["user"]["steps"]] == [
        'curl -fL -o "$HOME"/Downloads/OpenPets-mac-arm64.dmg '
        "https://github.com/OpenPetsHQ/openpets/releases/download/v4.1.0/OpenPets-4.1.0-mac-arm64.dmg",
        'mkdir -p "$HOME"/mnt/openpets "$HOME"/Applications && hdiutil attach -nobrowse -mountpoint "$HOME"/mnt/openpets '
        '"$HOME"/Downloads/OpenPets-mac-arm64.dmg && cp -R "$HOME"/mnt/openpets/openpets.app "$HOME"/Applications/ '
        '&& hdiutil detach -force "$HOME"/mnt/openpets',
    ]
    assert guide["user"]["first_task"] == 'open "$HOME"/Applications/openpets.app'
    assert guide["steps"][0]["command"].startswith("curl -fL -o /Users/sbx/Downloads/")  # the run's own, unchanged
