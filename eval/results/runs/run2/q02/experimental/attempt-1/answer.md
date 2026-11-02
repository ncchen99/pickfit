I recommend **leakguard**. It's a free, open-source command-line filter that reads logs from stdin and writes a scrubbed copy to stdout, entirely on your machine. Detection patterns are built in, so you don't write any regexes.

I haven't installed or tested it. pickfit had nothing tested that fit this job, so this recommendation is based on the tool's published documentation.

## Main pick: leakguard (Rust, MIT/Apache-2.0)

- **License and release:** dual MIT/Apache-2.0. Version 1.0.0 came out on 2026-10-06. Source: https://github.com/ptukovar/leakguard
- **How it works:** with no file arguments, it reads stdin and writes redacted text to stdout. It keeps line endings and removes a multi-line PEM private key as a single block.
- **What it detects:** emails, IPv4 and IPv6 addresses, JWTs, AWS access keys, GitHub, Slack, Stripe, Google, OpenAI, Telegram and Discord tokens, Azure connection strings, credentials inside URLs, private keys, credit cards, IBANs, phone numbers, US SSNs and MAC addresses.
- **One catch:** "generic_secret", a high-entropy scan for tokens it doesn't recognise by format, is **off by default**. If your logs contain your own app's tokens or session IDs, turn it on. Run `leakguard --help` to see exactly how.

### Install
I'm assuming you have the Rust toolchain (`cargo`). If you don't, install it from https://rustup.rs. Note that the standard rustup installer downloads a script and runs it in your shell, so read it first if you prefer.

```bash
cargo install leakguard        # puts the binary in ~/.cargo/bin/leakguard
leakguard --list-kinds         # confirm it works and see the detector names
```

### First run
```bash
# 1. Dry check: prints nothing, exits 1 if it finds anything sensitive.
#    -v lists each finding's type and position on stderr, never the value itself.
leakguard --check -v < server.log

# 2. Scrub and look at the result before pasting
leakguard server.log > server.clean.log
less server.clean.log

# 3. Common pipeline uses
journalctl -u myapp --since "1 hour ago" | leakguard > for-ai.txt
leakguard --stats server.log > clean.log         # summary of what it removed goes to stderr
leakguard --ignore 127.0.0.1,example.com app.log # leave known-safe values alone
leakguard --redact-word acme-internal app.log    # also hide your company or host names
```
Other replacement styles are available with `--mask`: `fixed` gives `[REDACTED]`, and `partial` keeps the last few characters.

## Alternatives
- **hexredact** (Python 3.9+, MIT, uses only the standard library). It has 31 detectors, including hostnames, UUIDs, usernames in sshd/sudo logs, and API keys for services like Anthropic and OpenAI. By default it replaces each value with the same token every time, so you can still follow one IP or user through the log, and you can map the AI's answer back to the real values. It's very new: 5 commits, no releases.
  ```bash
  pipx install git+https://github.com/happygream/hexredact
  cat server.log | hexredact redact - --map server.map.json > clean.log
  # add --mode mask if you want removal that can't be reversed
  ```
- **cleansh** (Rust) and **local-redact** (Python) work as stdin-to-stdout filters in the same way. They're worth trying if leakguard misses something in your log format.
- **Gitleaks** is well known, but it only *reports* secrets. It doesn't output a scrubbed copy of your text, so it doesn't fit this job.

## A caveat for any of these
These tools match patterns. They will miss secrets in formats they don't know, such as your own tokens, internal hostnames or customer IDs. Before you rely on one:
1. Run it once on a real sample log and compare the input and output, for example with `diff server.log clean.log | less`.
2. Add `--redact-word` or `--ignore` rules for your own terms.
3. Still skim the output before each paste.

Sources:
- [leakguard on docs.rs](https://docs.rs/crate/leakguard/latest)
- [leakguard CLI source](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs)
- [hexredact](https://github.com/happygream/hexredact)
- [cleansh](https://docs.rs/cleansh/0.1.7/i686-unknown-linux-gnu/cleansh/)
- [local-redact](https://github.com/sumankrsh/local-redact)
- [rog7/redact](https://github.com/rog7/redact)