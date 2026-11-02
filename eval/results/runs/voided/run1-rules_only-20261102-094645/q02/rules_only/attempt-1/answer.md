Yes. My main pick is **leakguard**, a small Rust command-line tool licensed MIT/Apache-2.0. It's a plain stdin→stdout filter with built-in patterns for exactly what you listed, and it runs entirely on your machine. I haven't installed or tested it. Everything below comes from its published docs.

Assumption: you're on a regular Linux distro and can install Rust's `cargo` (or already have it).

## Main pick: leakguard

**Why it fits**
- With no setup, `leakguard < in.log > out.log` covers **emails, IPv4/IPv6 addresses, JWTs, AWS keys, GitHub, Slack, Stripe, Google and OpenAI keys, PEM private keys, URLs with credentials embedded, and Discord/Telegram tokens**. It also catches credit cards, IBANs, SSNs and MAC addresses.
- It redacts **all** IPs, including private ones like 10.x and 192.168.x. Internal addresses in server logs are often the ones you want hidden.
- `--check` exits with status 1 if anything is found, so you can use it as a "safe to paste?" gate.

**Install**
```sh
# if you don't have Rust yet: your distro's package (e.g. `sudo apt install cargo`) or rustup
cargo install leakguard
# binary lands in ~/.cargo/bin — make sure that's on your PATH
```

**First run**
```sh
leakguard --list-kinds                      # see which detectors are on
echo 'user bob@corp.com from 10.0.0.7 key AKIAIOSFODNN7EXAMPLE' | leakguard
leakguard --stats server.log > clean.log    # stats go to stderr, clean text to stdout
leakguard --check clean.log && echo "nothing left"   # double-check the result
```
Useful options: `--only email,ipv4` limits it to certain types, `--ignore 127.0.0.1` keeps specific safe values, `--redact-word AcmeCorp` hides your own names, and `--mask partial --keep 4` leaves the last 4 characters visible so you can still tell values apart.

If you use X11, a handy pattern is `leakguard server.log | xclip -selection clipboard`. On Wayland, pipe to `wl-copy` instead.

**Caveat:** generic high-entropy secret detection (random strings without a known prefix, like `password=hunter2xyz` or custom tokens) is **opt-in and only available through the library, not the command-line tool**. Unusual secrets can get through. Read the output before you paste it.

## Alternatives

- **ferret-scan** (originally an AWS Labs project, Apache-2.0, Go). Install with `pip install ferret-scan` or Docker. Run it as `cat server.log | ferret-scan --stdin --enable-redaction > clean.log`. It writes redacted text to stdout and findings to stderr. It's more thorough on generic secrets (entropy analysis plus 40+ patterns) and looks more mature. The catch for your case is that by default it **skips private/reserved IPs** and only flags IPs when certain keywords appear nearby.
- **cleansh** (Rust, `cargo install cleansh`). Made for cleaning up terminal output you pipe into it, like `kubectl logs … | cleansh`. It masks emails, IPv4/IPv6 addresses and tokens.
- **local-redact** (Python). Works stdin→stdout and can put the original values back into the AI's answer afterward. That's handy if the reply refers to the placeholders.

One note on how I found these: I checked pickfit, the curated catalog of tested tools I have access to, and it had nothing that matches this job. The picks above come from a web search and the projects' own docs, not from a test install. Before relying on any of them, run a sample log with known fake secrets through it and check what gets missed.

Sources:
- [leakguard on docs.rs](https://docs.rs/crate/leakguard/latest) / [repo](https://github.com/ptukovar/leakguard)
- [ferret-scan](https://github.com/orshih6/ferret-scan) (fork of awslabs/ferret-scan)
- [cleansh](https://docs.rs/cleansh/0.1.7/i686-unknown-linux-gnu/cleansh/)
- [local-redact](https://github.com/sumankrsh/local-redact)
- [rog7/redact](https://github.com/rog7/redact)