**My pick: [leakguard](https://github.com/ptukovar/leakguard).** It's a small Rust command-line tool, dual-licensed MIT/Apache-2.0, with no dependencies. It reads from stdin, writes the redacted text to stdout, and runs entirely on your machine. The patterns are already built in, so you don't write any regexes.

**What it catches by default:** emails, IPv4 and IPv6 addresses, JWTs, AWS, Google, Stripe and OpenAI keys, GitHub, Slack, Telegram and Discord tokens, passwords inside URLs, Azure connection strings, PEM private keys, plus credit cards, SSNs, MAC addresses and IBANs. It can also flag any random-looking string as a possible secret (the generic "high-entropy" detector), but that's off by default and you have to turn it on.

## Install

I'm assuming you have the Rust toolchain or are willing to install it. The tool is installed through Cargo, Rust's package manager.

```bash
# Only if you don't already have cargo (Rust's official installer):
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

cargo install leakguard
leakguard --list-kinds    # shows the exact names of the things it can detect
```

## First run

```bash
# 1. Test on a sample first and compare the output with the original
leakguard --stats < server.log > server.redacted.log
diff <(head -200 server.log) <(head -200 server.redacted.log) | less

# 2. Normal use: pipe a log through it
journalctl -u myapp --since "1 hour ago" | leakguard > for-ai.txt
tail -n 500 /var/log/nginx/error.log | leakguard

# 3. Also scrub your own internal hostnames or names it can't know about
cat app.log | leakguard --redact-word mycorp.internal --redact-word db-prod-01
```

Use `--only` and `--without` to choose which patterns run, and `--mask` to change how redacted values look. To turn on the random-string detector, find its exact name in `--list-kinds` and add it with `--only`. If you do that, list the default kinds you still want as well. I haven't checked whether `--only` replaces the default set or adds to it, so look at the output to be sure. `--check` exits with code 1 if it finds anything, which is handy in scripts.

## Caveats

- **It's young.** Version 1.0.0 came out on 2026-10-06 and looks like a one-person project. Read through the source before you trust it, and pin the version.
- **Pattern matching has gaps.** It will miss secrets in formats it doesn't know: custom session IDs, internal hostnames, usernames, and keys inside unusual config formats. Always skim the output before you paste it. `--redact-word` handles known internal strings.
- **IPs:** it redacts all of them, including harmless ones like `127.0.0.1`. If you want to keep some, `--ignore` lets you allowlist values.

## Alternatives

- **[cleansh](https://docs.rs/crate/cleansh/latest)** (Rust, MIT/Apache-2.0): `cargo install cleansh`, then `cat app.log | cleansh sanitize`. It covers similar ground, also shortens home paths to `~/`, and has an opt-in random-string detector (`--engine entropy`). It pulls in an HTTP library and has inactive paid-service stubs. If you need a guarantee that nothing leaves the machine, check the source or run it with no network access.
- **[hexredact](https://github.com/happygream/hexredact):** replaces each value with a token, and the same value always gets the same token. That lets the AI still follow, say, "IP_3" through the whole log, and you can reverse it afterwards.
- **[rog7/redact](https://github.com/rog7/redact)** and **[local-redact](https://github.com/sumankrsh/local-redact)** (Python): simpler, smaller pattern sets.
- Gitleaks and TruffleHog are better known, but they report secrets rather than filtering text through, so they don't fit stdin-to-stdout use.

I didn't install or run any of these. The details above come from their docs.rs and GitHub pages.

Sources:
- [leakguard on docs.rs](https://docs.rs/crate/leakguard/latest) / [source](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs)
- [cleansh on docs.rs](https://docs.rs/crate/cleansh/latest) / [cleansh crate docs](https://docs.rs/cleansh/0.1.7/i686-unknown-linux-gnu/cleansh/)
- [hexredact](https://github.com/happygream/hexredact)
- [rog7/redact](https://github.com/rog7/redact)
- [local-redact](https://github.com/sumankrsh/local-redact)