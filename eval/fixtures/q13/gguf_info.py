#!/usr/bin/env python3
"""q13 calibration: read a GGUF file's header and record what the fixture is.

Prints JSON with the file size, SHA-256 (unless --no-hash), GGUF version,
tensor count and the metadata that identify the model (architecture, name,
size label, license, file type, context length, whether a chat template is
embedded). Large arrays (the tokenizer vocabulary) are skipped, only their
length is kept. Reads GGUF v2 and v3 (little-endian); it does not load any
tensor and does not need any inference library.

Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

# GGUF value types
U8, I8, U16, I16, U32, I32, F32, BOOL, STR, ARR, U64, I64, F64 = range(13)
SCALAR = {U8: "<B", I8: "<b", U16: "<H", I16: "<h", U32: "<I", I32: "<i", F32: "<f",
          BOOL: "<?", U64: "<Q", I64: "<q", F64: "<d"}
KEEP = ("general.architecture", "general.name", "general.basename", "general.size_label",
        "general.finetune", "general.license", "general.file_type", "general.quantization_version",
        "tokenizer.ggml.model")


class Reader:
    def __init__(self, fh):
        self.fh = fh

    def take(self, n: int) -> bytes:
        b = self.fh.read(n)
        if len(b) != n:
            raise ValueError("file ends inside the GGUF header")
        return b

    def unpack(self, fmt: str):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def string(self) -> str:
        n = self.unpack("<Q")
        if n > 1 << 26:
            raise ValueError("string length %d is not plausible" % n)
        return self.take(n).decode("utf-8", "replace")

    def value(self, vtype: int, keep_arrays: int = 16):
        if vtype in SCALAR:
            return self.unpack(SCALAR[vtype])
        if vtype == STR:
            return self.string()
        if vtype == ARR:
            etype = self.unpack("<I")
            count = self.unpack("<Q")
            items = []
            for i in range(count):
                v = self.value(etype, 0)
                if i < keep_arrays:
                    items.append(v)
            return {"array_of": etype, "length": count, "head": items}
        raise ValueError("unknown GGUF value type %d" % vtype)


def read_header(path: str) -> dict:
    with open(path, "rb") as fh:
        r = Reader(fh)
        magic = r.take(4)
        if magic != b"GGUF":
            raise ValueError("not a GGUF file (magic %r)" % magic)
        version = r.unpack("<I")
        if version < 2:
            raise ValueError("GGUF version %d is not supported (v2 or later)" % version)
        tensors = r.unpack("<Q")
        kv_count = r.unpack("<Q")
        meta = {}
        for _ in range(kv_count):
            key = r.string()
            vtype = r.unpack("<I")
            meta[key] = r.value(vtype)
    arch = meta.get("general.architecture")
    info = {"gguf_version": version, "tensor_count": tensors, "metadata_count": kv_count}
    for k in KEEP:
        if k in meta:
            info[k] = meta[k]
    if arch:
        for suffix in ("context_length", "block_count", "embedding_length"):
            k = "%s.%s" % (arch, suffix)
            if k in meta:
                info[k] = meta[k]
    tmpl = meta.get("tokenizer.chat_template")
    info["has_chat_template"] = isinstance(tmpl, str) and bool(tmpl)
    if isinstance(tmpl, str):
        info["chat_template_sha256"] = hashlib.sha256(tmpl.encode("utf-8")).hexdigest()
    tokens = meta.get("tokenizer.ggml.tokens")
    if isinstance(tokens, dict):
        info["vocab_size"] = tokens["length"]
    return info


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path")
    p.add_argument("--no-hash", action="store_true")
    args = p.parse_args(argv)
    out = {"file": os.path.basename(args.path), "bytes": os.stat(args.path).st_size}
    out.update(read_header(args.path))
    if not args.no_hash:
        out["sha256"] = sha256_file(args.path)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
