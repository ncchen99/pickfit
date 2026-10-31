#!/usr/bin/env python3
"""Check a base_url from a q20 answer against the runner's documented default (stdlib only).

  python3 check_base_url.py "http://localhost:11434/v1"

Accepted: scheme http, host localhost or 127.0.0.1, port 11434, path /v1 with or
without a trailing slash (no query or fragment). This is the documented default
address and OpenAI-compatible path of the runner the user already has (Ollama);
confirm it against the pinned version's documentation at freeze (calibration.md)
and change EXPECTED below only through an erratum (eval/README.md section 3).
The same rule applies when the answer sets OPENAI_BASE_URL instead.
Exit 0 when accepted.
"""

import json
import sys
from urllib.parse import urlsplit

EXPECTED = {"schemes": ("http",), "hosts": ("localhost", "127.0.0.1"), "port": 11434, "paths": ("/v1", "/v1/")}


def check(url):
    res = {"base_url": url}
    try:
        u = urlsplit(url.strip())
        port = u.port
    except ValueError as e:
        res.update({"pass": False, "reason": "not a URL: %s" % e})
        return res
    host = (u.hostname or "").lower()
    problems = []
    if u.scheme not in EXPECTED["schemes"]:
        problems.append("scheme %r" % u.scheme)
    if host not in EXPECTED["hosts"]:
        problems.append("host %r" % host)
    if port != EXPECTED["port"]:
        problems.append("port %r" % port)
    if u.path not in EXPECTED["paths"]:
        problems.append("path %r" % u.path)
    if u.query or u.fragment:
        problems.append("query or fragment present")
    if u.username or u.password:
        problems.append("credentials in URL")
    res["pass"] = not problems
    if problems:
        res["reason"] = "; ".join(problems)
    return res


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    res = check(sys.argv[1])
    print(json.dumps(res))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
