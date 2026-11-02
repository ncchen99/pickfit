My top pick is **ferret-scan** from AWS Labs ([awslabs/ferret-scan](https://github.com/awslabs/ferret-scan)). It has one gap with IP addresses, and **LogScrub** covers it. I got all of this from the project READMEs and haven't installed or tested either tool. I've assumed you have Python 3 (or Docker) available and are fine with installing something from PyPI or npm.

## Main recommendation: ferret-scan

**Why it fits:**
- It's free and open source (Apache-2.0), and it's the most established option I found: an AWS Labs project with about 100 GitHub stars. Most other tools in this space are small personal projects.
- It works as a filter: it reads stdin, sends the redacted text to stdout, and prints what it found to stderr.
- It runs offline. The README says "No data leaves your host."
- You don't write any regexes. It catches API keys and tokens using 40+ patterns (AWS, GitHub, Stripe, …) plus entropy analysis (spotting random-looking strings), and it also detects emails and IPv4/IPv6 addresses.

**The gap to know about:** It deliberately **skips private IPs** (10.x, 192.168.x and similar ranges) and only flags IPs that appear near keywords that suggest an IP. So it won't catch every IP in a server log. If that matters to you, use LogScrub below as well or instead.

### Install
```bash
# pipx keeps it isolated from system Python
pipx install ferret-scan        # or: pip install --user ferret-scan
# Alternatives:
#   docker pull public.ecr.aws/awslabs/ferret-scan:latest
#   brew tap awslabs/ferret-scan https://github.com/awslabs/ferret-scan && brew install awslabs/ferret-scan/ferret-scan
```

### First run
1. Test it on fake data first:
   ```bash
   printf 'user=alice@example.com ip=203.0.113.7 key=AKIAIOSFODNN7EXAMPLE token=ghp_abcdefghijklmnopqrstuvwxyz0123456789\n' \
     | ferret-scan --stdin --enable-redaction --redaction-strategy simple 2>/dev/null
   ```
   - `--redaction-strategy simple` replaces values with plain placeholders. The other options are `format_preserving` (the default) and `synthetic`, which swaps in fake values.
   - `2>/dev/null` hides the findings report. I couldn't confirm whether that report contains the original secrets, so keep it out of anything you paste.
2. Run it on a real log:
   ```bash
   ferret-scan --stdin --enable-redaction --redaction-strategy simple < server.log 2>/dev/null > server.clean.log
   ```
3. To skip unrelated checks (it runs all 19 by default, including credit cards and SSNs), add `--checks SECRETS,EMAIL,IP_ADDRESS`.

## Alternative or add-on: LogScrub, for full IP coverage

[LogScrub](https://github.com/Draylinp/logscrub) is MIT-licensed and runs locally on Node.js 18.3 or newer.
- It **scrubs all IPv4 and IPv6 addresses, private ones included** (add `--keep-private` if you want to leave those alone).
- It also handles emails, MAC addresses, hostnames, and many token types (AWS, GitHub, GitLab, Slack, Stripe, `sk-` keys, JWTs, `Authorization:` headers, private keys…).
- The same value always gets the same numbered placeholder. That's useful for AI debugging, because "IP_1 failed, then IP_2" still makes sense.
- The downside: it's a one-person project with about 1 star, so expect less vetting.

```bash
npm install -g @draylinp/logscrub
journalctl -u nginx | logscrub --stats > clean.log   # summary goes to stderr
logscrub --check server.log                          # exit code 1 if secrets are found
```

You can also chain the two tools: `ferret-scan --stdin --enable-redaction --redaction-strategy simple < app.log 2>/dev/null | logscrub > clean.log`

## Other options I found but didn't pick
- [wick](https://github.com/krypsis-io/wick): a Go tool that uses Gitleaks' 800+ secret rules plus email and IP detection, so its token coverage is probably the widest. Only about 1 star and no published releases.
- [leakguard](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs) (Rust) and [redactcli](https://pypi.org/project/redactcli/) / [logveil-cli](https://pypi.org/project/logveil-cli) (Python) are similar small stdin/stdout filters.
- [Anonip](https://github.com/DigitaleGesellschaft/Anonip) only masks IPs.
- Gitleaks and TruffleHog find secrets but don't output a cleaned copy of the text.

## Caveats
- All of these tools match known patterns, so they will miss things: internal hostnames, customer names, and unusual token formats. Look over the output before you paste it.
- If a real secret was ever in a log, rotate it. Redacting it now doesn't help if it was already exposed somewhere else.

Sources:
- [awslabs/ferret-scan](https://github.com/awslabs/ferret-scan) / [fork](https://github.com/orshih6/ferret-scan)
- [Draylinp/logscrub](https://github.com/Draylinp/logscrub)
- [krypsis-io/wick](https://github.com/krypsis-io/wick)
- [leakguard](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs)
- [redactcli](https://pypi.org/project/redactcli/)
- [logveil-cli](https://pypi.org/project/logveil-cli)
- [local-redact](https://github.com/sumankrsh/local-redact)
- [secret-redactor](https://github.com/nsisongltd/secret-redactor)
- [shush](https://github.com/adityaarsharma/shush)
- [Anonip](https://github.com/DigitaleGesellschaft/Anonip)