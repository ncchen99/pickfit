I recommend **leakguard**. It's a free Rust command-line tool, MIT/Apache-2.0 licensed, that reads from stdin or files and writes the scrubbed text to stdout. It comes with detectors already built in, so you don't write any regexes. Version 1.0.0 came out on 2026-10-06.

**What it catches by default:** email addresses, IPv4 and IPv6 addresses, JWTs, AWS access keys, credentials inside URLs (`user:pass@host`), and keys or tokens from GitHub, Slack, Stripe, Google API, OpenAI, Telegram and Discord. It also catches PEM private keys, Azure storage connection strings, MAC addresses, credit cards, IBANs and US Social Security numbers. You can turn on phone numbers and a generic high-entropy secret detector too, but they're off by default because they flag more harmless text by mistake.

**Assumption:** you can install a Rust toolchain. I only found `cargo install` as the documented install method and didn't confirm whether prebuilt binaries exist. I haven't installed or run leakguard myself; everything here comes from its published docs.

### Install
```bash
# If you don't have Rust yet: use your distro's package (e.g. `sudo apt install cargo`),
# or rustup from https://rustup.rs (read the script before you run it)
cargo install leakguard        # puts the binary in ~/.cargo/bin
leakguard --list-kinds         # checks the install and lists the detector names
```

### First run
```bash
# 1. Make a test file and look at the result
printf 'user=alice@corp.com from 10.1.2.3 key=AKIAIOSFODNN7EXAMPLE\n' | leakguard

# 2. Scrub a real log before pasting it
leakguard server.log > server.clean.log
# or pipe it:
journalctl -u myapp --since "1 hour ago" | leakguard > clean.txt

# 3. Copy straight to the clipboard (X11 shown; use wl-copy on Wayland)
leakguard server.log | xclip -selection clipboard
```

### Options worth knowing
- `--stats` shows how many items of each type were redacted, so you can check that it actually caught things.
- `--check` exits with status 1 if it finds anything. You can use it as a gate before sharing a file.
- `--redact-word AcmeCorp` and `--redact-literal "db-prod-01:HOST"` hide your own sensitive terms, like internal hostnames, customer names or usernames. **No built-in detector covers those.**
- `--ignore 127.0.0.1,noreply@example.com` leaves harmless values alone.
- `--mask partial --keep 4` keeps the last 4 characters, which helps you tell redacted values apart when debugging.
- `--only email,ipv4` and `--without <kind>` limit which detectors run.

### Alternatives
- **[cleansh](https://docs.rs/crate/cleansh/latest)** (Rust, MIT/Apache-2.0): `cat app.log | cleansh sanitize`. It has an optional entropy-based engine for secrets with no known format (`--engine entropy`), copies to the clipboard with `-c`, shows a diff with `-d`, and loads custom rules from YAML. It's a good second choice. The docs call it local-only but don't say anything specific about network access or telemetry.
- **[hexredact](https://github.com/happygream/hexredact)**: does reversible redaction. The same value always gets the same placeholder, and it saves a mapping file, so you can match the AI's answer back to the real hosts and IPs.
- **[local-redact](https://github.com/sumankrsh/local-redact)** (Python): `cat app.log | local-redact redact`, with an allowlist and a JSON report.

### Limitations
These tools all match patterns. They miss secrets that don't look like any known format, such as plain passwords in config dumps, session cookies or custom tokens. Unless you add them with `--redact-word`, they also miss internal domain names, usernames and file paths. Skim the output, or the `--stats` summary, before you paste.

I also checked pickfit's catalog of tested tools, but it had nothing that does this job. These picks came from a web search instead.

Sources:
- [leakguard on docs.rs](https://docs.rs/crate/leakguard/latest) · [leakguard binary source](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs) · repo: https://github.com/ptukovar/leakguard
- [cleansh on docs.rs](https://docs.rs/crate/cleansh/latest) · [cleansh crate docs](https://docs.rs/cleansh/0.1.7/i686-unknown-linux-gnu/cleansh/)
- [hexredact](https://github.com/happygream/hexredact)
- [local-redact](https://github.com/sumankrsh/local-redact)
- [rog7/redact](https://github.com/rog7/redact)