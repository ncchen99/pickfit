**Recommendation: try `leakguard` first, with `safelog` as the Python alternative.** Both read stdin, write stdout, and run locally. I found them through search and did not install or run either one, so check the install and flag names against each project's README before relying on them.

**Why these two:** Safelog is a streaming filter that covers API keys, tokens, emails, and IPs, and it lets you turn individual detectors off. leakguard covers the same categories, reads stdin when no files are given, and can limit redaction to chosen types. cleansh is a third option if you want entropy-based detection of unstructured secrets, but it's still in active development. scrubadub isn't a fit, since it has no CLI and no IP detector.

**Option A: leakguard (Rust)**

1. Install Rust with `rustup` if you don't have it, then run `cargo install leakguard`.
2. Check the flags with `leakguard --help`. The docs say it reads stdin when no file is given and can restrict redaction to specific types.
3. First run: `journalctl -n 200 | leakguard` (or `tail -n 200 server.log | leakguard`), then review the output and check that the types you need are covered.

**Option B: Safelog (Python)**

1. Install with `pipx install safelog` if it's published on PyPI. Otherwise, clone the GitHub repo and install it with `pipx install .` from that directory.
2. Check `safelog --help` for the detector toggles.
3. First run: `tail -n 200 server.log | safelog`, then review the output.

**Before you paste anything**

- Test on a sample file with known fake secrets first. Confirm each category you care about gets redacted, including the key formats your services actually use.
- Regex filters miss things. Skim the output before pasting, especially for custom token formats.
- Confirm the tool makes no network calls. You can check this with `strace -f -e trace=network` on Linux, or by reviewing the source.

**Environment note:** You said Linux, but the environment here reports macOS (darwin). The steps above work on either, but the `journalctl` example is Linux-only. Use `tail` or `log show` on macOS.

Sources:
- [leakguard on docs.rs](https://docs.rs/crate/leakguard/latest/source/src/bin/leakguard.rs)
- [Safelog on GitHub](https://github.com/ctkrug/safelog)
- [cleansh on docs.rs](https://docs.rs/crate/cleansh/0.1.9/source/COMMANDS.md)
- [ShareClean on GitHub](https://github.com/omarh-creator/shareclean)
- [scrubadub on PyPI](https://pypi.org/project/scrubadub/)
- [scrubbr on PyPI](https://pypi.org/project/scrubbr/)