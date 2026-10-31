#!/usr/bin/env python3
"""Check that a modified copy of script/ask.py changes only base_url, api_key and model (stdlib only).

  python3 check_script_diff.py script/ask.py /eval-work/q20/ask.py

Both files are parsed (Python AST). In each, the base_url= and api_key=
arguments of the OpenAI(...) call are removed and every model= argument value
is replaced by a placeholder; the two results must then be identical. Comments
and formatting do not matter. Prints JSON with the base_url / api_key / model
values found in the modified copy (string literals only; anything else is
reported as its source text). Exit 0 when only those three changed.
"""

import ast
import json
import sys

ALLOWED_CLIENT_ARGS = ("base_url", "api_key")


def is_openai_call(node):
    f = node.func
    return (isinstance(f, ast.Name) and f.id == "OpenAI") or (isinstance(f, ast.Attribute) and f.attr == "OpenAI")


class Normalize(ast.NodeTransformer):
    def __init__(self):
        self.found = {}

    def visit_Call(self, node):
        self.generic_visit(node)
        keep = []
        for kw in node.keywords:
            if is_openai_call(node) and kw.arg in ALLOWED_CLIENT_ARGS:
                self.found[kw.arg] = kw.value
                continue
            if kw.arg == "model":
                self.found["model"] = kw.value
                kw = ast.keyword(arg="model", value=ast.Constant(value="<model>"))
            keep.append(kw)
        node.keywords = keep
        return node


def value_of(node, src):
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    return {"expression": ast.get_source_segment(src, node)}


def normalized(src):
    tree = ast.parse(src)
    n = Normalize()
    tree = n.visit(tree)
    return ast.dump(tree, include_attributes=False), n.found


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        orig = f.read()
    with open(sys.argv[2], encoding="utf-8") as f:
        mod = f.read()
    d0, f0 = normalized(orig)
    d1, f1 = normalized(mod)
    res = {"only_allowed_changes": d0 == d1,
           "base_url": value_of(f1.get("base_url"), mod),
           "api_key_set_in_script": "api_key" in f1,
           "model": value_of(f1.get("model"), mod)}
    if isinstance(res["base_url"], dict) or isinstance(value_of(f1.get("api_key"), mod), dict):
        res["note"] = "base_url or api_key is an expression, not a literal: check by hand that it reads no new input"
    print(json.dumps(res, indent=1))
    return 0 if res["only_allowed_changes"] else 1


if __name__ == "__main__":
    sys.exit(main())
