I recommend **SOPS with age keys**. SOPS is a Mozilla-originated project, now under the CNCF, licensed MPL-2.0. age is a small modern encryption tool, licensed BSD-3.

I checked pickfit's catalogue first. It had nothing relevant: it returned security scanners, not secrets-encryption tools. So this recommendation is based on my own knowledge, and nobody has test-installed these steps for you. I also haven't run anything on your machine.

## Why SOPS + age fits your requirements

| Requirement | How SOPS + age handles it |
|---|---|
| Encrypted secrets committed to git | The encrypted files are committed like any other file. SOPS understands `.env` files natively. Only the values are encrypted, so key names still show up in diffs and code review. |
| Each developer uses their own key | Each person runs `age-keygen` once. Their public key goes in the repo's `.sops.yaml` file and their private key never leaves their laptop. |
| Remove someone cleanly | Delete their public key from `.sops.yaml`, then run `sops updatekeys` and `sops rotate`. The files are re-encrypted and their key no longer opens them. |
| No server or hosted service, free, open source | It's just two command-line programs. Nothing runs in the background. |
| macOS and Linux | Both have official binaries, and both are available in Homebrew. |

**Other options I considered:**
- **git-crypt:** you'd need to manage GPG keys, and removing someone doesn't change the repo's shared key unless you do extra work.
- **transcrypt:** everyone shares one password, so there are no per-person keys.
- **dotenvx:** usually used with one shared decryption key.

## Install

- **macOS:** `brew install sops age`
- **Linux:**
  - age: `sudo apt install age` (Debian 12 or later, Ubuntu 22.04 or later), `sudo dnf install age`, or Homebrew.
  - SOPS: run `brew install sops`, or download the binary for your system from https://github.com/getsops/sops/releases, check it against the published checksums, and put it somewhere on your `PATH`. Distro packages are often outdated, so I'd avoid them.
- Check it worked: run `sops --version` (you want 3.9 or later for the commands below) and `age --version`.

## First-run setup

**1. Each developer creates a key, once per machine:**
```sh
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
# add to ~/.zshrc or ~/.bashrc so macOS and Linux use the same location:
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
```
The command prints a `Public key: age1...` line. Each person sends that public key to the team. It's safe to share over chat. The `keys.txt` file is private: never share it, and back it up in a password manager.

**2. One person adds `.sops.yaml` at the root of the repo:**
```yaml
creation_rules:
  - path_regex: secrets/.*\.env$
    age: >-
      age1alice...,
      age1bob...,
      age1carol...,
      age1dave...
```

**3. Encrypt and commit:**
```sh
mkdir -p secrets
cp .env secrets/dev.env
sops encrypt -i secrets/dev.env      # encrypts the file in place
echo ".env" >> .gitignore            # never commit the plaintext copy
git add .sops.yaml secrets/dev.env .gitignore && git commit -m "Add encrypted secrets"
```
After this, delete the `.env` files from your chat history.

**4. Everyday use:**
```sh
sops edit secrets/dev.env                      # decrypts into $EDITOR, re-encrypts when you save
sops exec-env secrets/dev.env 'npm run dev'    # runs a command with the secrets set, no plaintext file written
sops decrypt secrets/dev.env > .env            # if your tooling needs a real .env file (it's gitignored)
```

**Optional, readable git diffs:** add `secrets/*.env diff=sopsdiffer` to `.gitattributes`, then have each developer run `git config diff.sopsdiffer.textconv "sops decrypt"`.

## When someone leaves
```sh
# 1. delete their age1... line from .sops.yaml, then:
for f in secrets/*.env; do sops updatekeys -y "$f"; sops rotate -i "$f"; done
git commit -am "Remove <name> from secrets recipients"
```
**This step is required:** re-encrypting only stops them reading *future* versions. They have already seen the plaintext, and old versions are still in git history. So you also need to **rotate the actual credentials** they had access to: API keys, database passwords, and tokens. Then update the new values with `sops edit`. No tool that keeps secrets in git can avoid this step. Make it part of your offboarding checklist.

**Adding a new person:** add their public key to `.sops.yaml` and run `sops updatekeys -y` on each file. Only someone who can already decrypt the files can do this.

**My assumptions:**
- Your secrets are plain `KEY=value` `.env` files, possibly one per environment, e.g. `secrets/dev.env` and `secrets/staging.env`.
- Everyone on the team should be able to read every environment. If production should be limited to fewer people, add a second rule in `.sops.yaml` with its own key list, e.g. `path_regex: secrets/prod\.env$`, placed above the general rule.