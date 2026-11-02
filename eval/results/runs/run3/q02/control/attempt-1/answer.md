I recommend **wick** ([krypsis-io/wick](https://github.com/krypsis-io/wick)). It's a single Go binary that works as a stdin-to-stdout filter and runs entirely on your machine. It does what you asked without you writing any regexes:

- **API keys and tokens:** it ships with the rule set from Gitleaks, a widely used secret scanner. That covers cloud keys, API tokens, JWTs, private keys and webhook URLs. It also catches values of keys like `password` and `*_TOKEN`, `Authorization` and cookie headers, and passwords inside connection strings.
- **Personal data:** email addresses, IPv4 and IPv6 addresses, US phone numbers and US Social Security numbers.
- **Output:** redacted text goes to stdout and messages go to stderr, so `wick in.log > out.log` gives you a clean file.

**Something to weigh first:** the project is very new. When I checked, it had 1 star and no visible users, though it has about 69 commits and CI. One search result said its license was AGPL-3.0, but the repo page says Apache-2.0. Either way it's free and open source, but check the LICENSE file if that matters to you. Because it's a security tool, pin a specific release instead of `@latest`, and look over its output before trusting it.

## Install (Linux)

Pick one:

```bash
# Option A: prebuilt binary. Download the Linux build for your CPU from
# https://github.com/krypsis-io/wick/releases, check it against the
# published checksum if there is one, then:
tar xzf wick_*_linux_amd64.tar.gz      # exact file name may differ
sudo install wick /usr/local/bin/

# Option B: build from source (needs a recent Go toolchain)
go install github.com/krypsis-io/wick/cmd/wick@latest   # or @vX.Y.Z to pin
# the binary ends up in ~/go/bin, so make sure that's on your PATH
```

## First run

```bash
# 1. Quick test with fake data
printf 'user=alice@example.com ip=10.1.2.3 Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.e30.abc\n' | wick
# Expected: the email, IP and token each become [REDACTED]

# 2. Real use
wick /var/log/myapp/app.log > app-safe.log
journalctl -u myapp --since today | wick > safe.txt

# 3. See what was caught (counts go to stderr, not into the file)
wick --summary app.log > app-safe.log
```

**Tip for AI chats:** try `--tokenize`. Instead of turning every value into the same `[REDACTED]`, it gives each distinct value a numbered placeholder like `[IPV4-1]` or `[EMAIL-2]`. The AI can then still tell which lines involve the same host or user. You can paste its reply into `wick --rehydrate` to put the real values back. The originals are kept in an encrypted map on your machine, and `wick --forget` deletes it.

**Cautions:**
- `--report` prints each finding, including the original value, to stderr. Never paste that output.
- It only catches what has a rule. Internal hostnames, customer IDs and similar things will get through unless you add patterns to `.wick.yaml`. Always skim the result before pasting.

## Alternatives, if wick's newness bothers you

From their READMEs; I haven't tested them:
- **[ferret-scan](https://github.com/orshih6/ferret-scan)** (Go): an offline CLI that detects secrets, emails and IPs and redacts them while keeping the original format. It reads stdin when you give it a redact flag. This is the closest match to wick.
- **[leakguard](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs)** (Rust, `cargo install leakguard`): a stdin/file-to-stdout filter that lets you choose types such as email and IPv4. Its `--check` flag returns exit code 1 when something is found, which is handy in scripts.
- **[secret-redactor](https://github.com/nsisongltd/secret-redactor)** and **[redactcli](https://pypi.org/project/redactcli/)**: both are pipe-friendly, but they focus on secrets and don't list IP addresses.

All of these are small projects. Running two of them in a row (for example `wick < app.log | leakguard`) and reading the result is a cheap extra check.

Sources:
- [krypsis-io/wick](https://github.com/krypsis-io/wick)
- [orshih6/ferret-scan](https://github.com/orshih6/ferret-scan)
- [leakguard (docs.rs)](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs)
- [nsisongltd/secret-redactor](https://github.com/nsisongltd/secret-redactor)
- [redactcli (PyPI)](https://pypi.org/project/redactcli/)
- [sumankrsh/local-redact](https://github.com/sumankrsh/local-redact)