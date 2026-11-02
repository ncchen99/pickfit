# Recommendation: SOPS + age

Use **[SOPS](https://github.com/getsops/sops)** to encrypt the files and **[age](https://github.com/FiloSottile/age)** for each developer's key. Both are free, open source (MPL-2.0 and BSD-3), run on macOS and Linux, and need no server or hosted service.

How it fits what you asked for:

- **Encrypted files in git.** You commit a file such as `secrets.enc.env`. SOPS encrypts only the values and leaves the key names readable, so `git diff` shows which variable changed without showing the secret.
- **Each developer has their own key.** Every person makes an age keypair and you list all four public keys in `.sops.yaml`. Anyone on that list can decrypt with their own private key. Nobody shares a password.
- **Cutting someone off.** Remove their public key, re-encrypt with a new data key, and change the actual secrets. Step 7 explains why you have to change the secrets too.

I wrote this from memory and haven't run anything on your machines. I'm assuming SOPS 3.9 or newer, which has the `sops encrypt`, `sops decrypt`, `sops edit` and `sops rotate` subcommands. On older versions the equivalents are `-e`, `-d`, plain `sops file` and `-r`.

---

## Install (each developer)

**macOS (Homebrew):**
```sh
brew install sops age
```

**Linux:**
```sh
# age is in most current distro repos (Debian 12+, Ubuntu 22.04+, Fedora, Arch)
sudo apt install age        # or: dnf install age / pacman -S age

# sops: download the binary from https://github.com/getsops/sops/releases
# (pick the linux.amd64 or linux.arm64 asset and check it against the published checksums file)
curl -LO https://github.com/getsops/sops/releases/download/vX.Y.Z/sops-vX.Y.Z.linux.amd64
sudo install -m 755 sops-vX.Y.Z.linux.amd64 /usr/local/bin/sops
```
Arch also has `pacman -S sops`, and Homebrew on Linux works too.

Check with `sops --version` and `age --version`.

## First run

**1. Each developer creates a key** (one time, on their own machine):
```sh
# Linux default location:
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt

# macOS default location:
mkdir -p "$HOME/Library/Application Support/sops/age"
age-keygen -o "$HOME/Library/Application Support/sops/age/keys.txt"
```
If you'd rather use the same path on both systems, set `export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt` in your shell profile.

The command prints a **public key** (`age1...`). Each person posts that public key in chat, which is safe because it's public. The private key file never leaves their machine. Back it up in your password manager.

**2. Add `.sops.yaml` to the root of the repo:**
```yaml
creation_rules:
  - path_regex: \.enc\.env$
    age: >-
      age1alice...,
      age1bob...,
      age1carol...,
      age1dave...
```

**3. Keep plaintext out of git.** Add this to `.gitignore`:
```
.env
.env.*
!*.enc.env
```

**4. Encrypt the current `.env` once and commit it:**
```sh
sops encrypt .env > secrets.enc.env      # the .env extension makes sops use dotenv format
git add .sops.yaml secrets.enc.env .gitignore
git commit -m "Add encrypted secrets"
```
After that, delete the copies of the `.env` that went around in chat, and plan to rotate those secrets because they've already been exposed.

**5. Daily use:**
```sh
sops edit secrets.enc.env                      # opens $EDITOR and re-encrypts when you save
sops decrypt secrets.enc.env > .env            # if your tooling needs a plain .env file
sops exec-env secrets.enc.env 'npm run dev'    # or skip the file and inject the vars into a process
```

**6. Adding a new teammate:** add their `age1...` key to `.sops.yaml`, then someone who already has access runs:
```sh
sops updatekeys -y secrets.enc.env
git commit -am "Grant access to <name>"
```

**7. Offboarding:**
```sh
# 1. remove their public key from .sops.yaml
sops updatekeys -y secrets.enc.env   # takes them off the recipient list
sops rotate -i secrets.enc.env       # makes a new data key
# 2. change the real secrets (API keys, DB passwords) at each provider
sops edit secrets.enc.env            # paste in the new values
git commit -am "Revoke <name>, rotate secrets"
```
**Step 2 is required.** Git history still holds the old encrypted file, and the person leaving can decrypt it with their key. Any secret they could read before should be treated as known to them. Encryption tooling can't fix that; you have to change the credentials at the source.

---

## Other tips

- **Per-environment access:** use separate files such as `dev.enc.env` and `prod.enc.env`, each with its own `creation_rules` entry, so prod can have a shorter recipient list.
- **CI:** create a separate age key for CI, add it as a recipient, and store the private key in the CI system's secret store as `SOPS_AGE_KEY`.
- **SSH keys:** age can also encrypt to existing `ssh-ed25519` public keys, but separate age keys are simpler and keep your SSH and secrets keys apart.

## Alternatives I'd skip

| Tool | Why not first choice |
|---|---|
| git-crypt | Needs GPG and encrypts whole files, so diffs are useless. Removing a user is awkward. |
| git-secret | GPG-based and clunkier to use. |
| transcrypt | Everyone shares one password, so you can't remove a single person. |
| dotenvx | Works well, but each environment has one shared private key, not one key per person. |

Sources:
- https://github.com/getsops/sops
- https://github.com/FiloSottile/age