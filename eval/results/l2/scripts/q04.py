"""L2 for q04 (eval/fixtures/q04/README.md sections 2-4), run 1: three boxes A, B, C, the answer's steps verbatim.

  uv run python eval/results/l2/scripts/q04.py control|experimental

Grader-filled placeholders and prose (section 5): the sops version vX.Y.Z (the latest release at grading
time), the recipient list in .sops.yaml (A and B; C is never added), "remove their public key from
.sops.yaml" (the grader edits the file), and "paste in the new values" in `sops edit` (an EDITOR that
writes the rotated .env from make_env.py --version 2). Fake values never leave the boxes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "eval" / "runner"))
from l2_boxes import Flow  # noqa: E402

GROUP = sys.argv[1]
OUT = ROOT / "eval" / "results" / "l2" / f"q04-{GROUP}"
R = "/work/team-app"
S = "/opt/eval/state/q04"
EG = f"python3 $SHARED/egress.py run --out {S}/egress --cwd {R}"
LATEST = ("curl -fsSL https://api.github.com/repos/getsops/sops/releases/latest | "
          "python3 -c 'import json,sys; print(json.load(sys.stdin)[\"tag_name\"])'")
PASTE = "printf '#!/bin/sh\\ncp /work/team-app/.env \"$1\"\\n' > /usr/local/bin/paste-v2 && chmod 755 /usr/local/bin/paste-v2"

if GROUP == "control":
    ENC_FILE = "secrets.enc.env"
    REGEX = r"\.enc\.env$"

    def install(b, ver):  # "Linux:" block
        b.sh("printf '\\n' | script -qec 'sudo apt install age' /dev/null", "install 1 (default accepted)")
        b.sh(f"cd /tmp && curl -LO https://github.com/getsops/sops/releases/download/{ver}/sops-{ver}.linux.amd64", "install 2")
        b.sh(f"cd /tmp && sudo install -m 755 sops-{ver}.linux.amd64 /usr/local/bin/sops", "install 3")
        b.sh("sops --version && age --version", "install check")

    def keygen(b):
        b.sh("mkdir -p ~/.config/sops/age", "keygen 1")
        b.sh("age-keygen -o ~/.config/sops/age/keys.txt", "keygen 2")

    def encrypt(a):
        a.sh(f"cd {R} && printf '.env\\n.env.*\\n!*.enc.env\\n' >> .gitignore", "gitignore (answer step 3)")
        a.sh(f"{EG} --label a-encrypt-1 --sh 'sops encrypt .env > secrets.enc.env'", "a-encrypt-1")
        a.sh(f"cd {R} && git add .sops.yaml secrets.enc.env .gitignore", "git add")
        a.sh(f"cd {R} && git commit -m 'Add encrypted secrets'", "git commit")

    DECRYPT = "sops decrypt secrets.enc.env > .env"
    DECRYPTED = ".env"

    def remove_and_rotate(a, keep_only):
        keep_only()
        a.sh(f"{EG} --label a-encrypt-2a --sh 'sops updatekeys -y secrets.enc.env'", "a updatekeys")
        a.sh(f"{EG} --label a-encrypt-2b --sh 'sops rotate -i secrets.enc.env'", "a rotate")
        a.sh(f"python3 $F/q04/make_env.py {R}/.env {S}/values-v2.txt --version 2", "grader: new values (provider rotation)")
        a.sh(f"{EG} --label a-encrypt-2c --sh 'EDITOR=paste-v2 sops edit secrets.enc.env'", "a sops edit (paste new values)")
        a.sh(f"cd {R} && git commit -am 'Revoke B, rotate secrets'", "git commit")
else:
    ENC_FILE = "secrets/dev.env"
    REGEX = r"secrets/.*\.env$"

    def install(b, ver):  # "Debian/Ubuntu/Fedora:" prose: apt install age; the sops .deb from releases, checksum checked
        b.sh("printf '\\n' | script -qec 'apt install age' /dev/null", "install 1 (default accepted)")
        v = ver.lstrip("v")
        b.sh(f"cd /tmp && curl -fsSLO https://github.com/getsops/sops/releases/download/{ver}/sops_{v}_amd64.deb "
             f"&& curl -fsSLO https://github.com/getsops/sops/releases/download/{ver}/sops-{ver}.checksums.txt", "install 2 (prose: download the .deb)")
        b.sh(f"cd /tmp && sha256sum --ignore-missing -c sops-{ver}.checksums.txt; grep -c deb sops-{ver}.checksums.txt; cut -c66- sops-{ver}.checksums.txt", "install 3 (prose: check the checksums)")
        b.sh(f"cd /tmp && dpkg -i sops_{v}_amd64.deb", "install 4 (prose: install the .deb)")
        b.sh("sops --version && age --version", "install check")

    def keygen(b):
        b.sh("mkdir -p ~/.config/sops/age", "keygen 1")
        b.sh("age-keygen -o ~/.config/sops/age/keys.txt", "keygen 2")
        b.sh("chmod 600 ~/.config/sops/age/keys.txt", "keygen 3")

    def encrypt(a):
        a.sh(f"cd {R} && mkdir -p secrets && cp .env secrets/dev.env", "copy .env")
        a.sh(f"{EG} --label a-encrypt-1 --sh 'sops encrypt -i secrets/dev.env'", "a-encrypt-1")
        a.sh(f"cd {R} && echo '.env' >> .gitignore", "gitignore")
        a.sh(f"cd {R} && git add .sops.yaml secrets/dev.env .gitignore", "git add")
        a.sh(f"cd {R} && git commit -m 'Add SOPS-encrypted secrets'", "git commit")

    DECRYPT = "sops decrypt secrets/dev.env > .env"
    DECRYPTED = ".env"

    def remove_and_rotate(a, keep_only):
        keep_only()
        a.sh(f"{EG} --label a-encrypt-2a --sh 'sops updatekeys -y secrets/*.env'", "a updatekeys")
        a.sh(f"{EG} --label a-encrypt-2b --sh 'sops rotate -i secrets/dev.env'", "a rotate")
        a.sh(f"cd {R} && git commit -am 'Remove B from secrets recipients'", "git commit")
        # prose after the block: change the credentials, "then put the new values in with sops edit" (no commit given)
        a.sh(f"python3 $F/q04/make_env.py {R}/.env {S}/values-v2.txt --version 2", "grader: new values (provider rotation)")
        a.sh(f"{EG} --label a-encrypt-2c --sh 'EDITOR=paste-v2 sops edit secrets/dev.env'", "a sops edit (paste new values)")


def pubkey(b) -> str:
    return b.get("/root/.config/sops/age/keys.txt").decode().split("# public key: ")[1].split()[0]


def sops_yaml(keys: list[str]) -> bytes:
    lines = ["creation_rules:", f"  - path_regex: {REGEX}", "    age: >-"]
    lines += [f"      {k}," for k in keys[:-1]] + [f"      {keys[-1]}"]
    return ("\n".join(lines) + "\n").encode()


with Flow(f"q04-{GROUP}", OUT, ["q04", "_shared"]) as flow:
    boxes = {n: flow.box(n) for n in "ABC"}
    a, b, c = boxes["A"], boxes["B"], boxes["C"]
    _, tag = a.sh(LATEST, "grader: latest sops release (fills vX.Y.Z)")
    ver = tag.strip().splitlines()[-1]
    for n, x in boxes.items():
        x.sh(f"git config --global user.name 'Developer {n}' && git config --global user.email dev-{n.lower()}@example.test"
             " && apt-get update -qq > /dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo > /dev/null",
             "environment: git identity, sudo (9.3 A)")
        x.sh(PASTE, "grader: EDITOR that pastes the new values")
        install(x, ver)
        keygen(x)
    ka, kb = pubkey(a), pubkey(b)
    # item 1 (box A)
    a.sh(f"sh $F/q04/setup_repo.sh {R} && mkdir -p {S} && python3 $F/q04/make_env.py {R}/.env {S}/values-v1.txt", "setup repo, .env v1")
    a.put(f"{R}/.sops.yaml", sops_yaml([ka, kb]))
    encrypt(a)
    a.sh(f"sh $F/q04/check_history.sh {R} {S}/values-v1.txt {ENC_FILE}", "ITEM 1 check_history")
    a.sh(f"git -C {R} bundle create /opt/eval/xfer/team-app.bundle --all", "bundle")
    bundle, v1 = a.get("/opt/eval/xfer/team-app.bundle"), a.get(f"{S}/values-v1.txt")
    # item 2 (boxes B, C)
    for x, who in ((b, "b"), (c, "c")):
        x.put("/opt/eval/xfer/team-app.bundle", bundle)
        x.put(f"{S}/values-v1.txt", v1)
        x.sh(f"git clone /opt/eval/xfer/team-app.bundle {R}", "clone")
        x.sh(f"{EG} --label {who}-decrypt-1 --stdout {S}/{who}1.out --stderr {S}/{who}1.err --sh '{DECRYPT}'", f"{who}-decrypt-1")
    b.sh(f"sh $F/q04/check_values.sh present {S}/values-v1.txt {R}/{DECRYPTED} {S}/b1.out", "ITEM 2 B present")
    c.sh(f"sh $F/q04/check_values.sh absent {S}/values-v1.txt {R} {S}/c1.out {S}/c1.err", "ITEM 2 C absent")
    # item 3 (A removes B and rotates; B tries in its old clone and a fresh one)
    remove_and_rotate(a, lambda: a.put(f"{R}/.sops.yaml", sops_yaml([ka])))
    a.sh(f"git -C {R} bundle create /opt/eval/xfer/team-app.bundle --all", "bundle 2")
    b.put("/opt/eval/xfer/team-app.bundle", a.get("/opt/eval/xfer/team-app.bundle"))
    b.put(f"{S}/values-v2.txt", a.get(f"{S}/values-v2.txt"))
    b.sh(f"cd {R} && git pull --ff-only", "B pull")
    b.sh(f"{EG} --label b-decrypt-2 --stdout {S}/b2.out --stderr {S}/b2.err --sh '{DECRYPT}'", "b-decrypt-2")
    b.sh(f"git clone /opt/eval/xfer/team-app.bundle {R}-fresh", "fresh clone")
    b.sh(f"python3 $SHARED/egress.py run --out {S}/egress --cwd {R}-fresh --label b-decrypt-3 --stdout {S}/b3.out "
         f"--stderr {S}/b3.err --sh '{DECRYPT}'", "b-decrypt-3")
    b.sh(f"sh $F/q04/check_values.sh absent {S}/values-v2.txt {R} {R}-fresh {S}/b2.out {S}/b2.err {S}/b3.out {S}/b3.err",
         "ITEM 3 B absent (v2)")
    # item 4: each box's own report (traces may hold written data, so they stay in the boxes; README section 2)
    verdicts = {}
    for n, x in boxes.items():
        x.sh(f"python3 $SHARED/egress.py stop --out {S}/egress", "egress stop")
        x.sh(f"tail -n 3 {S}/egress/*.stderr", "stderr tails of the traced steps (errors only; outputs went to files)")
        rc, out = x.sh(f"python3 $SHARED/egress.py report --out {S}/egress --json /tmp/eg-{n}.json", f"ITEM 4 egress report box {n}")
        verdicts[n] = rc
        (OUT / f"q04-egress-{n}.json").write_bytes(x.get(f"/tmp/eg-{n}.json"))
    flow.log.append({"box": "grader", "what": "ITEM 4 (every box exit 0 = pass)", "exit": max(verdicts.values()), "tail": str(verdicts)})
    print("ITEM 4 per box", verdicts)
