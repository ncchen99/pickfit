I recommend **leakguard**. It's a small Rust command-line tool that reads stdin and writes redacted text to stdout. It runs entirely on your machine, needs no network, and is MIT/Apache-2.0 licensed. You don't write any regexes: it already detects emails, IPv4 and IPv6 addresses, JWTs, AWS, GitHub, Slack, Stripe, Google and OpenAI keys, Azure connection strings, PEM private keys, passwords inside URLs, and more. Version 1.0.0 came out on 2026-10-06 and it has about 74k downloads on crates.io.

I haven't installed or run it. pickfit, the tool-recommendation service I checked first, had no tested tool for this job. Everything below comes from leakguard's README and its crates.io page.

## Install (Linux)

You need a Rust toolchain (Rust 1.70 or newer). If you don't have one, install it with your distro's package manager or with rustup:

```bash
# Option A: distro package (Debian/Ubuntu example)
sudo apt install cargo

# Option B: rustup (official installer; read the script first if you prefer)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Then:
cargo install leakguard
```

The binary goes into `~/.cargo/bin`, so make sure that folder is on your `PATH`.

## First run

```bash
# See what it detects
leakguard --list-kinds

# Scrub a log and copy to clipboard for pasting (X11 / Wayland)
leakguard < server.log | xclip -selection clipboard
leakguard < server.log | wl-copy

# Check what was redacted (summary goes to stderr)
leakguard --stats server.log > clean.log

# Live tail
tail -f app.log | leakguard
```

By default each match is replaced with a label such as `[REDACTED:EMAIL]`. Some useful options:
- `--mask partial --keep 4` keeps the last 4 characters, which helps you tell values apart.
- `--ignore 10.0.0.1,test@example.com` leaves values you know are safe untouched.
- `--redact-word AcmeCorp` or `--redact-literal "..."` also removes your own hostnames, customer names and similar terms.
- `--without credit_card` helps with logs full of numbers. Some long timestamps pass the card checksum and get redacted by mistake.
- `--check` exits with code 1 if anything sensitive is found, so you can use it as a "safe to paste?" check.

## Important limitation

The command-line tool doesn't do high-entropy detection (spotting random-looking strings); only the library has that. In practice it catches tokens with known formats but can **miss custom or unprefixed secrets**, like `Authorization: Bearer <opaque>` or `api_key=abc123...` from your own services. Always look over the output before pasting, and add `--redact-literal` for any secrets you know about. The README calls the tool "best-effort" and says its detectors are conservative.

## Alternatives (not checked in detail)

- **cleansh** (Rust, `cargo install cleansh`): reads stdin and masks emails, IPs, JWT/AWS/GCP tokens, SSH keys and hex secrets. It's newer and much less used (about 2.7k downloads, last release December 2025).
- **ferret-scan** (Go): `--stdin --enable-redaction` writes redacted text to stdout and scores matches by context. It may catch more generic secrets, but it's a bigger tool.
- **redactor** (its30NA) and **redactcli** (PyPI): both are built specifically for cleaning text before pasting it into an AI chat. They're small projects whose quality I haven't checked.

Sources:
- [leakguard on GitHub](https://github.com/ptukovar/leakguard) · [docs.rs](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs) · [crates.io API](https://crates.io/api/v1/crates/leakguard)
- [cleansh](https://docs.rs/crate/cleansh/0.1.4/source/src/main.rs) · [crates.io API](https://crates.io/api/v1/crates/cleansh)
- [ferret-scan](https://github.com/orshih6/ferret-scan)
- [redactor](https://github.com/its30NA/redactor)
- [redactcli](https://pypi.org/project/redactcli/)
- [rog7/redact](https://github.com/rog7/redact)
- [redactscan PR #8](https://github.com/boktavec/redactscan/pull/8)