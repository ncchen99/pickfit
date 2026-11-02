# Use SOPS with age keys

**SOPS** (`getsops/sops`, a CNCF project under MPL-2.0) with **age** keys (`FiloSottile/age`, BSD-3) fits every requirement:

- **Encrypted secrets in git.** Each encrypted file sits next to your code. SOPS encrypts only the values in `.env`, so variable names stay readable and diffs still mean something.
- **One key per developer.** Each person generates their own age keypair. The file is encrypted to all of the team's public keys, and each person decrypts with their own private key.
- **Cutting someone off.** Remove their public key from `.sops.yaml`, run one command to re-encrypt, and commit.
- **No server or hosted service.** It's two CLI binaries and a config file. It's free and works on macOS and Linux.

Assumption: you want everything offline and local, so I'm leaving out SOPS's cloud KMS and Vault backends.

## Install

**macOS:**
```sh
brew install sops age
```

**Linux:**
```sh
# age is in most distro repos
sudo apt install age          # Debian/Ubuntu (or: dnf install age, pacman -S age)
# sops: get the binary from https://github.com/getsops/sops/releases
# (also: brew install sops on Linux, or pacman -S sops on Arch)
```
Check with `sops --version` (aim for 3.9 or later) and `age --version`.

## First run

**1. Each developer creates a keypair (once each):**
```sh
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```
This prints a public key like `age1abc...`. The public key is safe to share over chat. The private key never leaves that person's machine.

On macOS, SOPS looks for the key in `~/Library/Application Support/sops/age/keys.txt` by default. To use the same path on both OSes, add this to your shell profile:
```sh
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
```

**2. Add `.sops.yaml` to the repo root and list everyone's public key:**
```yaml
creation_rules:
  - path_regex: .*\.enc\.env$
    age: >-
      age1alice...,
      age1bob...,
      age1carol...,
      age1dave...
```

**3. Encrypt your existing `.env` (one person does this):**
```sh
sops encrypt --input-type dotenv --output-type dotenv .env > secrets.enc.env
echo ".env" >> .gitignore          # never commit plaintext
git add .sops.yaml secrets.enc.env .gitignore
git commit -m "Add SOPS-encrypted secrets"
```

**4. Daily use:**
```sh
sops edit secrets.enc.env                        # opens $EDITOR, re-encrypts on save
sops decrypt secrets.enc.env > .env              # write a local plaintext .env (gitignored)
sops exec-env secrets.enc.env 'npm run dev'      # or inject vars without writing a file
```
`exec-env` is the safest option because no plaintext ever touches the disk.

## Adding someone
1. They generate a key as in step 1 and send you their public key.
2. Add it to `.sops.yaml`.
3. Run `sops updatekeys secrets.enc.env` (once per encrypted file), then commit.

## Removing someone
```sh
# 1. Delete their age1... line from .sops.yaml, then:
sops updatekeys -y secrets.enc.env      # drop them from the recipient list
sops rotate -i secrets.enc.env          # new data key, re-encrypt everything
git commit -am "Remove <name> from secrets"
```
**Important:** this only blocks them from future versions of the file. They have already seen the plaintext, and they can still decrypt old commits with their key. To fully cut them off, **rotate the real credentials** (API keys, DB passwords, and so on) at each provider, then `sops edit` in the new values. No file-encryption tool can avoid this step. It's also a good reason to keep a short list of where each secret comes from.

## Tips
- Use one file per environment (`dev.enc.env`, `prod.enc.env`). You can give `prod` a separate `creation_rules` entry with fewer recipients if not everyone needs production access.
- Add a pre-commit check (for example, `gitleaks`) so a plaintext `.env` can't be committed by accident.
- Have each developer back up their private key in a password manager. A lost key only means re-adding that person, but it's still a hassle.

## Alternatives I considered
- **git-crypt:** decrypts files automatically on checkout, but it's built on GPG, and removing a user is awkward because there's no real revocation without re-keying by hand. The whole file is encrypted, so diffs are unreadable.
- **dotenvx:** has a nice `.env` workflow, but by default the team shares one private key, which defeats "each developer has their own key and can be cut off."
- **transcrypt / git-secret:** transcrypt uses one shared password, and git-secret depends on GPG. Both make offboarding weaker or more painful than SOPS with age.