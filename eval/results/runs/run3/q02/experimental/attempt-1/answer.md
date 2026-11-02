I'd recommend **leakguard**. It's a small Rust command-line tool, licensed MIT/Apache-2.0, that reads from stdin and writes the redacted text to stdout. It runs entirely on your machine with built-in detectors, so you don't write any regexes.

**How I checked:** pickfit's list of tested tools had nothing for this, so I found these through a web search and read their crates.io/docs.rs pages. I haven't installed or tested either tool, and both are new projects with few users. Treat them as a first pass and still skim the output before you paste it.

## Main pick: leakguard (v1.0.0, released 2026-10-06)

**Detects by default:** emails, IPv4 and IPv6 addresses, JWTs, URLs with embedded credentials, PEM private keys, and API tokens from AWS, GitHub, Slack, Stripe, Google, OpenAI, Azure connection strings, Telegram and Discord. It also catches credit cards (Luhn-checked), IBANs, US SSNs and MAC addresses.

**Off by default (more false positives):** generic high-entropy secrets and phone numbers. Server logs often hold custom or internal tokens that match no known format, so you probably want the high-entropy detector on.

### Install
I'm assuming you don't have a Rust toolchain yet. If you do, skip to step 2.
```sh
# 1. Rust toolchain (from your distro or rustup; rustup pipes a script into sh, so read it first)
sudo apt install cargo        # Debian/Ubuntu; or: sudo dnf install cargo
# 2. Install leakguard into ~/.cargo/bin
cargo install leakguard
# make sure ~/.cargo/bin is on your PATH
```

### First run
```sh
# See which detectors exist and what they're called (including the opt-in entropy one)
leakguard --list-kinds

# Quick test
printf 'user bob@example.com from 203.0.113.7 key=ghp_abcdefghijklmnopqrstuvwxyz0123456789\n' | leakguard

# Real use: scrub a log into a clean file, then paste that
leakguard server.log > clean.log
# or straight from a pipe
journalctl -u myapp --since "1 hour ago" | leakguard > clean.log

# See what it caught (counts per type)
leakguard --stats server.log > clean.log
```
Other useful flags:
- `--check` exits with code 1 if anything sensitive is found, which works as a "safe to paste?" gate.
- `--redact-literal` / `--redact-word` add your own hostnames or customer names without writing regexes.
- `--mask partial --keep 4` keeps the last 4 characters so you can still tell values apart.

I didn't find the exact name of the entropy detector, so look it up with `--list-kinds`.

## Alternative: cleansh (v0.1.11, Dec 2025, MIT/Apache-2.0)
cleansh covers the same ground. Pick it if you'd rather not install Rust, because it has prebuilt binaries on [GitHub Releases](https://github.com/KarmaYama/cleansh-workspace). You can also run `cargo install cleansh`.
```sh
docker logs my-container | cleansh sanitize
cat server.log | cleansh sanitize --engine entropy   # also catch unknown-format secrets
```
Extras over leakguard:
- It shortens `/home/<user>` paths to `~/`.
- It can copy the output to the clipboard (`-c`) or show a diff (`-d`).
- It accepts custom YAML rules through `--config`.

Some "team" features in it are inactive stubs, but the sanitizing itself is fully open source.

## Other options I found but didn't look into
- [hexredact](https://github.com/happygream/hexredact) replaces each value with a consistent token, so the same IP always becomes the same placeholder. That keeps logs traceable, which helps when you ask an AI to debug them.
- [local-redact](https://github.com/sumankrsh/local-redact) is a Python command-line tool that reads stdin and writes stdout.
- [rog7/redact](https://github.com/rog7/redact) is a simple Python script.
- Microsoft Presidio is well known but much heavier (Python plus an NLP model). It focuses on personal data more than API keys and is overkill for piping logs.

**Caveat:** all of these are best-effort pattern matchers, and leakguard's docs say so too. Secrets without a recognizable shape can still get through, such as a plain `password=hunter2` or an internal hostname. Turn on the entropy detector, add your own hostnames and names with `--redact-literal`, and skim the result before pasting.

Sources:
- [leakguard on docs.rs](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs)
- [cleansh on docs.rs](https://docs.rs/cleansh/0.1.7/i686-unknown-linux-gnu/cleansh/)
- [hexredact](https://github.com/happygream/hexredact)
- [local-redact](https://github.com/sumankrsh/local-redact)
- [rog7/redact](https://github.com/rog7/redact)