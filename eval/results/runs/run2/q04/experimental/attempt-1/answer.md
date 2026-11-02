# Recommendation: SOPS with age keys

Use **[SOPS](https://github.com/getsops/sops)** (CNCF project, MPL-2.0) with **[age](https://github.com/FiloSottile/age)** keys (BSD-3). Both are single static binaries for macOS and Linux. You don't need a server or account.

It covers each of your requirements:
- **Encrypted secrets in git:** SOPS reads `.env` (dotenv) files directly. It encrypts each value and leaves the key names readable, so `git diff` still shows *which* variable changed.
- **One key per developer:** each person makes their own age keypair. The repo holds a list of everyone's public keys, and anyone on the list can decrypt with their own private key.
- **Removing someone:** delete their public key from the list, then run `sops updatekeys` and `sops rotate`. This step is covered in full below because it has a catch.
- **Free and open source,** and it runs fully offline.

I couldn't verify this with pickfit, the tool-recommendation service I checked. It found no tested match for this need, so this recommendation is from my own knowledge. pickfit's untested suggestion was git-crypt, which I compare at the end.

## Install (each developer)

```bash
# macOS
brew install sops age

# Linux: age is in most distro repos (Debian 12+, Ubuntu 22.04+, Fedora, Arch)
sudo apt install age            # or dnf/pacman
# sops: download the binary for your arch from https://github.com/getsops/sops/releases
# (also available via Homebrew on Linux, or as `sops` in Arch/Nix)
```

Check that both installed: `sops --version && age --version`

## First-time setup

**1. Each developer creates a key** (one time only):
```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```
The command prints a public key that looks like `age1...`. Each person sends that line to the team. Public keys are safe to share over chat.

Assumption to check: SOPS looks for the key file in a different place by default on macOS (`~/Library/Application Support/sops/age/keys.txt`). To keep everyone the same, macOS users can add this to their shell profile:
```bash
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
```

**2. One person adds a `.sops.yaml` file at the repo root and commits it:**
```yaml
creation_rules:
  - path_regex: \.enc\.env$
    age: >-
      age1alice...,
      age1bob...,
      age1carol...,
      age1dave...
```

**3. Encrypt the existing `.env` and commit it:**
```bash
cp .env secrets.enc.env
sops encrypt --in-place secrets.enc.env
echo ".env" >> .gitignore
git add .sops.yaml secrets.enc.env .gitignore
git commit -m "Add encrypted secrets"
```
Name the file `*.env` so SOPS recognises the dotenv format. Before committing, open `secrets.enc.env` and check that every value shows as `ENC[AES256_GCM,...]`.

## Daily use

```bash
sops edit secrets.enc.env                    # opens $EDITOR on the decrypted file; re-encrypts on save
sops exec-env secrets.enc.env 'npm run dev'  # runs a command with the secrets as env vars, no plaintext file
sops decrypt secrets.enc.env > .env          # if your tooling needs a real .env (it's gitignored)
```

## Adding or removing a developer

- **Adding someone:** put their public key in `.sops.yaml`, run `sops updatekeys -y secrets.enc.env`, then commit.
- **Removing someone:**
  1. Delete their key from `.sops.yaml`.
  2. Run `sops updatekeys -y secrets.enc.env`.
  3. Run `sops rotate --in-place secrets.enc.env`. This generates a new data key.
  4. Commit.
  5. **Change the actual credentials** (database passwords, API keys) at each provider, then `sops edit` the file with the new values.

**Step 5 is essential, whichever tool you use.** The person who left has already seen the plaintext, and old commits can still be decrypted with their key. Re-encrypting only stops them from reading *future* changes. Once a secret is changed at the provider, the old copies in git history are useless.

## Alternatives I'd rank lower

- **git-crypt:** this is what pickfit suggested, but pickfit hasn't tested it. Its per-user keys depend on GPG, which is awkward to set up. It has no command to remove a user, so you'd have to rekey by hand. It also encrypts whole files, so diffs show nothing useful. It's fine if your team already uses GPG.
- **dotenvx:** a good tool, but the usual setup uses one shared private key per environment rather than one key per developer. That doesn't match your requirement to cut off one person cleanly.

If you want extra safety later, add a pre-commit hook such as gitleaks so nobody commits a plaintext `.env` by accident.