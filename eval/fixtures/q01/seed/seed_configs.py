#!/usr/bin/env python3
"""Seed and check the q01 agent config files.

  seed   write every enabled location in locations.json with its one
         unrelated setting, and record what was written in a state file
  check  re-read every seeded file: it must still exist, still parse as
         JSON/TOML, and the seeded setting must be deep-equal to what was
         seeded. Also reports (for information only) which files now hold
         the fixture server and whether TOML comment lines survived.

Python 3.11+ standard library (tomllib). No network.

  python3 seed_configs.py seed  --home "$HOME" --project /work/proj \
      --fixture /opt/eval/fixtures/q01 --state /opt/eval/state/q01-seeded.json
  python3 seed_configs.py check --state /opt/eval/state/q01-seeded.json \
      [--report /opt/eval/state/q01-check.json]

Exit codes: 0 pass, 1 fail, 2 usage or environment error.
"""
import argparse
import hashlib
import json
import os
import sys

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

HERE = os.path.dirname(os.path.abspath(__file__))


def subst(value, mapping):
    if isinstance(value, str):
        for k, v in mapping.items():
            value = value.replace("{" + k + "}", v)
        return value
    if isinstance(value, list):
        return [subst(x, mapping) for x in value]
    if isinstance(value, dict):
        return {subst(k, mapping): subst(v, mapping) for k, v in value.items()}
    return value


def get_path(obj, path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError("/".join(path))
        cur = cur[key]
    return cur


def parse(fmt, data):
    if fmt == "json":
        return json.loads(data.decode("utf-8"))
    if fmt == "toml":
        return tomllib.loads(data.decode("utf-8"))
    raise ValueError("unknown format " + fmt)


def find_server(fmt, obj, name):
    """Where in this parsed file does the named server appear (information only)."""
    hits = []
    if not isinstance(obj, dict):
        return hits
    if fmt == "toml":
        if isinstance(obj.get("mcp_servers"), dict) and name in obj["mcp_servers"]:
            hits.append("mcp_servers." + name)
    else:
        if isinstance(obj.get("mcpServers"), dict) and name in obj["mcpServers"]:
            hits.append("mcpServers." + name)
        projects = obj.get("projects")
        if isinstance(projects, dict):
            for p, v in projects.items():
                if isinstance(v, dict) and isinstance(v.get("mcpServers"), dict) \
                        and name in v["mcpServers"]:
                    hits.append("projects[" + p + "].mcpServers." + name)
    return hits


def cmd_seed(a):
    if tomllib is None:
        print("error: needs Python 3.11+ (tomllib)", file=sys.stderr)
        return 2
    with open(a.locations, encoding="utf-8") as f:
        spec = json.load(f)
    mapping = {"HOME": os.path.abspath(a.home), "PROJECT": os.path.abspath(a.project),
               "FIXTURE": os.path.abspath(a.fixture)}
    entries = []
    for loc in spec["locations"]:
        if not loc.get("enabled", True):
            print("skip  %-15s (disabled in locations.json)" % loc["id"])
            continue
        path = subst(loc["path"], mapping)
        if os.path.exists(path) and not a.force:
            print("error: %s already exists; seed a fresh HOME/PROJECT (or --force)" % path,
                  file=sys.stderr)
            return 2
        if loc["format"] == "json":
            seed_obj = subst(loc["seed"], mapping)
            data = (json.dumps(seed_obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        else:
            data = subst(loc["seed_text"], mapping).encode("utf-8")
        key_path = subst(loc["key_path"], mapping)
        parsed = parse(loc["format"], data)
        expected = get_path(parsed, key_path)
        if "expect" in loc and expected != subst(loc["expect"], mapping):
            print("error: seed for %s does not hold its expected value" % loc["id"],
                  file=sys.stderr)
            return 2
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        entries.append({
            "id": loc["id"], "agent": loc["agent"], "scope": loc["scope"],
            "path": path, "format": loc["format"], "key_path": key_path,
            "expected": expected, "sha256": hashlib.sha256(data).hexdigest(),
            "comment_line": loc.get("comment_line"),
        })
        print("seed  %-15s %s" % (loc["id"], path))
    state = {"version": 1, "server_name": spec.get("server_name", "fixture-echo"),
             "mapping": mapping, "locations": entries}
    os.makedirs(os.path.dirname(os.path.abspath(a.state)), exist_ok=True)
    with open(a.state, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("state written to " + a.state)
    return 0


def cmd_check(a):
    if tomllib is None:
        print("error: needs Python 3.11+ (tomllib)", file=sys.stderr)
        return 2
    with open(a.state, encoding="utf-8") as f:
        state = json.load(f)
    name = a.server or state.get("server_name", "fixture-echo")
    results = []
    all_ok = True
    for e in state["locations"]:
        r = {"id": e["id"], "path": e["path"], "exists": False, "parses": False,
             "setting_unchanged": False, "byte_identical": False,
             "server_entries": [], "comment_kept": None, "error": None}
        try:
            with open(e["path"], "rb") as f:
                data = f.read()
            r["exists"] = True
            r["byte_identical"] = hashlib.sha256(data).hexdigest() == e["sha256"]
            obj = parse(e["format"], data)
            r["parses"] = True
            try:
                r["setting_unchanged"] = get_path(obj, e["key_path"]) == e["expected"]
                if not r["setting_unchanged"]:
                    r["error"] = "seeded setting changed"
            except KeyError:
                r["error"] = "seeded setting missing"
            r["server_entries"] = find_server(e["format"], obj, name)
            if e.get("comment_line"):
                r["comment_kept"] = e["comment_line"].encode("utf-8") in data
        except FileNotFoundError:
            r["error"] = "file missing"
        except (ValueError, UnicodeDecodeError) as exc:  # json / toml decode errors
            r["error"] = "does not parse: " + str(exc).splitlines()[0][:160]
        ok = r["exists"] and r["parses"] and r["setting_unchanged"]
        r["pass"] = ok
        all_ok = all_ok and ok
        results.append(r)
        print("%s  %-15s %-55s %s%s" % (
            "PASS" if ok else "FAIL", e["id"], e["path"],
            r["error"] or "setting unchanged",
            ("; holds " + ", ".join(r["server_entries"])) if r["server_entries"] else ""))
    print("RESULT " + ("PASS" if all_ok else "FAIL")
          + " (every seeded file exists, parses, and keeps its seeded setting)")
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump({"pass": all_ok, "server_name": name, "results": results}, f,
                      indent=2, ensure_ascii=False)
            f.write("\n")
    return 0 if all_ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--home", default=os.environ.get("HOME", ""))
    s.add_argument("--project", required=True)
    s.add_argument("--fixture", default=os.path.dirname(HERE))
    s.add_argument("--locations", default=os.path.join(HERE, "locations.json"))
    s.add_argument("--state", required=True)
    s.add_argument("--force", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("--state", required=True)
    c.add_argument("--server", default=None)
    c.add_argument("--report", default=None)
    a = ap.parse_args()
    return cmd_seed(a) if a.cmd == "seed" else cmd_check(a)


if __name__ == "__main__":
    sys.exit(main())
