## My recommendation: SOPS with age keys

**[SOPS](https://github.com/getsops/sops)** (a CNCF project, MPL-2.0) with **[age](https://github.com/FiloSottile/age)** keys (BSD-3) covers everything you asked for:

- **Secrets live in git, encrypted.** SOPS understands dotenv files. It encrypts each value but leaves the key names readable, so diffs and code reviews still make sense.
- **Each developer has their own key.** Every file is encrypted to a list of age public keys, one per person (and one for CI if you want). No shared password.
- **Removing someone is a few commands.** Take their public key out of the config, re-encrypt, commit.
- **No server, no hosted service.** It's two small local programs on macOS and Linux.

**About where this comes from:** I checked pickfit, the tool catalog I have access to. It has not tested any tool that fits this job. It named SOPS too, but it hasn't installed or verified it. The steps below come from my own knowledge of SOPS 3.9+ and age, not from a tested run. Check them against the current SOPS README the first time you go through them.

---

### 1. Install (every developer)

**macOS (Homebrew):**
```sh
brew install sops age
```

**Linux:**
- Arch: `sudo pacman -S sops age`
- Debian/Ubuntu/Fedora: install `age` from your package manager (`apt install age` / `dnf install age`). For `sops`, download the binary or .deb/.rpm from https://github.com/getsops/sops/releases, because distro packages are often missing or old. Check it against the published checksums before installing.

Check both installed: `sops --version` and `age --version`

### 2. Each developer makes a key (once)

```sh
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```
This prints a public key (`age1...`). Each person posts **only the public key** in chat; that part is safe to share. The private key never leaves their machine.

On macOS, SOPS looks for keys in `~/Library/Application Support/sops/age/keys.txt` by default. To use one path on both systems, add this to your shell profile:
```sh
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
```

Have everyone back up their private key in their password manager. If someone loses it, they can't decrypt until a teammate re-adds their new key.

### 3. Set up the repo (one person, once)

Create `.sops.yaml` at the repo root:
```yaml
creation_rules:
  - path_regex: secrets/.*\.env$
    age: >-
      age1alice...,
      age1bob...,
      age1carol...,
      age1dave...
```

Then encrypt your current `.env`:
```sh
mkdir -p secrets
cp .env secrets/dev.env
sops encrypt -i secrets/dev.env      # the .env extension makes SOPS treat it as dotenv
echo ".env" >> .gitignore            # never commit the plaintext file
git add .sops.yaml secrets/dev.env .gitignore
git commit -m "Add SOPS-encrypted secrets"
```
Open `secrets/dev.env` to check: the keys should be readable and the values should look like `ENC[AES256_GCM,...]`.

### 4. Daily use

```sh
sops edit secrets/dev.env                       # opens decrypted in $EDITOR, re-encrypts on save
sops exec-env secrets/dev.env 'npm run dev'     # runs a command with the secrets as env vars, nothing written to disk
sops decrypt secrets/dev.env > .env             # if your tooling needs a real .env file (it's gitignored)
```
On SOPS older than 3.9, `sops secrets/dev.env` is the same as `edit`, and `sops -d` is the same as `decrypt`.

You can keep one file per environment (`secrets/staging.env`, `secrets/prod.env`) with different recipient lists in `.sops.yaml`. That way, for example, only two people can read prod.

### 5. Adding someone
Add their `age1...` key to `.sops.yaml`, then:
```sh
sops updatekeys -y secrets/*.env
git commit -am "Add Erin to secrets recipients"
```

### 6. Removing someone who leaves
```sh
# 1. remove their public key from .sops.yaml
sops updatekeys -y secrets/*.env     # re-encrypt to the remaining keys
sops rotate -i secrets/dev.env       # new data key (repeat for each file)
git commit -am "Remove Dave from secrets recipients"
```
**Important:** this only protects future changes. The person who left can still decrypt every old version in git history with their key, and they've already seen the plaintext values. To really cut them off, **change the actual credentials** they could see (API keys, database passwords, and so on), then put the new values in with `sops edit`. No git-based tool can avoid this step.

### 7. CI (optional)
Make a separate age key for CI. Add its public key to `.sops.yaml` and store the private key as a CI secret in `SOPS_AGE_KEY`.

---

### Other options I looked at
- **git-crypt** decrypts files automatically on checkout using GPG keys. But removing a user isn't built in (you have to re-key by hand), and you'd need GPG, which is more work to manage than age.
- **transcrypt** uses one shared password, so there are no per-person keys. That doesn't meet your requirement.
- **dotenvx** encrypts .env files nicely, but each environment has one shared private key instead of a key per developer. Removing someone means handing a new key to everyone.
- **agebox** is age-based and simpler than SOPS, but it encrypts whole files instead of individual values, and fewer people use and maintain it.

**My assumptions:** your secrets are plain `KEY=value` dotenv files, and your team uses Homebrew on macOS. If you'd rather not manage new keys, SOPS 3.10+ can reportedly also use existing `ssh-ed25519` keys as age recipients. I haven't verified that, so check the release notes before relying on it.