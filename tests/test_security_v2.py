"""pickfit.security sec.v2 (docs/proposals/security.md S1-S8): where each package sits, whether its vulnerable code runs,
the level per finding and per record, and what is stored. No network: OSV, CISA KEV, FIRST EPSS and deps.dev are
fixtures; repositories are folders written here."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pickfit import sbom, security
from pickfit.ledger import TAIPEI
from pickfit.schema import SecurityCheck, SoftwareRecord
from pickfit.score import build_web_scores
from tests.verify_fakes import FakeBox

ROOT = Path(__file__).resolve().parents[1]
WEB_FIXTURE = ROOT / "worker" / "test" / "fixtures" / "software" / "fixture-web-sketch.json"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=TAIPEI)
SEC_V2_SCHEMA = "sec.v2" in SecurityCheck.model_fields["version"].annotation.__args__
needs_v2_schema = pytest.mark.skipif(not SEC_V2_SCHEMA, reason="apply loop/proposals/security-schema.patch")


def adv(vid: str, summary: str, severity: str = "HIGH", *, vector: str | None = None, aliases: list[str] | None = None,
        package: tuple[str, str] | None = None, fixed: str | None = None, **extra: Any) -> dict[str, Any]:
    v: dict[str, Any] = {"id": vid, "summary": summary, "aliases": aliases or [], "database_specific": {"severity": severity},
                         "published": "2026-10-01T00:00:00Z", "modified": "2026-10-02T00:00:00Z"}
    if vector:
        v["severity"] = [{"type": "CVSS_V3", "score": vector}]
    if package:
        v["affected"] = [{"package": {"ecosystem": package[0], "name": package[1]},
                          "ranges": [{"events": [{"introduced": "0"}, {"fixed": fixed or "99.0.0"}]}]}]
    return v | extra


NET = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
NET_DOS = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H"
FILE = "CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H"


def fake_osv(monkeypatch: pytest.MonkeyPatch, hits: dict[tuple[str, str], list[str]], advisories: dict[str, Any]) -> None:
    def fake_http(url: str, body: Any = None, tries: int = 4) -> Any:
        if url.endswith("/querybatch"):
            return {"results": [{"vulns": [{"id": i} for i in hits.get((q["package"]["name"], q["version"]), [])]}
                                for q in body["queries"]]}
        if "/vulns/" in url:
            return advisories[url.rsplit("/", 1)[1]]
        raise AssertionError(f"no network in tests: {url}")

    monkeypatch.setattr(security, "_http", fake_http)


def run_check(monkeypatch: pytest.MonkeyPatch, repo: Path, raw: dict[str, Any], *, kev: dict[str, str] | None = None,
              sbom_doc: Any = None, crate_index: security.CrateIndex | None = None) -> security.CheckResult:
    monkeypatch.setattr(security, "clone", lambda url, slug, clones=None: (repo, "a" * 40))
    intel = security.Intel(kev if kev is not None else {}, kev_catalog="2026.11.19", epss={}, epss_date="2026-11-19",
                           day="2026-11-19")
    return security.check(raw, security.Advisories(), now=NOW, intel=intel, fix_dates=security.FixDates(False),
                          sbom=sbom_doc, crate_index=crate_index)


def record(slug: str, kind: str = "cli_tool", **over: Any) -> dict[str, Any]:
    return {"slug": slug, "name": slug, "kind": kind, "repo": {"url": f"https://github.com/o/{slug}",
                                                              "full_name": f"o/{slug}"},
            "platforms": ["macos", "linux", "windows"], "verification": {"runs": []}, "scores": None, **over}


def by_package(result: security.CheckResult) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for f in result.details["findings"]:
        out.setdefault(f"{f['package']}@{f['version']}", []).append(f)
    return out


def write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


# --- an OpenPets-style pnpm workspace ----------------------------------------------------------------------------------

OPENPETS_LOCK = """lockfileVersion: '9.0'

settings:
  autoInstallPeers: true

importers:

  .:
    devDependencies:
      typescript:
        specifier: ^6.0.3
        version: 6.0.3

  apps/desktop:
    dependencies:
      '@op/mcp':
        specifier: workspace:*
        version: link:../../packages/mcp
      '@op/openclaw':
        specifier: workspace:*
        version: link:../../packages/openclaw
      get-windows:
        specifier: ^9.3.0
        version: 9.3.0
      sharp:
        specifier: ^0.34.5
        version: 0.34.5
      undici:
        specifier: ^7.29.0
        version: 7.29.0
    devDependencies:
      electron:
        specifier: ^42.0.0
        version: 42.0.0
      vite:
        specifier: ^8.0.0
        version: 8.0.14

  packages/mcp:
    dependencies:
      '@modelcontextprotocol/sdk':
        specifier: ^1.29.0
        version: 1.29.0(zod@4.4.3)
      zod:
        specifier: ^4.4.3
        version: 4.4.3

  packages/openclaw:
    dependencies:
      openclaw:
        specifier: '*'
        version: 2026.1.0

  packages/pi:
    dependencies:
      '@earendil/pi-agent':
        specifier: '*'
        version: 0.74.0

packages:

  '@modelcontextprotocol/sdk@1.29.0':
    resolution: {integrity: sha512-x}
    peerDependencies:
      zod: ^4.0.0

  get-windows@9.3.0:
    resolution: {integrity: sha512-y}
    os: [darwin, win32, linux]

snapshots:

  '@modelcontextprotocol/sdk@1.29.0(zod@4.4.3)':
    dependencies:
      express: 5.2.1
      hono: 4.12.18
      zod: 4.4.3

  express@5.2.1:
    dependencies:
      proxy-addr: 2.0.7

  proxy-addr@2.0.7: {}

  hono@4.12.18: {}

  zod@4.4.3: {}

  get-windows@9.3.0:
    dependencies:
      node-gyp: 10.3.1

  node-gyp@10.3.1:
    dependencies:
      tar: 6.2.1

  tar@6.2.1: {}

  openclaw@2026.1.0:
    dependencies:
      tar: 7.5.19

  tar@7.5.19: {}

  sharp@0.34.5: {}

  undici@7.29.0: {}

  electron@42.0.0: {}

  vite@8.0.14: {}

  typescript@6.0.3: {}

  '@earendil/pi-agent@0.74.0': {}
"""

OPENPETS_ADVISORIES = {
    "GHSA-pa01": adv("GHSA-pa01", "proxy-addr vulnerable to IP spoofing via IPv4-mapped IPv6 trust subnet", "CRITICAL",
                     vector=NET, aliases=["CVE-2026-1001"], package=("npm", "proxy-addr"), fixed="2.0.8"),
    "GHSA-sd01": adv("GHSA-sd01", "MCP TypeScript SDK: HTTP server transports and handlers did not limit request size",
                     vector=NET_DOS, package=("npm", "@modelcontextprotocol/sdk"), fixed="1.30.1"),
    "GHSA-sd02": adv("GHSA-sd02", "MCP TypeScript SDK: ReDoS in UriTemplate", vector=NET_DOS,
                     package=("npm", "@modelcontextprotocol/sdk"), fixed="1.30.1"),
    "GHSA-ho01": adv("GHSA-ho01", "hono: CORS Middleware reflects any Origin with credentials", vector=NET,
                     package=("npm", "hono"), fixed="4.12.25"),
    "GHSA-ta01": adv("GHSA-ta01", "node-tar: Decompression/parse DoS via unlimited input", "CRITICAL",
                     package=("npm", "tar"), fixed="7.5.19"),
    "GHSA-ta02": adv("GHSA-ta02", "node-tar: Uncontrolled recursion in mapHas", package=("npm", "tar"), fixed="7.5.21"),
    "GHSA-oc01": adv("GHSA-oc01", "openclaw: predictable temp paths", package=("npm", "openclaw")),
    "GHSA-pi01": adv("GHSA-pi01", "Pi Agent: predictable extension install paths", package=("npm", "@earendil/pi-agent")),
    "GHSA-sh01": adv("GHSA-sh01", "sharp inherited vulnerabilities in libvips", vector=FILE, aliases=["CVE-2026-2001"],
                     package=("npm", "sharp"), fixed="0.35.0"),
    "GHSA-un01": adv("GHSA-un01", "undici vulnerable to TLS certificate validation bypass", vector=NET,
                     aliases=["CVE-2026-3001"], package=("npm", "undici"), fixed="7.30.1"),
    "GHSA-el01": adv("GHSA-el01", "Electron: sandboxed iframe can bypass allow-popups", package=("npm", "electron"),
                     fixed="42.0.1"),
    "GHSA-vi01": adv("GHSA-vi01", "vite dev server file read", vector=NET, package=("npm", "vite")),
    "GHSA-zo01": adv("GHSA-zo01", "Zod can exhaust memory while validating oversized collections", "MODERATE",
                     package=("npm", "zod")),
}
OPENPETS_HITS = {("proxy-addr", "2.0.7"): ["GHSA-pa01"], ("@modelcontextprotocol/sdk", "1.29.0"): ["GHSA-sd01", "GHSA-sd02"],
                 ("hono", "4.12.18"): ["GHSA-ho01"], ("tar", "6.2.1"): ["GHSA-ta01"], ("tar", "7.5.19"): ["GHSA-ta02"],
                 ("openclaw", "2026.1.0"): ["GHSA-oc01"], ("@earendil/pi-agent", "0.74.0"): ["GHSA-pi01"],
                 ("sharp", "0.34.5"): ["GHSA-sh01"], ("undici", "7.29.0"): ["GHSA-un01"],
                 ("electron", "42.0.0"): ["GHSA-el01"], ("vite", "8.0.14"): ["GHSA-vi01"], ("zod", "4.4.3"): ["GHSA-zo01"]}


def openpets(root: Path, *, http: bool = False) -> Path:
    write(root, "pnpm-lock.yaml", OPENPETS_LOCK)
    write(root, "package.json", json.dumps({"name": "op-workspace", "private": True}))
    write(root, "apps/desktop/package.json", json.dumps({"name": "@op/desktop", "private": True, "main": "dist/main.js"}))
    write(root, "apps/desktop/src/main.ts", "import { fetch } from 'undici';\nimport sharp from 'sharp';\n")
    write(root, "packages/mcp/package.json", json.dumps({"name": "@op/mcp", "bin": {"op-mcp": "dist/index.js"}}))
    write(root, "packages/mcp/src/index.ts",
          'import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";\n'
          'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n')
    if http:
        write(root, "packages/mcp/src/http.ts",
              'import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";\n')
    write(root, "packages/openclaw/package.json", json.dumps({"name": "@op/openclaw", "peerDependencies": {"openclaw": "*"}}))
    write(root, "packages/pi/package.json", json.dumps({"name": "@op/pi", "peerDependencies": {"@earendil/pi-agent": "*"}}))
    return root


def test_openpets_workspace_each_finding_lands_where_it_belongs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, OPENPETS_HITS, OPENPETS_ADVISORIES)
    result = run_check(monkeypatch, openpets(tmp_path / "repo"), record("openpets", "desktop_app"))
    got = by_package(result)
    level = {k: [f["level"] for f in v] for k, v in got.items()}
    # The MCP SDK's HTTP side (express > proxy-addr, hono, its own HTTP advisory): the stdio server never loads it.
    assert level["npm:proxy-addr@2.0.7"] == ["present_unreachable"]
    assert level["npm:hono@4.12.18"] == ["present_unreachable"]
    sdk = {f["advisory"]: f for f in got["npm:@modelcontextprotocol/sdk@1.29.0"]}
    assert sdk["GHSA-sd01"]["level"] == "present_unreachable" and sdk["GHSA-sd01"]["reachability"]["method"] == "entry_point_grep"
    assert sdk["GHSA-sd02"]["level"] == "conditional"  # the SDK's own ReDoS is not about HTTP: not settled
    assert got["npm:proxy-addr@2.0.7"][0]["paths"] == [
        "apps/desktop > @op/mcp > @modelcontextprotocol/sdk > express > proxy-addr"] or \
        got["npm:proxy-addr@2.0.7"][0]["paths"][0].endswith("@modelcontextprotocol/sdk > express > proxy-addr")
    # tar under node-gyp builds a native addon; tar under openclaw comes with a peer; vite is a dev dependency;
    # the pi plugin is a workspace member the desktop app does not ship.
    assert (got["npm:tar@6.2.1"][0]["scope"], got["npm:tar@6.2.1"][0]["level"]) == ("build", "not_shipped")
    assert (got["npm:tar@7.5.19"][0]["scope"], got["npm:tar@7.5.19"][0]["level"]) == ("peer", "not_shipped")
    assert (got["npm:openclaw@2026.1.0"][0]["scope"], got["npm:openclaw@2026.1.0"][0]["level"]) == ("peer", "not_shipped")
    assert (got["npm:vite@8.0.14"][0]["scope"], got["npm:vite@8.0.14"][0]["level"]) == ("dev", "not_shipped")
    assert got["npm:@earendil/pi-agent@0.74.0"][0]["level"] == "not_shipped"
    assert got["npm:@earendil/pi-agent@0.74.0"][0]["scope"] in ("workspace", "peer")
    # What runs: electron (a dev dependency whose runtime ships in the app), sharp and undici.
    for pkg in ("npm:electron@42.0.0", "npm:sharp@0.34.5", "npm:undici@7.29.0"):
        assert level[pkg] == ["conditional"], pkg
    assert "user_interaction" in got["npm:sharp@0.34.5"][0]["preconditions"]
    # A moderate one is observed, not counted.
    assert got["npm:zod@4.4.3"][0]["counted"] is False
    a = result["assessment"]
    assert a["level"] == "conditional" and result["status"] == "vulnerable"
    assert a["counts"] == {"conditional": 4, "present_unreachable": 3, "not_shipped": 5} and a["uncounted"] == 1
    cover = result["coverage"]
    assert (cover["state"], cover["target"], cover["gaps"]) == ("complete", "repo_lockfile", [])
    assert cover["packages_found"] == cover["packages_checked"] == result["packages_checked"]
    assert cover["components"] == [{"ecosystem": "npm", "component": "pnpm-lock.yaml", "status": "scanned",
                                    "packages": result["packages_checked"], "gaps": []}]
    assert result["findings_total"] == 4 and {f["level"] for f in result["findings"]} == {"conditional",
                                                                                           "present_unreachable"}
    assert [f["package"] for f in result["findings"][:4]] == ["npm:@modelcontextprotocol/sdk", "npm:electron",
                                                              "npm:sharp", "npm:undici"]
    obs = result["observation"]
    assert obs["target"] == "repo_lockfile" and obs["commit"] == "a" * 40 and obs["findings_total"] == 13
    # node-gyp and tar build; vite is the app's dev tool; the root's typescript and the pi plugin are not the app's.
    assert (obs["scopes"]["build"], obs["scopes"]["dev"], obs["scopes"]["workspace"]) == (2, 1, 2)
    if SEC_V2_SCHEMA:
        SecurityCheck.model_validate(result)


def test_openpets_with_an_http_transport_the_sdk_side_is_reached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, OPENPETS_HITS, OPENPETS_ADVISORIES)
    result = run_check(monkeypatch, openpets(tmp_path / "repo", http=True), record("openpets", "desktop_app"))
    got = by_package(result)
    proxy = got["npm:proxy-addr@2.0.7"][0]
    assert proxy["reachability"]["result"] == "reachable" and proxy["level"] == "exposed"  # a call path, over the network
    assert proxy["reachability"]["evidence"][0].startswith("packages/mcp/src/http.ts:1:")
    assert result["assessment"]["level"] == "exposed"


def test_the_mcp_sdk_http_client_and_server_are_told_apart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 11/19, continue: an SSE client reaches the SDK's client code, not its HTTP server transports.
    advisories = OPENPETS_ADVISORIES | {
        "GHSA-sd03": adv("GHSA-sd03", "MCP TypeScript SDK: OAuth client could send credentials to an authorization server",
                         vector=NET, package=("npm", "@modelcontextprotocol/sdk"), fixed="1.31.0")}
    hits = OPENPETS_HITS | {("@modelcontextprotocol/sdk", "1.29.0"): ["GHSA-sd01", "GHSA-sd02", "GHSA-sd03"]}
    fake_osv(monkeypatch, hits, advisories)
    repo = openpets(tmp_path / "repo")
    write(repo, "packages/mcp/src/remote.ts", 'import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";\n')
    got = {f["advisory"]: f for f in run_check(monkeypatch, repo, record("openpets", "desktop_app")).details["findings"]}
    assert got["GHSA-sd03"]["level"] == "exposed"  # the OAuth client: imported
    assert got["GHSA-sd01"]["level"] == "present_unreachable"  # the HTTP server transports: never loaded
    assert got["GHSA-pa01"]["level"] == "present_unreachable"  # express > proxy-addr: server side


def test_evidence_sits_in_a_file_that_imports_the_package(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 11/19, eli-v2-0: `trust_remote_code=True` in a sample script for another library is no evidence about diffusers.
    advisories = {"GHSA-df01": adv("GHSA-df01", "Diffusers has a `trust_remote_code` bypass via `custom_pipeline`",
                                   package=("PyPI", "diffusers"))}
    fake_osv(monkeypatch, {("diffusers", "0.37.1"): ["GHSA-df01"]}, advisories)
    repo = tmp_path / "repo"
    write(repo, "requirements.txt", "diffusers==0.37.1\n")
    write(repo, "app/finetune.py", "from transformers import AutoModel\nAutoModel.from_pretrained(x, trust_remote_code=True)\n")
    write(repo, "app/gen.py", "from diffusers import DiffusionPipeline\n")
    f = run_check(monkeypatch, repo, record("tool")).details["findings"][0]
    assert (f["reachability"]["result"], f["level"]) == ("unknown", "conditional")
    write(repo, "app/gen.py", "from diffusers import DiffusionPipeline\nDiffusionPipeline.from_pretrained(x, custom_pipeline=p)\n")
    f = run_check(monkeypatch, repo, record("tool")).details["findings"][0]
    assert f["reachability"]["evidence"] == ["app/gen.py:2: DiffusionPipeline.from_pretrained(x, custom_pipeline=p)"]


def test_a_go_function_is_called_through_its_package_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 11/19, detent: `detent.StaticFS()` is the project's own function, not echo's middleware.StaticFS.
    advisories = {"GHSA-ec01": adv("GHSA-ec01", "Echo: encoded slash bypasses route protection", aliases=["GO-2026-0003"],
                                   package=("Go", "github.com/labstack/echo/v4")),
                  "GO-2026-0003": {"id": "GO-2026-0003", "affected": [{"ecosystem_specific": {"imports": [
                      {"path": "github.com/labstack/echo/v4/middleware", "symbols": ["StaticFS"]}]}}]}}
    fake_osv(monkeypatch, {("github.com/labstack/echo/v4", "v4.15.1"): ["GHSA-ec01"]}, advisories)
    repo = tmp_path / "repo"
    write(repo, "go.mod", "module example.com/d\n\ngo 1.25\n\nrequire github.com/labstack/echo/v4 v4.15.1\n")
    write(repo, "a.go", 'package d\n\nimport "github.com/labstack/echo/v4/middleware"\n\nvar _ = middleware.Logger\n'
                        'func f() { detent.StaticFS() }\n')
    f = run_check(monkeypatch, repo, record("d")).details["findings"][0]
    assert (f["reachability"]["result"], f["level"]) == ("unknown", "conditional")
    write(repo, "a.go", 'package d\n\nimport "github.com/labstack/echo/v4/middleware"\n\nfunc f() { e.Use(middleware.StaticFS(fs)) }\n')
    f = run_check(monkeypatch, repo, record("d")).details["findings"][0]
    assert f["level"] == "exposed" and f["reachability"]["evidence"][0].startswith("a.go:5:")
    assert security._go_package_name("gopkg.in/yaml.v3") == "yaml"
    # A method symbol: called on a value, but not through another package the file imports.
    src = tmp_path / "methods"
    write(src, "b.go", 'package d\n\nimport (\n\t"github.com/labstack/echo/v4"\n\t"example.com/detent"\n)\n\n'
                       'func f() { detent.StaticFS() }\n')
    assert security.go_call(security.Sources(src), "github.com/labstack/echo/v4", "Echo.StaticFS") is None
    write(src, "b.go", 'package d\n\nimport (\n\tlabecho "github.com/labstack/echo/v4"\n)\n\n'
                       'func f() { e := labecho.New(); e.StaticFS("/", fs) }\n')
    assert security.go_call(security.Sources(src), "github.com/labstack/echo/v4", "Echo.StaticFS").startswith("b.go:7:")
    write(src, "b.go", 'package d\n\nimport labecho "github.com/labstack/echo/v4"\n\nfunc f() { labecho.New().StaticFS("/", fs) }\n')
    assert security.go_call(security.Sources(src), "github.com/labstack/echo/v4", "Echo.StaticFS").startswith("b.go:5:")


def test_a_kev_entry_blocks_only_where_the_code_reaches_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, OPENPETS_HITS, OPENPETS_ADVISORIES)
    kev = {"CVE-2026-3001": "2026-11-01", "CVE-2026-1001": "2026-11-01"}
    result = run_check(monkeypatch, openpets(tmp_path / "repo"), record("openpets", "desktop_app"), kev=kev)
    got = by_package(result)
    # On KEV, but nothing shows undici's affected code runs: conditional, named first for review (S6's queue).
    assert got["npm:undici@7.29.0"][0]["kev"] is True and got["npm:undici@7.29.0"][0]["level"] == "conditional"
    # KEV on code shown unreachable does not block either.
    assert got["npm:proxy-addr@2.0.7"][0]["kev"] is True and got["npm:proxy-addr@2.0.7"][0]["level"] == "present_unreachable"
    assert result["assessment"]["level"] == "conditional" and result["findings"][0]["advisory"] == "GHSA-un01"
    assert result["assessment"]["reasons"][0].startswith("kev:GHSA-un01")
    # The HTTP transport imported: the code reaches proxy-addr, which is on KEV.
    result = run_check(monkeypatch, openpets(tmp_path / "http", http=True), record("openpets", "desktop_app"), kev=kev)
    assert by_package(result)["npm:proxy-addr@2.0.7"][0]["level"] == "blocked"
    assert result["assessment"]["level"] == "blocked" and result["assessment"]["reasons"][0].startswith("kev:GHSA-pa01")


# --- Cargo: an optional dependency, dev, build and another platform ------------------------------------------------------

CARGO_LOCK = """version = 4

[[package]]
name = "tool"
version = "0.1.0"
dependencies = ["quinn", "zip", "pulldown-cmark", "criterion", "winapi", "cc"]

[[package]]
name = "quinn"
version = "0.11.9"
source = "registry+https://github.com/rust-lang/crates.io-index"
dependencies = ["quinn-proto"]

[[package]]
name = "quinn-proto"
version = "0.11.17"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "zip"
version = "8.6.0"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "pulldown-cmark"
version = "0.13.0"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "criterion"
version = "0.5.1"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "winapi"
version = "0.3.9"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "cc"
version = "1.2.0"
source = "registry+https://github.com/rust-lang/crates.io-index"
"""

CARGO_TOML = """[package]
name = "tool"
version = "0.1.0"
edition = "2021"

[dependencies]
quinn = { version = "0.11", optional = true }
zip = "8"
pulldown-cmark = "0.13"

[features]
default = []
http3 = ["dep:quinn"]

[dev-dependencies]
criterion = "0.5"

[build-dependencies]
cc = "1"

[target.'cfg(windows)'.dependencies]
winapi = "0.3"
"""

CARGO_ADVISORIES = {
    "RUSTSEC-2026-0340": adv("RUSTSEC-2026-0340", "Peer minimum ACK delay can panic quinn-proto when ACK_FREQUENCY is enabled",
                             package=("crates.io", "quinn-proto")),
    "RUSTSEC-2026-0369": adv("RUSTSEC-2026-0369", "ZipStreamReader::extract() and ZipArchive::extract() apply Unix "
                             "permissions through symlinks", "CRITICAL", package=("crates.io", "zip")),
    "GHSA-zp01": adv("GHSA-zp01", "zip: Parser Differential via Dual-Header Inconsistencies", "CRITICAL",
                     package=("crates.io", "zip")),
    "RUSTSEC-2026-0433": adv("RUSTSEC-2026-0433", "Quadratic parsing of nested image wikilinks with `ENABLE_WIKILINKS`",
                             package=("crates.io", "pulldown-cmark")),
    "RUSTSEC-2026-0500": adv("RUSTSEC-2026-0500", "criterion: bad thing", package=("crates.io", "criterion")),
    "RUSTSEC-2026-0501": adv("RUSTSEC-2026-0501", "winapi: bad thing", package=("crates.io", "winapi")),
    "RUSTSEC-2026-0502": adv("RUSTSEC-2026-0502", "cc: bad thing", package=("crates.io", "cc")),
}
CARGO_HITS = {("quinn-proto", "0.11.17"): ["RUSTSEC-2026-0340"], ("zip", "8.6.0"): ["RUSTSEC-2026-0369", "GHSA-zp01"],
              ("pulldown-cmark", "0.13.0"): ["RUSTSEC-2026-0433"], ("criterion", "0.5.1"): ["RUSTSEC-2026-0500"],
              ("winapi", "0.3.9"): ["RUSTSEC-2026-0501"], ("cc", "1.2.0"): ["RUSTSEC-2026-0502"]}


def cargo_repo(root: Path, main: str = "fn main() { let a = zip::ZipArchive::new(f); }\n") -> Path:
    write(root, "Cargo.lock", CARGO_LOCK)
    write(root, "Cargo.toml", CARGO_TOML)
    write(root, "src/main.rs", main)
    return root


def test_cargo_optional_dev_build_and_other_platform_dependencies_are_not_shipped(monkeypatch: pytest.MonkeyPatch,
                                                                                 tmp_path: Path) -> None:
    fake_osv(monkeypatch, CARGO_HITS, CARGO_ADVISORIES)
    result = run_check(monkeypatch, cargo_repo(tmp_path / "repo"), record("tool", platforms=["linux", "macos"]))
    got = {f["package"]: f for f in result.details["findings"] if f["advisory"] != "GHSA-zp01"}
    # quinn-proto is locked, but only the non-default http3 feature turns quinn on (11/19: 55 records hit this).
    assert (got["crates:quinn-proto"]["scope"], got["crates:quinn-proto"]["level"]) == ("optional", "not_shipped")
    assert (got["crates:criterion"]["scope"], got["crates:winapi"]["scope"], got["crates:cc"]["scope"]) == \
        ("dev", "platform", "build")
    assert all(got[p]["level"] == "not_shipped" for p in ("crates:criterion", "crates:winapi", "crates:cc"))
    # The project is zip's only user and never calls extract(); nor does it turn on ENABLE_WIKILINKS.
    assert got["crates:zip"]["level"] == "present_unreachable"
    assert got["crates:zip"]["reachability"]["method"] == "symbol_grep"
    assert got["crates:pulldown-cmark"]["level"] == "present_unreachable"
    assert got["crates:pulldown-cmark"]["reachability"]["method"] == "option_grep"
    assert "option:ENABLE_WIKILINKS" in got["crates:pulldown-cmark"]["preconditions"]
    # A zip advisory that names nothing to look for stays conditional.
    zp = next(f for f in result.details["findings"] if f["advisory"] == "GHSA-zp01")
    assert zp["level"] == "conditional" and result["assessment"]["level"] == "conditional"


def test_crates_io_index_settles_an_optional_dependency_of_a_dependency(monkeypatch: pytest.MonkeyPatch,
                                                                         tmp_path: Path) -> None:
    # 11/19: quinn-proto under reqwest > quinn. reqwest's http3 feature turns quinn on; the project asks for json.
    lock = ('version = 4\n\n[[package]]\nname = "tool"\nversion = "0.1.0"\ndependencies = ["reqwest"]\n\n'
            '[[package]]\nname = "reqwest"\nversion = "0.12.9"\nsource = "registry+x"\n'
            'dependencies = ["quinn", "serde_json"]\n\n'
            '[[package]]\nname = "quinn"\nversion = "0.11.9"\nsource = "registry+x"\ndependencies = ["quinn-proto"]\n\n'
            '[[package]]\nname = "quinn-proto"\nversion = "0.11.17"\nsource = "registry+x"\n\n'
            '[[package]]\nname = "serde_json"\nversion = "1.0.0"\nsource = "registry+x"\n')
    repo = tmp_path / "repo"
    write(repo, "Cargo.lock", lock)
    write(repo, "Cargo.toml", '[package]\nname = "tool"\nversion = "0.1.0"\n\n[dependencies]\n'
                              'reqwest = { version = "0.12", features = ["json"] }\n')
    write(repo, "src/main.rs", "fn main() {}\n")
    index = tmp_path / "index"
    write(index, "reqwest.jsonl", json.dumps({
        "name": "reqwest", "vers": "0.12.9",
        "deps": [{"name": "quinn", "req": "^0.11", "optional": True, "kind": "normal"},
                 {"name": "serde_json", "req": "^1", "optional": True, "kind": "normal"},
                 {"name": "tokio-test", "req": "^0.4", "optional": False, "kind": "dev"}],
        "features": {"default": [], "json": ["dep:serde_json"], "http3": ["dep:quinn"]}}) + "\n")
    fake_osv(monkeypatch, {("quinn-proto", "0.11.17"): ["RUSTSEC-2026-0340"]}, CARGO_ADVISORIES)
    result = run_check(monkeypatch, repo, record("tool"), crate_index=security.CrateIndex(index, fetch=False))
    f = result.details["findings"][0]
    assert (f["scope"], f["level"]) == ("optional", "not_shipped")
    assert f["paths"] == ["tool > reqwest > quinn > quinn-proto"]
    # Without the index, Cargo.lock's edge stands; asking for http3 turns it on.
    assert run_check(monkeypatch, repo, record("tool")).details["findings"][0]["scope"] == "runtime"
    write(repo, "Cargo.toml", '[package]\nname = "tool"\nversion = "0.1.0"\n\n[dependencies]\n'
                              'reqwest = { version = "0.12", features = ["json", "http3"] }\n')
    result = run_check(monkeypatch, repo, record("tool"), crate_index=security.CrateIndex(index, fetch=False))
    assert result.details["findings"][0]["scope"] == "runtime"


def test_an_option_set_off_or_named_in_a_comment_is_not_evidence(tmp_path: Path) -> None:
    write(tmp_path, "a.py", "# trust_remote_code is unsafe\nload(trust_remote_code=False)\n")
    write(tmp_path, "b.py", "load(trust_remote_code=True)\n")
    sources = security.Sources(tmp_path)
    token = re.compile(r"\btrust_remote_code\b")
    assert sources.find(token, "pypi", reject=security._off("trust_remote_code")) == "b.py:1: load(trust_remote_code=True)"
    (tmp_path / "b.py").unlink()
    assert security.Sources(tmp_path).find(token, "pypi", reject=security._off("trust_remote_code")) is None


def test_cargo_calls_found_in_the_source_are_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, CARGO_HITS, CARGO_ADVISORIES)
    main = ("use pulldown_cmark::Options;\nfn main() {\n    let o = Options::ENABLE_WIKILINKS;\n"
            "    let mut z = zip::ZipArchive::new(f).unwrap();\n    z.extract(dir).unwrap();\n}\n")
    result = run_check(monkeypatch, cargo_repo(tmp_path / "repo", main), record("tool", platforms=["windows"]))
    got = {f["advisory"]: f for f in result.details["findings"]}
    assert got["RUSTSEC-2026-0433"]["reachability"]["evidence"][0].startswith("src/main.rs:3:")
    assert got["RUSTSEC-2026-0369"]["reachability"]["evidence"][0].startswith("src/main.rs:5:")
    assert got["RUSTSEC-2026-0369"]["level"] == "exposed"  # no CVSS vector: reachable is enough
    assert got["RUSTSEC-2026-0501"]["scope"] == "runtime"  # winapi ships on Windows


# --- Go: a module whose vulnerable package is never imported -----------------------------------------------------------

GO_MOD = """module example.com/tool

go 1.25

require (
\tgolang.org/x/crypto v0.51.0
\tgithub.com/klauspost/compress v1.18.0 // indirect
)
"""

GO_ADVISORIES = {
    "GHSA-xc01": adv("GHSA-xc01", "golang.org/x/crypto: Invoking VerifiedPublicKeyCallback permissions skip enforcement",
                     "CRITICAL", aliases=["GO-2026-0001", "CVE-2026-4001"], package=("Go", "golang.org/x/crypto")),
    "GO-2026-0001": {"id": "GO-2026-0001", "aliases": ["GHSA-xc01"], "affected": [
        {"package": {"ecosystem": "Go", "name": "golang.org/x/crypto"},
         "ecosystem_specific": {"imports": [{"path": "golang.org/x/crypto/ssh", "symbols": ["ServerConn.Verify"]}]}}]},
    "GHSA-kc01": adv("GHSA-kc01", "klauspost/compress: zstd decoder DoS", aliases=["GO-2026-0002"],
                     package=("Go", "github.com/klauspost/compress")),
    "GO-2026-0002": {"id": "GO-2026-0002", "affected": [{"ecosystem_specific": {"imports": [
        {"path": "github.com/klauspost/compress/zstd"}]}}]},
}
GO_HITS = {("golang.org/x/crypto", "v0.51.0"): ["GHSA-xc01"], ("github.com/klauspost/compress", "v1.18.0"): ["GHSA-kc01"]}


def test_go_without_an_import_of_x_crypto_ssh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, GO_HITS, GO_ADVISORIES)
    repo = tmp_path / "repo"
    write(repo, "go.mod", GO_MOD)
    write(repo, "main.go", 'package main\n\nimport (\n\t"golang.org/x/crypto/bcrypt"\n)\n')
    write(repo, "main_test.go", 'package main\n\nimport "golang.org/x/crypto/ssh"\n')  # tests do not ship
    result = run_check(monkeypatch, repo, record("tool"))
    got = {f["advisory"]: f for f in result.details["findings"]}
    assert got["GHSA-xc01"]["level"] == "present_unreachable"
    assert got["GHSA-xc01"]["reachability"]["method"] == "import_grep"
    assert "golang.org/x/crypto/ssh" in got["GHSA-xc01"]["reachability"]["evidence"][0]
    # An indirect module: something else may import the package, so it is not settled.
    assert got["GHSA-kc01"]["level"] == "conditional"
    assert result["assessment"]["level"] == "conditional"
    # Imported but the vulnerable function never called: not settled (the import alone is not a call).
    write(repo, "ssh.go", 'package main\n\nimport "golang.org/x/crypto/ssh"\n\nvar _ = ssh.Dial\n')
    result = run_check(monkeypatch, repo, record("tool"))
    got = {f["advisory"]: f for f in result.details["findings"]}
    assert got["GHSA-xc01"]["reachability"]["result"] == "unknown"
    assert got["GHSA-xc01"]["reachability"]["evidence"][0].startswith("ssh.go:3:")
    assert got["GHSA-xc01"]["level"] == "conditional"
    # Called: the call is the evidence.
    write(repo, "ssh.go", 'package main\n\nimport "golang.org/x/crypto/ssh"\n\n'
                          'func check(c *ssh.ServerConn) {\n\t// c.Verify is what the advisory names\n\tc.Verify(nil)\n}\n')
    result = run_check(monkeypatch, repo, record("tool"))
    got = {f["advisory"]: f for f in result.details["findings"]}
    assert got["GHSA-xc01"]["reachability"]["evidence"][0] == "ssh.go:7: c.Verify(nil)"  # the comment is skipped
    assert got["GHSA-xc01"]["level"] == "exposed"


def test_govulncheck_on_the_installed_binary_settles_go_findings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, GO_HITS, GO_ADVISORIES)
    repo = tmp_path / "repo"
    write(repo, "go.mod", GO_MOD)
    raw = record("tool", verification={"runs": [{"id": "verify-tool-1", "level": "function",
                                                  "checked_at": "2026-11-19T10:00:00+08:00"}]})
    doc = {"run_id": "verify-tool-1", "tool_version": "1.2.3", "govulncheck_ran": True,
           "artifacts": [{"path": "/home/sbx/go/bin/tool", "sha256": "b" * 64}],
           "packages": [{"ecosystem": "go", "name": "golang.org/x/crypto", "version": "v0.51.0",
                         "found_by": "go-module-binary-cataloger", "locations": ["/go/bin/tool"]},
                        {"ecosystem": "go", "name": "github.com/klauspost/compress", "version": "v1.18.0",
                         "found_by": "go-module-binary-cataloger", "locations": ["/go/bin/tool"]}],
           "govulncheck": [{"binary": "/home/sbx/go/bin/tool", "osv": "GO-2026-0001", "level": "package",
                            "package": "golang.org/x/crypto/ssh"},
                           {"binary": "/home/sbx/go/bin/tool", "osv": "GO-2026-0002", "level": "symbol",
                            "function": "zstd.Decoder.DecodeAll"}]}
    result = run_check(monkeypatch, repo, raw, sbom_doc=doc)
    got = {f["advisory"]: f for f in result.details["findings"]}
    assert got["GHSA-xc01"]["reachability"]["method"] == "govulncheck_binary"
    assert got["GHSA-xc01"]["level"] == "present_unreachable"  # compiled in, never called
    assert got["GHSA-kc01"]["level"] == "exposed"  # called
    obs = result["observation"]
    assert (obs["target"], obs["run_id"], obs["tool_version"], obs["artifact_sha256"]) == \
        ("installed_artifact", "verify-tool-1", "1.2.3", ["b" * 64])
    assert all(f["in_artifact"] for f in result.details["findings"])


# --- Next.js built as a static export ----------------------------------------------------------------------------------

NEXT_ADVISORIES = {
    "GHSA-nx01": adv("GHSA-nx01", "Next.js: Unauthenticated Remote Code Execution in Image Optimization API", "CRITICAL",
                     vector=NET, package=("npm", "next")),
    "GHSA-nx02": adv("GHSA-nx02", "Next.js: XSS in the client-side router", package=("npm", "next")),
    "GHSA-pc01": adv("GHSA-pc01", "PostCSS: path traversal in source map auto-loading", package=("npm", "postcss")),
}
NEXT_HITS = {("next", "16.0.10"): ["GHSA-nx01", "GHSA-nx02"], ("postcss", "8.4.31"): ["GHSA-pc01"]}


def next_repo(root: Path, config: str) -> Path:
    write(root, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
        "": {"name": "site", "dependencies": {"next": "16.0.10", "react": "19.0.0"}},
        "node_modules/next": {"version": "16.0.10", "dependencies": {"postcss": "8.4.31"}},
        "node_modules/postcss": {"version": "8.4.31"},
        "node_modules/react": {"version": "19.0.0"}}}))
    write(root, "next.config.mjs", config)
    write(root, "app/page.tsx", "export default function Page() { return null }\n")
    return root


def test_nextjs_static_export_has_no_server_to_attack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, NEXT_HITS, NEXT_ADVISORIES)
    repo = next_repo(tmp_path / "repo", "const nextConfig = { output: 'export', images: { unoptimized: true } };\n"
                                        "export default nextConfig;\n")
    result = run_check(monkeypatch, repo, record("site", "web_app"))
    got = {f["advisory"]: f for f in result.details["findings"]}
    assert got["GHSA-nx01"]["level"] == "not_shipped" and got["GHSA-nx01"]["reachability"]["method"] == "next_static_export"
    assert "server_side" in got["GHSA-nx01"]["preconditions"]
    assert got["GHSA-nx02"]["level"] == "conditional"  # client-side: the exported pages carry it
    assert (got["GHSA-pc01"]["scope"], got["GHSA-pc01"]["level"]) == ("build", "not_shipped")  # postcss under next
    assert result["assessment"]["level"] == "conditional"
    # The same app with a server: the server-side advisory stays.
    other = next_repo(tmp_path / "server", "export default { reactStrictMode: true };\n")
    result = run_check(monkeypatch, other, record("site", "web_app"))
    assert {f["advisory"]: f["level"] for f in result.details["findings"]}["GHSA-nx01"] == "conditional"


# --- npm: a development dependency -------------------------------------------------------------------------------------


def test_an_npm_dev_dependency_is_counted_but_not_held_against_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, {("vitest", "1.0.0"): ["GHSA-vt01"], ("esbuild", "0.19.0"): ["GHSA-es01"]},
             {"GHSA-vt01": adv("GHSA-vt01", "vitest RCE when the API server listens", "CRITICAL", vector=NET,
                               package=("npm", "vitest")),
              "GHSA-es01": adv("GHSA-es01", "esbuild dev server CORS", package=("npm", "esbuild"))})
    repo = tmp_path / "repo"
    write(repo, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
        "": {"name": "tool", "bin": {"tool": "cli.js"}, "dependencies": {"chalk": "5.3.0"},
             "devDependencies": {"vitest": "1.0.0"}},
        "node_modules/chalk": {"version": "5.3.0"},
        "node_modules/vitest": {"version": "1.0.0", "dev": True, "dependencies": {"esbuild": "0.19.0"}},
        "node_modules/esbuild": {"version": "0.19.0", "dev": True}}}))
    result = run_check(monkeypatch, repo, record("tool"))
    got = {f["package"]: f for f in result.details["findings"]}
    assert (got["npm:vitest"]["scope"], got["npm:vitest"]["level"]) == ("dev", "not_shipped")
    assert got["npm:esbuild"]["scope"] == "dev" and got["npm:esbuild"]["paths"] == [". > vitest > esbuild"]
    assert got["npm:vitest"]["vex"] == {"status": "not_affected", "justification": "component_not_present"}
    a = result["assessment"]
    assert (a["level"], result["status"], result["findings_total"], a["counts"]) == \
        ("not_shipped", "clean", 0, {"not_shipped": 2})
    assert result["findings"] == []  # not_shipped findings are only counted in the record
    assert result.details["findings"]  # and kept in full in data/security/<slug>.json
    if SEC_V2_SCHEMA:
        SecurityCheck.model_validate(result)


# --- the installed artifact (S3) -----------------------------------------------------------------------------------------


def test_the_sbom_decides_what_is_in_the_artifact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, {("left-pad", "1.0.0"): ["GHSA-lp01"], ("chalk", "5.3.0"): ["GHSA-ch01"],
                           ("chalk", "5.4.0"): ["GHSA-ch02"]},
             {"GHSA-lp01": adv("GHSA-lp01", "left-pad bad", package=("npm", "left-pad")),
              "GHSA-ch01": adv("GHSA-ch01", "chalk bad", package=("npm", "chalk")),
              "GHSA-ch02": adv("GHSA-ch02", "chalk 5.4 bad", package=("npm", "chalk"))})
    repo = tmp_path / "repo"
    write(repo, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {
        "": {"name": "tool", "dependencies": {"chalk": "^5", "left-pad": "1"}},
        "node_modules/chalk": {"version": "5.3.0"}, "node_modules/left-pad": {"version": "1.0.0"}}}))
    raw = record("tool", verification={"runs": [{"id": "verify-tool-2", "level": "function",
                                                  "checked_at": "2026-11-19T10:00:00+08:00"}]})
    doc = {"run_id": "verify-tool-2", "tool_version": "2.0.0", "packages": [
        {"ecosystem": "npm", "name": "tool", "version": "2.0.0", "found_by": "npm-ls", "locations": ["tool"]},
        {"ecosystem": "npm", "name": "chalk", "version": "5.4.0", "found_by": "npm-ls", "locations": ["tool > chalk"]}]}
    result = run_check(monkeypatch, repo, raw, sbom_doc=doc)
    got = {f["advisory"]: f for f in result.details["findings"]}
    # The repository's lockfile pins chalk 5.3.0 and left-pad; the release installed chalk 5.4.0 and no left-pad.
    assert (got["GHSA-ch01"]["in_artifact"], got["GHSA-ch01"]["level"]) == (False, "not_shipped")
    assert (got["GHSA-lp01"]["in_artifact"], got["GHSA-lp01"]["level"]) == (False, "not_shipped")
    assert (got["GHSA-ch02"]["in_artifact"], got["GHSA-ch02"]["found_in"], got["GHSA-ch02"]["level"]) == \
        (True, "sbom:verify-tool-2", "conditional")
    assert result["observation"]["target"] == "installed_artifact"
    assert any(s.startswith("sbom:verify-tool-2") for s in result["sources"])


# --- the policy, pure ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("finding", "level"), [
    ({"malicious": True, "scope": "dev"}, "blocked"),
    ({"scope": "build"}, "not_shipped"),
    ({"scope": "runtime", "in_artifact": False}, "not_shipped"),
    ({"reachability": {"method": "next_static_export", "result": "not_reachable"}}, "not_shipped"),
    ({"reachability": {"method": "symbol_grep", "result": "not_reachable"}, "kev": True}, "present_unreachable"),
    ({"reachability": {"method": "import_grep", "result": "reachable"}, "kev": True, "attack_vector": "local"}, "blocked"),
    ({"kev": True}, "conditional"),
    ({"reachability": {"method": "symbol_grep", "result": "reachable"}, "attack_vector": "network"}, "exposed"),
    ({"reachability": {"method": "symbol_grep", "result": "reachable"}, "attack_vector": "local"}, "conditional"),
    ({"reachability": {"method": "symbol_grep", "result": "unknown"}}, "conditional"),
    ({}, "conditional"),
])
def test_finding_levels(finding: dict[str, Any], level: str) -> None:
    assert security.finding_level(finding) == level


def f(level: str, severity: str = "HIGH", **over: Any) -> dict[str, Any]:
    return {"package": "npm:x", "version": "1.0.0", "advisory": f"GHSA-{level}", "severity": severity, "level": level,
            "counted": severity in ("HIGH", "CRITICAL"), **over}


def test_the_level_is_the_worst_counted_finding_and_coverage_is_apart() -> None:
    a = lambda fs: security.assess(fs, now=NOW)  # noqa: E731
    assert a([f("present_unreachable"), f("conditional"), f("not_shipped")])["level"] == "conditional"
    assert a([f("present_unreachable"), f("not_shipped")])["level"] == "present_unreachable"
    assert a([f("not_shipped")])["level"] == "not_shipped"
    assert a([f("exposed", "MODERATE")])["level"] == "none"  # observed, not counted
    assert a([])["level"] == "none"
    got = a([f("conditional"), f("conditional", "CRITICAL"), f("not_shipped", "LOW")])
    assert got["counts"] == {"conditional": 2} and got["uncounted"] == 1 and "complete" not in got
    assert got["reasons"][0].startswith("worst:GHSA-conditional npm:x@1.0.0 (conditional)")
    # Coverage: unknowns are never a level. Unchecked when nothing was checked, partial with a gap.
    c = lambda checked, gaps: security.coverage("repo_lockfile", checked, [], gaps, now=NOW)  # noqa: E731
    assert c(10, [])["state"] == "complete" and c(0, [])["state"] == "unchecked"
    partial = c(10, [security.gap("lockfile.unsupported_format", "npm", "web/yarn.lock", "yarn_lock", found=30)])
    assert (partial["state"], partial["packages_checked"], partial["packages_found"]) == ("partial", 10, 40)
    # The sec.v1 status: vulnerable only for a level that warns; an unknown is unchecked, never vulnerable.
    assert {security.status_for(lvl, s) for lvl in ("blocked", "exposed", "conditional")
            for s in security.COVERAGE_STATES} == {"vulnerable"}
    assert {security.status_for(lvl, "complete") for lvl in ("present_unreachable", "not_shipped", "none")} == {"clean"}
    assert {security.status_for(lvl, s) for lvl in ("present_unreachable", "not_shipped", "none")
            for s in ("partial", "unchecked")} == {"unchecked"}


def test_level_of_reads_the_assessment_and_says_none_for_a_sec_v1_record() -> None:
    assert security.level_of({"security": {"version": "sec.v2", "assessment": {"level": "not_shipped"}}}) == "not_shipped"
    assert security.level_of({"security": {"version": "sec.v1", "status": "vulnerable"}}) is None
    assert security.level_of({}) is None
    assert security.legacy_level({"status": "vulnerable", "findings": [{"malicious": True}]}) == "blocked"
    assert security.legacy_level({"status": "vulnerable", "findings": [{}]}) == "conditional"
    assert security.legacy_level({"status": "unchecked"}) == security.legacy_level(None) == "none"
    assert security.coverage_of({"security": {"status": "clean"}}) == "complete"
    assert security.coverage_of({"security": {"status": "unchecked"}}) == "unchecked"
    assert security.coverage_of({}) == "unchecked"


def test_gaps_follow_the_taxonomy_and_sec_v1_reasons_map_onto_it() -> None:
    for code, (category, capability) in security.GAP_CODES.items():
        g = security.gap(code, "npm", "x", "yarn_lock is not read yet", now=NOW)
        assert (g["category"], g["first_seen"], g["last_seen"]) == (category, "2026-11-19", "2026-11-19")
        assert "{" not in g["capability"]
    assert security.gap("adapter.missing", "rubygems")["capability"] == "adapter:rubygems"
    assert security.gap("lockfile.unsupported_format", "npm", None, "yarn_lock is not read")["capability"] == \
        "read_lockfile:yarn_lock"
    v1 = {"version": "sec.v1", "status": "unchecked", "unchecked_reason": "no_lockfile", "checked_at": "2026-11-03T21:00:00+08:00"}
    assert [(g["code"], g["ecosystem"], g["first_seen"]) for g in security.gaps_of({"security": v1})] == [
        ("lockfile.missing", "unknown", "2026-11-03")]
    assert {r: security.LEGACY_GAP[r] for r in ("resolve_failed", "no_source", "lockfile_not_supported")} == {
        "resolve_failed": "resolve.registry_failed", "no_source": "source.none",
        "lockfile_not_supported": "lockfile.unsupported_format"}
    assert security.gaps_of({"security": {"version": "sec.v1", "status": "clean"}}) == []
    assert security.gaps_of({}) == []  # never checked: counted apart as not run
    # A gap seen before keeps its first_seen.
    again = security.coverage("repo_lockfile", 3, [], [security.gap("lockfile.missing", "npm", now=NOW)],
                              previous=security.gaps_of({"security": v1}), now=NOW)
    assert again["gaps"][0]["first_seen"] == "2026-11-03"


def test_the_repository_read_names_every_gap(tmp_path: Path) -> None:
    write(tmp_path, "package.json", json.dumps({"dependencies": {"a": "1", "b": "2"}}))  # no lockfile
    write(tmp_path, "web/yarn.lock", '"left-pad@^1.0.0":\n  version "1.3.0"\n\nchalk@^5:\n  version "5.3.0"\n')
    write(tmp_path, "web/package.json", json.dumps({"dependencies": {"left-pad": "^1"}}))  # its yarn.lock covers it
    write(tmp_path, "Cargo.toml", '[package]\nname = "t"\n\n[dependencies]\nzip = "8"\n')  # no Cargo.lock
    write(tmp_path, "android/build.gradle", "dependencies {\n    implementation 'a:b:1'\n    api 'c:d:2'\n}\n")
    write(tmp_path, "native/CMakeLists.txt", "project(x)\n")
    write(tmp_path, "requirements.txt", "requests\nrich>=13\n")
    write(tmp_path, "go.mod", "module x\n\ngo 1.25\n\nrequire github.com/a/b v1.2.3\n")
    write(tmp_path, "sub/Cargo.lock", "not toml [[[")
    got = security.repo_deps(tmp_path)
    gaps = {(g["code"], g["ecosystem"], g["component"]): g.get("found") for g in got.gaps}
    assert gaps == {("lockfile.missing", "npm", "package.json"): 2, ("lockfile.missing", "crates", "Cargo.toml"): 1,
                    ("lockfile.unsupported_format", "npm", "web/yarn.lock"): 2,
                    ("adapter.missing", "maven", "android/build.gradle"): 2,
                    ("advisory_db.no_ecosystem", "c/c++", "native/CMakeLists.txt"): None,
                    ("lockfile.missing", "pypi", "requirements.txt"): 2,
                    ("lockfile.parse_error", "crates", "sub/Cargo.lock"): None}
    assert [c["component"] for c in got.components if c["status"] == "scanned"] == ["go.mod"]
    empty = tmp_path / "empty"
    write(empty, "README.md", "hello\n")
    assert [g["code"] for g in security.repo_deps(empty).gaps] == ["lockfile.none_found"]


def test_gap_report_groups_by_code_ecosystem_category_and_platform() -> None:
    v2 = {"category": "dev_cli", "verification": {"runs": [{"os": "macos"}]}, "security": {"coverage": {
        "state": "partial", "gaps": [security.gap("lockfile.unsupported_format", "npm", "yarn.lock", "yarn_lock", found=9),
                                     security.gap("adapter.missing", "maven", "build.gradle")]}}}
    v1 = {"category": "mcp_server", "verification": {"runs": [{"os": "linux"}]},
          "security": {"version": "sec.v1", "status": "unchecked", "unchecked_reason": "no_source"}}
    report = security.gap_report([v2, v1, {"category": "x"}])
    assert (report["records"], report["not_run"], report["records_with_gaps"]) == (3, 1, 2)
    assert report["coverage"] == {"partial": 1, "unchecked": 1}
    assert report["by_code"] == {"lockfile.unsupported_format": 1, "adapter.missing": 1, "source.none": 1}
    assert report["by_category"]["no_source"] == 1 and report["by_ecosystem"]["maven"] == 1
    assert report["by_software_category"]["mcp_server:source.none"] == 1
    assert report["by_platform"]["macos:adapter.missing"] == 1 and report["packages_hidden"]["lockfile.unsupported_format"] == 9


def test_the_levels_match_the_schema_patch() -> None:
    from pickfit import schema

    if not SEC_V2_SCHEMA:
        pytest.skip("apply loop/proposals/security-schema.patch")
    assert schema.SECURITY_LEVELS == security.LEVELS and schema.FINDING_LEVELS == security.FINDING_LEVELS
    assert schema.COVERAGE_STATES == security.COVERAGE_STATES
    assert schema.GAP_CATEGORY == {code: category for code, (category, _) in security.GAP_CODES.items()}
    for level in security.LEVELS:
        for state in security.COVERAGE_STATES:
            assert schema.security_status_for(level, state) == security.status_for(level, state)


def test_advisory_facts_and_tokens() -> None:
    facts = security.advisory_facts(adv("GHSA-a", "x", vector=NET_DOS) | {"database_specific": {"cwe_ids": ["CWE-400"]}})
    assert (facts["attack_vector"], facts["dos_only"], facts["cwes"]) == ("network", True, ["CWE-400"])
    assert security.advisory_facts(adv("GHSA-b", "Remote code execution via crafted input"))["dos_only"] is None
    assert security.advisory_facts(adv("GHSA-c", "Quadratic run time when checking a start tag"))["dos_only"] is True
    options, symbols = security.advisory_tokens(adv("X", "DOMPurify SAFE_FOR_TEMPLATES bypass when `RETURN_DOM` is set"))
    assert options == ["SAFE_FOR_TEMPLATES", "RETURN_DOM"] and symbols == []
    options, symbols = security.advisory_tokens(adv("X", "proxy bypass when HTTPS_PROXY and NO_PROXY are set"))
    assert options == []  # environment variables are the person's, not the code's
    _, symbols = security.advisory_tokens(adv("X", "Unbounded allocation in `NsReader`; X509Ref::ocsp_responders UB"))
    assert symbols == ["NsReader", "X509Ref::ocsp_responders"]
    _, symbols = security.advisory_tokens({"id": "GHSA-2v37-7h3g-55p8", "summary": "nanoid: custom generators loop"})
    assert symbols == ["customAlphabet", "customRandom"]
    assert security.purl("npm", "@scope/pkg", "1.0.0") == "pkg:npm/%40scope/pkg@1.0.0"
    assert security.purl("pypi", "Foo_Bar", "2.0") == "pkg:pypi/foo-bar@2.0"
    assert security.cvss_preconditions({"cvss_v3": FILE, "dos_only": False}) == ["local_access", "user_interaction"]


def test_cfg_targets() -> None:
    assert security.cfg_matches("cfg(windows)", "windows") and not security.cfg_matches("cfg(windows)", "linux")
    assert security.cfg_matches("cfg(unix)", "macos") and not security.cfg_matches("cfg(unix)", "windows")
    assert security.cfg_matches('cfg(target_os = "macos")', "macos")
    assert not security.cfg_matches('cfg(any(target_os = "android", target_os = "ios"))', "linux")
    assert security.cfg_matches('cfg(not(target_arch = "wasm32"))', "linux")
    assert not security.cfg_matches('cfg(target_arch = "wasm32")', "linux")
    assert security.cfg_matches('cfg(all(unix, not(target_os = "macos")))', "linux")
    assert security.cfg_matches("x86_64-pc-windows-msvc", "windows") and not security.cfg_matches("x86_64-pc-windows-msvc", "linux")


# --- writing, the sidecar, re-assessing, staleness ----------------------------------------------------------------------


def scored_web(security_check: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.loads(WEB_FIXTURE.read_text(encoding="utf-8"))
    if security_check is not None:
        data["security"] = security_check
    data["scores"] = build_web_scores(SoftwareRecord.model_validate(data), stars=None, hn=4, now=NOW)
    return data


@needs_v2_schema
def test_write_security_stores_the_details_beside_the_record(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, OPENPETS_HITS, OPENPETS_ADVISORIES)
    result = run_check(monkeypatch, openpets(tmp_path / "repo"), record("fixture-web-sketch", "desktop_app"))
    software = tmp_path / "data" / "software"
    software.mkdir(parents=True)
    path = software / "fixture-web-sketch.json"
    path.write_text(json.dumps(scored_web()), encoding="utf-8")
    written = security.write_security(path, result, NOW)
    details = tmp_path / "data" / "security" / "fixture-web-sketch.json"
    text = details.read_text(encoding="utf-8")
    obs = written["security"]["observation"]
    assert obs["details"] == "security/fixture-web-sketch.json"
    assert obs["details_sha256"] == __import__("hashlib").sha256(text.encode()).hexdigest()
    from pickfit.schema import SecurityDetails

    full = SecurityDetails.model_validate_json(text)
    assert len(full.findings) == 13 and full.assessment.level == "conditional"
    stored = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
    assert stored.security.assessment.level == "conditional" and stored.security.status == "vulnerable"
    assert stored.scores.quality.cap_reason == "known_vulnerability"  # status vulnerable: sec.v1's cap still reads it
    # Re-judging offline from the stored details gives the same level, with no lookups.
    monkeypatch.setattr(security, "_http", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    again = security.reassess(json.loads(path.read_text(encoding="utf-8")), security.Advisories(), now=NOW,
                              details_dir=details.parent)
    assert again["level"] == "conditional" and again["matched"] == 13


@needs_v2_schema
def test_a_blocked_kev_entry_hides_the_record(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_osv(monkeypatch, OPENPETS_HITS, OPENPETS_ADVISORIES)
    result = run_check(monkeypatch, openpets(tmp_path / "repo", http=True), record("fixture-web-sketch", "desktop_app"),
                       kev={"CVE-2026-1001": "2026-11-01"})
    path = tmp_path / "software" / "fixture-web-sketch.json"
    path.parent.mkdir()
    path.write_text(json.dumps(scored_web()), encoding="utf-8")
    written = security.write_security(path, result, NOW)
    assert written["status"] == "hidden" and "CISA KEV" in written["status_reason"]


@needs_v2_schema
def test_the_index_carries_the_level_and_the_unreachable_findings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from pickfit.index import _security
    from pickfit.score import refresh_scores

    fake_osv(monkeypatch, OPENPETS_HITS, OPENPETS_ADVISORIES)
    result = run_check(monkeypatch, openpets(tmp_path / "repo"), record("fixture-web-sketch", "desktop_app"))
    data = scored_web()
    data["security"] = dict(result)
    refresh_scores(data, NOW)
    entry = _security(SoftwareRecord.model_validate(data))
    assert (entry["status"], entry["level"], entry["target"], entry["count"]) == \
        ("vulnerable", "conditional", "repo_lockfile", 4)
    assert entry["counts"] == {"conditional": 4, "present_unreachable": 3, "not_shipped": 5}
    assert entry["coverage"] == {"state": "complete", "packages_checked": result["packages_checked"],
                                 "packages_found": result["packages_checked"], "gaps": []}
    assert {f["level"] for f in entry["findings"]} == {"conditional"}
    sharp = next(f for f in entry["findings"] if f["package"] == "npm:sharp")
    assert sharp["preconditions"] == ["local_access", "user_interaction"] and sharp["scope"] == "runtime"
    assert {u["package"] for u in entry["unreachable"]} == {"npm:proxy-addr", "npm:hono", "npm:@modelcontextprotocol/sdk"}
    assert entry["unreachable"][0]["method"] == "entry_point_grep"


def test_reassess_estimates_a_sec_v1_record_from_its_findings_and_a_cached_clone(monkeypatch: pytest.MonkeyPatch,
                                                                                 tmp_path: Path) -> None:
    fake_osv(monkeypatch, OPENPETS_HITS, OPENPETS_ADVISORIES)
    openpets(tmp_path / "clones" / "openpets")
    (tmp_path / "clones" / "openpets" / ".git").mkdir()
    stored = [{"package": "npm:proxy-addr", "version": "2.0.7", "advisory": "GHSA-pa01", "cves": [], "severity": "CRITICAL",
               "fixed_in": "2.0.8", "summary": "proxy-addr spoofing", "malicious": False},
              {"package": "npm:tar", "version": "6.2.1", "advisory": "GHSA-ta01", "cves": [], "severity": "CRITICAL",
               "fixed_in": "7.5.19", "summary": "tar", "malicious": False}]
    raw = record("openpets", "desktop_app", security={
        "version": "sec.v1", "status": "vulnerable", "unchecked_reason": None,
        "sources": ["github.com/o/openpets@5235d5677f01", "pnpm-lock.yaml"], "packages_checked": 755,
        "findings_total": 2, "advisories_total": 2, "findings": stored, "database": "OSV.dev",
        "checked_at": "2026-11-03T21:41:45+08:00"})
    got = security.reassess(raw, security.Advisories(), now=NOW, clones=tmp_path / "clones")
    assert got["level"] == "present_unreachable" and got["matched"] == 2 and not got["truncated"]
    assert {f["advisory"]: f["level"] for f in got["findings"]} == {"GHSA-pa01": "present_unreachable",
                                                                    "GHSA-ta01": "not_shipped"}


def test_stale_records() -> None:
    assert security.stale({}, 14, NOW)
    assert security.stale({"security": {"checked_at": (NOW - timedelta(days=15)).isoformat()}}, 14, NOW)
    assert not security.stale({"security": {"checked_at": (NOW - timedelta(days=3)).isoformat()}}, 14, NOW)


# --- pickfit/sbom.py ---------------------------------------------------------------------------------------------------


def test_the_in_box_reducer_reads_syft_npm_and_govulncheck(tmp_path: Path) -> None:
    work = tmp_path / "w"
    work.mkdir()
    (work / "reduce.py").write_text(sbom.REDUCER, encoding="utf-8")
    (work / "syft.json").write_text(json.dumps({"descriptor": {"version": "1.56.0"}, "artifacts": [
        {"name": "golang.org/x/crypto", "version": "v0.51.0", "type": "go-module", "purl": "pkg:golang/x@v0.51.0",
         "foundBy": "go-module-binary-cataloger", "locations": [{"path": "/go/bin/tool"}]},
        {"name": "zip", "version": "8.6.0", "type": "rust-crate", "foundBy": "cargo-auditable-binary-cataloger",
         "locations": [{"path": "/.cargo/bin/rtool"}]},
        {"name": "rich", "version": "13.0.0", "type": "python", "foundBy": "python-installed-package-cataloger",
         "locations": [{"path": "/.local/share/uv/tools/t/lib/python3.12/site-packages/rich-13.0.0.dist-info/METADATA"}]}]}))
    (work / "npm.json").write_text(json.dumps({"dependencies": {"tool": {"version": "2.0.0", "dependencies": {
        "chalk": {"version": "5.4.0"}}}}}))
    (work / "artifacts.txt").write_text(f"{'c' * 64}  /home/sbx/go/bin/tool\nnot a line\n")
    (work / "status").write_text("syft 0\nnpm 1\n")
    out = subprocess.run([sys.executable, "-I", str(work / "reduce.py"), "base", str(work), "/home/sbx"],
                         capture_output=True, text=True, check=True)
    inv = json.loads(out.stdout)
    assert inv["syft_version"] == "1.56.0" and inv["go_binaries"] == ["/home/sbx/go/bin/tool"]
    assert inv["rust_binaries"] == ["/home/sbx/.cargo/bin/rtool"]
    assert [(p["ecosystem"], p["name"]) for p in inv["packages"]] == [
        ("go", "golang.org/x/crypto"), ("crates", "zip"), ("pypi", "rich"), ("npm", "tool"), ("npm", "chalk")]
    assert inv["packages"][-1]["locations"] == ["tool > chalk"]
    assert inv["artifacts"] == [{"sha256": "c" * 64, "path": "/home/sbx/go/bin/tool"}]
    stream = (json.dumps({"config": {}}, indent=2) + "\n" +
              json.dumps({"finding": {"osv": "GO-1", "trace": [{"module": "m", "version": "v1"}]}}, indent=2) +
              json.dumps({"finding": {"osv": "GO-1", "fixed_version": "v2", "trace": [
                  {"module": "m", "package": "m/p", "function": "Do", "receiver": "*T"}]}}))
    (work / "g.json").write_text(stream)
    out = subprocess.run([sys.executable, "-I", str(work / "reduce.py"), "govuln", str(work), str(work / "g.json"), "/b"],
                         capture_output=True, text=True, check=True)
    assert [json.loads(line) for line in out.stdout.splitlines()] == [
        {"binary": "/b", "osv": "GO-1", "level": "symbol", "module": "m", "version": None, "package": "m/p",
         "function": "*T.Do", "fixed_version": "v2"}]


def test_collect_runs_the_tools_in_the_box_and_writes_sbom_json(tmp_path: Path) -> None:
    box = FakeBox({"govulncheck": (0, "", ""), "cargo-audit": (3, "", "")})
    inventory = {"packages": [{"ecosystem": "go", "name": "golang.org/x/crypto", "version": "v0.51.0",
                               "found_by": "go-module-binary-cataloger"}],
                 "go_binaries": ["/home/sbx/go/bin/tool"], "rust_binaries": ["/home/sbx/.cargo/bin/r"],
                 "artifacts": [{"sha256": "d" * 64, "path": "/home/sbx/go/bin/tool"}], "syft_version": "1.56.0",
                 "status": {"syft": "0", "npm": "1"}, "errors": {}}
    box.files[f"{sbom.WORK}/inventory.json"] = json.dumps(inventory).encode()
    box.files[f"{sbom.WORK}/govuln.jsonl"] = (json.dumps({"osv": "GO-1", "level": "symbol"}) + "\n").encode()
    doc = sbom.collect(box, tmp_path, run_id="verify-tool-3", tool_version="1.0", log=lambda line: None)
    assert doc is not None and box.files[f"{sbom.WORK}/reduce.py"] == sbom.REDUCER.encode()
    commands = [c for c, _ in box.ran]
    assert commands[0].startswith("mkdir -p /tmp/pickfit-sbom") and "--override-default-catalogers image" in commands[0]
    assert "/usr/local/bin/syft scan dir:/home/sbx" in commands[0] and "--exclude './.cache/**'" in commands[0]
    assert "npm ls -g --all --omit=dev --json" in commands[0]
    assert "govulncheck -mode=binary -json /home/sbx/go/bin/tool" in commands[1]
    assert "cargo-audit audit --db /tmp/pickfit-sbom/advisory-db --json bin /home/sbx/.cargo/bin/r" in commands[2]
    assert doc["govulncheck"] == [{"osv": "GO-1", "level": "symbol"}] and doc["govulncheck_ran"]
    assert doc["errors"] == ["cargo audit /home/sbx/.cargo/bin/r: exited 3"]  # reported, never raised
    saved = json.loads((tmp_path / "sbom.json").read_text(encoding="utf-8"))
    assert (saved["run_id"], saved["tool_version"], saved["tools"]["syft"]) == ("verify-tool-3", "1.0", "1.56.0")
    # What security.check reads from it.
    inv = security.installed_of({"slug": "tool", "verification": {"runs": []}}, saved)
    assert inv is not None and inv.covered == {"go"} and inv.govuln["GO-1"][0] == "symbol" and inv.govuln_ran
    assert inv.artifacts == ["d" * 64]


def test_collect_never_raises_and_skips_other_systems(tmp_path: Path) -> None:
    box = FakeBox({"mkdir -p /tmp/pickfit-sbom": (1, "", "no space")})
    doc = sbom.collect(box, tmp_path, run_id="r", log=lambda line: None)
    assert doc is not None and doc["packages"] == [] and doc["errors"]
    mac = FakeBox()
    mac.os = "macos"
    assert sbom.collect(mac, tmp_path, run_id="r", log=lambda line: None) is None
