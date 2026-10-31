"""Pinned tools and files for calibration and L2 (9.3 B.4; 念誠's decision 2, 2026-10-31).

Everything is fetched from its official source, fixed by version and sha256, and never
committed: the list and the hashes are. Three steps:

  pins.py resolve                     read official metadata (npm, Node's SHASUMS256, PyPI, GitHub
                                      releases, Hugging Face, the Ollama registry, Docker Hub) and
                                      write eval/fixtures/pins.json: version, URL, and the sha256 (or
                                      npm sha512) the source publishes
  pins.py verify --confirm-spend      download every file once inside a Modal sandbox (the dev image),
                                      hash it there, compare with the published value, record bytes
  pins.py render                      write eval/fixtures/PINS.md from pins.json

The choices follow each needs.json's first (recommended) candidate; versions are the latest
at the pin date. Run with: uv run python eval/runner/pins.py ...
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "eval" / "fixtures"
PINS_JSON = FIXTURES / "pins.json"
PINS_MD = FIXTURES / "PINS.md"
TAIPEI = dt.timezone(dt.timedelta(hours=8))
UA = {"User-Agent": "pickfit-eval-pins"}

NPM = [("claude-code", "@anthropic-ai/claude-code", "q01"), ("codex-cli", "@openai/codex", "q01"),
       ("gemini-cli", "@google/gemini-cli", "q01")]
PYPI = [("openai", "openai", "q12, q14, q20", "py3-none-any"), ("srt", "srt", "q15", "py3-none-any"),
        ("openai-whisper", "openai-whisper", "q15 (baseline)", "sdist"),
        ("fasttext", "fasttext", "q16", "cp312-cp312-manylinux_2_17_x86_64"),
        ("fonttools", "fonttools", "q05 (static Regular and Bold instances of the variable font)", "py3-none-any")]
OPENCC_FILES = ("STCharacters.txt", "STPhrases.txt", "TSCharacters.txt", "TWVariants.txt")
OLLAMA_MODELS = [("llama3.2:3b", "q18, q19 (tool-calling fixture model)"), ("qwen2.5:0.5b", "q20 (small model)")]
HF_FILES = [("mlx-community/Qwen2.5-1.5B-Instruct-4bit", None, "q12 (Mac, MLX fixture model)"),
            ("Qwen/Qwen2.5-1.5B-Instruct-GGUF", "qwen2.5-1.5b-instruct-q4_k_m.gguf", "q13 (GGUF fixture)")]
DOCKER = [("nginx:1.27-alpine", "q08"), ("redis:7.2-alpine", "q08")]
WHISPER_SMALL = ("https://openaipublic.azureedge.net/main/whisper/models/"
                 "9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt")
FASTTEXT_LID = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"


def now() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


def get(url: str, accept: str | None = None) -> bytes:
    headers = dict(UA, **({"Accept": accept} if accept else {}))
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return r.read()


def getj(url: str, accept: str | None = None) -> Any:
    return json.loads(get(url, accept))


def item(id_: str, used_by: str, version: str, url: str, *, sha256: str | None = None, sha512: str | None = None,
         published_by: str, note: str = "") -> dict[str, Any]:
    return {"id": id_, "used_by": used_by, "version": version, "url": url, "published_sha256": sha256,
            "published_sha512": sha512, "published_by": published_by, "note": note,
            "verified_sha256": None, "bytes": None, "verified_at": None, "verified_in": None}


def resolve() -> dict[str, Any]:
    """Fresh metadata; an item whose URL did not change keeps its earlier download check."""
    items = []
    for id_, pkg, used in NPM:
        m = getj(f"https://registry.npmjs.org/{pkg.replace('/', '%2F')}/latest")
        items.append(item(id_, used, m["version"], m["dist"]["tarball"], sha512=m["dist"]["integrity"],
                          published_by="npm registry dist.integrity"))
        # The launcher's Linux x64 binary comes from a pinned optional dependency; pin that file too.
        for dep, spec in (m.get("optionalDependencies") or {}).items():
            if not dep.endswith("linux-x64"):
                continue
            real, _, ver = spec[4:].rpartition("@") if spec.startswith("npm:") else (dep, "", spec)
            d = getj(f"https://registry.npmjs.org/{real.replace('/', '%2F')}/{ver}")
            items.append(item(f"{id_}-{dep.rsplit('/', 1)[-1]}", used + f" (Linux x64 part of {pkg})", ver,
                              d["dist"]["tarball"], sha512=d["dist"]["integrity"],
                              published_by="npm registry dist.integrity"))
    index = getj("https://nodejs.org/dist/index.json")
    lts = next(r for r in index if r["lts"])
    sums = get(f"https://nodejs.org/dist/{lts['version']}/SHASUMS256.txt").decode()
    name = f"node-{lts['version']}-linux-x64.tar.xz"
    items.append(item("nodejs", "q01 (runtime of the agent CLIs)", lts["version"],
                      f"https://nodejs.org/dist/{lts['version']}/{name}",
                      sha256=next(line.split()[0] for line in sums.splitlines() if line.endswith(name)),
                      published_by="nodejs.org SHASUMS256.txt", note=f"latest LTS ({lts['lts']}) at the pin date"))
    for id_, pkg, used, want in PYPI:
        m = getj(f"https://pypi.org/pypi/{pkg}/json")
        files = m["urls"]
        pick = next((f for f in files if want in f["filename"]), None) or next(
            (f for f in files if f["packagetype"] == "sdist"), files[0])
        items.append(item(id_, used, m["info"]["version"], pick["url"], sha256=pick["digests"]["sha256"],
                          published_by="PyPI JSON digests", note=pick["filename"]))
    tag = getj("https://api.github.com/repos/BYVoid/OpenCC/releases/latest")["tag_name"]
    for f in OPENCC_FILES:
        items.append(item(f"opencc-{f}", "q11, q15 (shared OpenCC scorer)", tag,
                          f"https://raw.githubusercontent.com/BYVoid/OpenCC/{tag}/data/dictionary/{f}",
                          published_by="none (hashed at download)"))
    rel = getj("https://api.github.com/repos/ollama/ollama/releases/latest")
    asset = next(a for a in rel["assets"] if a["name"] == "ollama-linux-amd64.tar.zst")
    sums = get(next(a for a in rel["assets"] if a["name"] == "sha256sum.txt")["browser_download_url"]).decode()
    items.append(item("ollama-linux-amd64", "q18, q19, q20", rel["tag_name"], asset["browser_download_url"],
                      sha256=next(line.split()[0] for line in sums.splitlines() if line.rstrip().endswith(asset["name"])),
                      published_by="release sha256sum.txt", note="zstd archive: unpacking needs zstd"))
    for tag_, used in OLLAMA_MODELS:
        model, t = tag_.split(":")
        man = getj(f"https://registry.ollama.ai/v2/library/{model}/manifests/{t}",
                   "application/vnd.docker.distribution.manifest.v2+json")
        layer = next(layer for layer in man["layers"] if layer["mediaType"].endswith(".model"))
        items.append(item(f"ollama-model-{tag_}", used, tag_,
                          f"https://registry.ollama.ai/v2/library/{model}/blobs/{layer['digest']}",
                          sha256=layer["digest"].split(":", 1)[1], published_by="Ollama registry manifest layer digest",
                          note=f"model layer, {layer['size']} bytes; the manifest's other layers are templates and licenses"))
    for repo, filename, used in HF_FILES:
        meta = getj(f"https://huggingface.co/api/models/{repo}/revision/main?blobs=true")
        rev = meta["sha"]
        for s in meta.get("siblings") or []:
            name = s["rfilename"]
            if filename and name != filename:
                continue
            lfs = s.get("lfs") or {}
            items.append(item(f"hf-{repo.split('/')[1]}-{name}", used, rev,
                              f"https://huggingface.co/{repo}/resolve/{rev}/{name}", sha256=lfs.get("sha256"),
                              published_by="Hugging Face LFS sha256" if lfs else "none (hashed at download)"))
    for ref, used in DOCKER:
        out = subprocess.run(["docker", "buildx", "imagetools", "inspect", ref], capture_output=True, text=True)
        digest = next((line.split()[-1] for line in out.stdout.splitlines() if line.startswith("Digest:")), None)
        items.append(item(f"docker-{ref}", used, ref, f"docker.io/library/{ref}@{digest}", sha256=digest,
                          published_by="Docker Hub index digest (not downloaded: Mac runs pull it)"))
    commits = getj("https://api.github.com/repos/google/fonts/commits?path=ofl/notosanstc&per_page=1")
    sha = commits[0]["sha"]
    tree = getj(f"https://api.github.com/repos/google/fonts/contents/ofl/notosanstc?ref={sha}")
    for f in (t for t in tree if t["name"].endswith(".ttf")):
        items.append(item(f"font-{f['name']}", "q05 (CJK font embedded in fixture.pdf)", sha[:12],
                          f"https://raw.githubusercontent.com/google/fonts/{sha}/ofl/notosanstc/{urllib.parse.quote(f['name'])}",
                          published_by="none (hashed at download)",
                          note="google/fonts ships a variable font; make_pdf.py prints the weight it uses (q05 needs.json)"))
    page = get("https://download.pytorch.org/whl/cpu/torch/").decode()
    wheels = re.findall(r'href="([^"]*?/(torch-([0-9.]+)%2Bcpu-cp312-cp312-manylinux_2_28_x86_64\.whl)#sha256=([0-9a-f]{64}))"', page)
    if wheels:
        best = max(wheels, key=lambda w: tuple(int(x) for x in w[2].split(".")))
        href, fname, ver, digest = best
        url = href.split("#")[0]
        url = url if url.startswith("http") else "https://download.pytorch.org" + url
        items.append(item("torch-cpu", "q15 (baseline: openai-whisper's dependency)", ver + "+cpu", url, sha256=digest,
                          published_by="download.pytorch.org index sha256", note=fname.replace("%2B", "+")))
    items.append(item("whisper-small.pt", "q15 (baseline)", "small", WHISPER_SMALL,
                      sha256=WHISPER_SMALL.split("/")[-2], published_by="openai-whisper _MODELS URL"))
    items.append(item("fasttext-lid.176.ftz", "q16 (language identifier)", "lid.176.ftz", FASTTEXT_LID,
                      published_by="none (hashed at download)"))
    return {"resolved_at": now(), "items": items}


VERIFY_SCRIPT = r'''
import hashlib, json, sys, urllib.request
items = json.load(open("/tmp/pins.json"))["items"]
out = {}
for it in items:
    if it["url"].startswith("docker.io/") or it.get("verified_sha256"):
        continue
    h256, h512, n = hashlib.sha256(), hashlib.sha512(), 0
    try:
        req = urllib.request.Request(it["url"], headers={"User-Agent": "pickfit-eval-pins"})
        with urllib.request.urlopen(req, timeout=600) as r:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                h256.update(chunk); h512.update(chunk); n += len(chunk)
        import base64
        out[it["id"]] = {"sha256": h256.hexdigest(), "sha512": "sha512-" + base64.b64encode(h512.digest()).decode(), "bytes": n}
    except Exception as e:
        out[it["id"]] = {"error": repr(e)}
    print(it["id"], out[it["id"]].get("bytes"), out[it["id"]].get("error", ""), flush=True)
json.dump(out, open("/tmp/verified.json", "w"))
'''


def verify(confirm: bool) -> int:
    if not confirm:
        print("refused: downloads run in a Modal sandbox; pass --confirm-spend")
        return 2
    import modal

    sys.path.insert(0, str(ROOT / "eval" / "runner"))
    import l2_image

    pins = json.loads(PINS_JSON.read_text(encoding="utf-8"))
    client = l2_image.modal_client()
    app = modal.App.lookup(l2_image.APP_NAME, create_if_missing=True, client=client)
    name = l2_image.read_record()["images"]["dev"]["name"]
    sb = modal.Sandbox.create("sleep", "3600", app=app, client=client, image=modal.Image.from_name(name),
                              timeout=3700, cpu=(2.0, 2.0), memory=(4096, 4096))
    try:
        l2_image.put(sb, "/tmp/pins.json", PINS_JSON.read_bytes())
        l2_image.put(sb, "/tmp/verify.py", VERIFY_SCRIPT.encode())
        proc = sb.exec("python3", "/tmp/verify.py")
        for line in proc.stdout:
            print(line, end="")
        proc.wait()
        cat = sb.exec("cat", "/tmp/verified.json")
        cat.wait()
        got = json.loads(cat.stdout.read())
    finally:
        sb.terminate()
    when, where = now(), f"Modal sandbox {getattr(sb, 'object_id', None)} ({name})"
    bad = 0
    for it in pins["items"]:
        g = got.get(it["id"])
        if not g:
            continue
        if "error" in g:
            it["verify_error"] = g["error"]
            bad += 1
            continue
        it.update(verified_sha256=g["sha256"], bytes=g["bytes"], verified_at=when, verified_in=where)
        it["matches_published"] = (
            g["sha256"] == it["published_sha256"] if it["published_sha256"]
            else g["sha512"] == it["published_sha512"] if it["published_sha512"] else None)
        if it["matches_published"] is False:
            bad += 1
    PINS_JSON.write_text(json.dumps(pins, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"verified {sum(1 for i in pins['items'] if i['verified_sha256'])}, problems {bad}")
    return 1 if bad else 0


def render() -> None:
    pins = json.loads(PINS_JSON.read_text(encoding="utf-8"))
    lines = ["# 固定版本的工具與檔案（9.3 B.4）", "",
             "校準與 L2 用的工具、模型、字典檔、字型等，一律從官方來源下載到沙盒，以版本號與 sha256 固定，**不 commit 進 repo**；"
             "這份清單與 sha256 才 commit。產生方式：`uv run python eval/runner/pins.py resolve`（讀官方的 metadata，記下來源公布的雜湊）→ "
             "`verify --confirm-spend`（在 Modal 的 dev image 沙盒裡下載每個檔、自己算 sha256、和公布的比對）→ `render`。"
             "選擇照各題 `needs.json` 的第一個（建議的）候選，版本取固定當天的最新版。原始資料在 [pins.json](pins.json)。", "",
             f"metadata 讀取：{pins['resolved_at']}", "",
             "| 項目 | 用在 | 版本 | sha256（沙盒內下載後算的） | 和來源公布的一致 | 大小 | 來源 |", "|---|---|---|---|---|---|---|"]
    for it in pins["items"]:
        match = {True: "是", False: "**否**", None: "（來源沒公布）"}[it.get("matches_published")] if it["verified_sha256"] else "—"
        sha = it["verified_sha256"] or (it["published_sha256"] or "") + ("（公布值，未下載）" if it["published_sha256"] else "")
        size = f"{it['bytes']:,}" if it["bytes"] else "—"
        lines.append(f"| `{it['id']}` | {it['used_by']} | `{it['version']}` | `{sha}` | {match} | {size} | {it['url']} |")
    runs = sorted({(i["verified_at"], i["verified_in"]) for i in pins["items"] if i["verified_at"]})
    if runs:
        lines += ["", "下載與雜湊：" + "；".join(f"{at}，{where}" for at, where in runs) + "。Docker 映像只記 Hub 公布的 digest（Mac 實跑時才 pull）。"]
    notes = [f"- `{i['id']}`：{i['note']}" for i in pins["items"] if i["note"]]
    if notes:
        lines += ["", "備註：", ""] + notes
    PINS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eval/runner/pins.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("resolve")
    v = sub.add_parser("verify")
    v.add_argument("--confirm-spend", action="store_true")
    sub.add_parser("render")
    a = p.parse_args(argv)
    if a.command == "resolve":
        fresh = resolve()
        old = {i["url"]: i for i in json.loads(PINS_JSON.read_text(encoding="utf-8"))["items"]} if PINS_JSON.exists() else {}
        for it in fresh["items"]:
            prev = old.get(it["url"])
            if prev and prev.get("verified_sha256"):
                for key in ("verified_sha256", "bytes", "verified_at", "verified_in", "matches_published"):
                    it[key] = prev.get(key)
        PINS_JSON.write_text(json.dumps(fresh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {PINS_JSON.relative_to(ROOT)}")
        return 0
    if a.command == "verify":
        return verify(a.confirm_spend)
    render()
    print(f"wrote {PINS_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
