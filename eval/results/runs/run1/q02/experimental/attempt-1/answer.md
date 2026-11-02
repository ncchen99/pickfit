My main recommendation is **leakguard**. It's a free, open-source Rust command-line tool that reads stdin, writes the redacted text to stdout, and does everything on your machine. It comes with built-in detectors, so you don't write any regexes.

I'm assuming a typical Debian/Ubuntu/Fedora machine and that you're fine installing Rust's `cargo`. I haven't run leakguard myself. pickfit's tested catalog had nothing for this task, so everything below comes from the project's crates.io/docs.rs page and README.

## Main pick: leakguard

- **License:** MIT or Apache-2.0. Version 1.0.0 was released 2026-10-06. It has no dependencies and makes no network calls.
- **What it catches by default:**
  - **API keys and tokens:** AWS, GitHub, Slack, Stripe, Google, OpenAI, Telegram and Discord keys, JWTs, Azure connection strings, PEM private keys, and URLs with `user:pass@` in them.
  - **Personal data:** email addresses, IPv4 and IPv6 addresses, MAC addresses, credit card numbers, IBANs and US Social Security numbers.
  - **Off unless you turn them on:** phone numbers and a general "random-looking string" detector.
- **Limits to know about:**
  - It's a small project (about 25 GitHub stars, one maintainer) and calls itself "best-effort."
  - It doesn't list a detector for plain `password=...` or `Authorization: Bearer <random string>` values. A Bearer token is only caught if it's a JWT or a known key format.
  - It can mistake 14-digit timestamps for credit card numbers. Its docs suggest `--without credit_card` for logs with lots of numbers.

### Install
1. You need Rust 1.70 or newer. Debian 12's packaged `cargo` is too old, so use rustup (it pipes a script into your shell, so read it first if you like):
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source "$HOME/.cargo/env"
   ```
   On Ubuntu 24.04 or Fedora, `sudo apt install cargo` or `sudo dnf install cargo` should be new enough.
2. Install leakguard:
   ```bash
   cargo install leakguard
   ```
   This builds it from source and puts it in `~/.cargo/bin`. There don't seem to be ready-made binaries.

### First run
```bash
leakguard --list-kinds            # see what it detects

# Test it on fake data first
printf 'user=bob@example.com ip=10.1.2.3 key=AKIAIOSFODNN7EXAMPLE\npassword=hunter2\n' | leakguard

# Real use
leakguard --without credit_card < server.log > clean.log
journalctl -u myapp --since today | leakguard | xclip -sel clip   # straight to clipboard

# Useful extras
leakguard --stats < server.log > /dev/null   # counts of what it found
leakguard --check < clean.log                # fails (non-zero exit) if anything sensitive is left
leakguard --only email,ipv4 --mask char --char '#' < server.log
```
Running the test line shows you right away whether `password=hunter2` gets through. I expect it will. If your logs have plain `key=value` secrets, add the specific values with `--redact-word` or `--redact-literal`, or check the redacted output before you paste it.

## Alternatives
- **cleansh** (Rust, MIT/Apache-2.0, `cargo install cleansh`): built for cleaning terminal output before sharing. Besides IPs, emails and tokens, it looks at what comes after `=`, `:` and quotes and uses a randomness check. That may catch the generic `password=` and `api_key=` values leakguard misses. However, its stdin usage isn't well documented and it has almost no users (1 star), so I'd only use it as a backup.
- **hexredact** ([GitHub](https://github.com/happygream/hexredact)): replaces the same value with the same placeholder every time, so you can still follow one IP or user through the logs. I haven't looked into it beyond the README summary.
- **Microsoft Presidio** (well-known; I haven't checked it and pickfit hasn't either): the most established open-source tool for finding personal data. It's a heavy Python library with spaCy language models rather than a ready-made stdin-to-stdout filter, so you'd need a small wrapper script. It's mainly for names and other personal data, not API keys.

**Bottom line:** none of these is guaranteed to catch everything. Pipe through leakguard, then give the output a quick look (or run `leakguard --check`) before pasting into an AI chat.

Sources:
- [leakguard on docs.rs](https://docs.rs/crate/leakguard/latest)
- [leakguard GitHub](https://github.com/ptukovar/leakguard)
- [cleansh on docs.rs](https://docs.rs/crate/cleansh/0.1.4/source/src/main.rs)
- [cleansh GitHub](https://github.com/KarmaYama/cleansh-workspace)
- [hexredact](https://github.com/happygream/hexredact)
- [local-redact](https://github.com/sumankrsh/local-redact)
- [rog7/redact](https://github.com/rog7/redact)