#!/usr/bin/env python3
"""Print a throwaway API-key value, made at run time (never commit its output).

Use only when an answer says a key is required but any value works for a local
server (for example "set the API key to anything"). If the answer gives a
literal value (for example "ollama" or "dummy"), use that literal instead.
The value is random, starts with "local-", and is not valid for any service.

  python3 gen_dummy_key.py            # local-3f9c0a...
"""

import secrets

print("local-" + secrets.token_hex(16))
