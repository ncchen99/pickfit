I recommend **leakguard**. It's a small Rust command-line tool that reads stdin and writes the redacted text to stdout. It runs entirely on your machine, the regexes are built in, and it's free (MIT or Apache-2.0).

## Main recommendation: leakguard

- **Repo:** https://github.com/ptukovar/leakguard. Version 1.0.0 came out on 2026-10-06.
- **What it catches by default:** email addresses, IPv4 and IPv6 addresses, JWTs, private keys, URLs with a username and password in them, and API tokens from AWS, GitHub, Slack, Stripe, Google, OpenAI, Azure, Telegram and Discord. It also catches credit card numbers, IBANs, US Social Security numbers and MAC addresses.
- **Off by default:** phone numbers and "high-entropy" strings (random-looking values that might be secrets). You can turn them on, but they flag more things that aren't secrets.
- **Output:** each match is replaced with a label, such as `[REDACTED:EMAIL]` or `[REDACTED:IPV4]`.

### Install
I'm assuming you don't have a Rust toolchain yet and that no prebuilt Linux binary is available. If the repo's Releases page has one, you can use that instead.
```bash
# 1. Install Rust (skip if `cargo --version` already works)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# 2. Install leakguard
cargo install leakguard
leakguard --help
```

### First run
```bash
# Check it on fake data first
printf 'user bob@example.com from 203.0.113.7 token ghp_%s\n' "$(head -c 36 /dev/zero | tr '\0' 'a')" | leakguard

# Redact a log file to a new file, then read the result before pasting it
leakguard app.log > app.clean.log
less app.clean.log

# Or pipe logs straight in
journalctl -u myservice --since "1 hour ago" | leakguard > clean.log

# Keep the last 4 characters of each match, so you can still tell values apart
leakguard --mask partial --keep 4 access.log > clean.log
```
If you use X11 and want the redacted text on your clipboard, pipe it on with `... | leakguard | xclip -selection clipboard`.

## Alternatives
- **cleansh** ([KarmaYama/cleansh-workspace](https://github.com/KarmaYama/cleansh-workspace), MIT or Apache-2.0). Install with `cargo install cleansh`, then run `docker logs x | cleansh sanitize`. It covers similar ground, can also shorten home-directory paths to `~/`, and has an optional entropy mode for secrets that don't match a known pattern. One thing to check: it lists an HTTP library among its dependencies, and its docs don't say what that's for.
- **hexredact** ([happygream/hexredact](https://github.com/happygream/hexredact)). It replaces each value with a token, and the same value always gets the same token. That means you can still follow one IP or user through the logs.
- **local-redact** ([sumankrsh/local-redact](https://github.com/sumankrsh/local-redact)). It's built specifically for pasting into an LLM and can put the original values back into the answer afterwards.
- **rog7/redact** ([GitHub](https://github.com/rog7/redact)). A simpler Python script that hides emails, API keys and tokens.

## Caveats
- **Pattern matching misses things.** leakguard's own docs call it "best-effort." It won't catch internal hostnames, usernames, customer IDs or home-grown token formats. Always skim the output before you paste it.
- **For more coverage, turn on the extra checks.** The high-entropy option (or cleansh's entropy mode) catches random-looking secrets that don't match a known format.
- **These are small projects run by individuals.** I didn't review their code, so look at the repo, or build from a specific tagged release, before trusting one with production logs.

Sources:
- [leakguard on docs.rs](https://docs.rs/crate/leakguard/latest)
- [leakguard source](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs)
- [cleansh on docs.rs](https://docs.rs/crate/cleansh/latest)
- [cleansh crate docs](https://docs.rs/cleansh/0.1.7/i686-unknown-linux-gnu/cleansh/)
- [hexredact](https://github.com/happygream/hexredact)
- [local-redact](https://github.com/sumankrsh/local-redact)
- [rog7/redact](https://github.com/rog7/redact)
- [pncli PR #504](https://github.com/kolatts/pncli/pull/504)