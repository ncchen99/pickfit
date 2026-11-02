# Recommendation: SOPS with age keys

Use **[SOPS](https://github.com/getsops/sops)** (CNCF project, MPL-2.0) to encrypt the files and **[age](https://github.com/FiloSottile/age)** (BSD-3) for each person's key. Both are free, open source, run on macOS and Linux, and need no server.

**Why it fits:**
- **One key per person.** Each developer makes their own age keypair and shares only the public key. Each file is encrypted to everyone's public key, so anyone can decrypt it with their own private key.
- **Readable git diffs.** For `.env` files, SOPS encrypts each value but leaves the key names in plain text. Diffs show which variable changed, and merge conflicts are manageable.
- **Clear offboarding.** You remove the person's public key, re-encrypt the files, and rotate the data key. You don't need to re-share anything with the rest of the team.
- **Simple keys.** age keys are one line each. GPG keyrings aren't needed.

**Assumptions:** your secrets are `.env`-style files, and you can add a small config file to the repo. I'm answering from what I know and didn't check current release notes. The commands match SOPS 3.9 and later. Older versions use `sops -e` and `sops -d` instead of `sops encrypt` and `sops decrypt`.

---

## Install (every developer)

**macOS:**
```sh
brew install sops age
```

**Linux:**
```sh
sudo apt install age        # Debian/Ubuntu; or dnf/pacman install age
# sops: distro packages are often old, so get the release binary:
# https://github.com/getsops/sops/releases  (verify the checksum, put it in /usr/local/bin/sops)
```

Check that both work: `sops --version` and `age --version`.

## First run

### 1. Each developer creates a key (once)
```sh
# Linux default location:
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt

# macOS default location is ~/Library/Application Support/sops/age/keys.txt.
# You can use the Linux path instead and add this to your shell profile:
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
```
The command prints a public key (`age1...`). Post that line in chat; public keys are safe to share. **Never share or commit `keys.txt`**, and back it up in a password manager.

### 2. One person sets up the repo
Create `.sops.yaml` in the repo root:
```yaml
creation_rules:
  - path_regex: secrets/.*\.env$
    age: >-
      age1alice...,
      age1bob...,
      age1carol...,
      age1dave...
```

Encrypt your existing `.env` and commit it:
```sh
mkdir -p secrets
sops encrypt --input-type dotenv --output-type dotenv .env > secrets/dev.env
echo ".env" >> .gitignore          # never commit the plaintext file
git add .sops.yaml secrets/dev.env .gitignore
git commit -m "Add SOPS-encrypted secrets"
```
Then delete the copies of the `.env` that went around in chat.

### 3. Daily use
```sh
sops edit secrets/dev.env                         # opens $EDITOR, re-encrypts when you save
sops exec-env secrets/dev.env 'npm run dev'       # runs the app with the secrets, no plaintext file on disk
sops decrypt secrets/dev.env > .env               # if a tool really needs a .env file (it's gitignored)
```

## Adding someone
1. They do step 1 and send you their public key.
2. You add the key to `.sops.yaml`.
3. Run `sops updatekeys secrets/*.env` and commit.

## Removing someone
1. Delete their key from `.sops.yaml`.
2. Re-encrypt the files for the remaining keys:
   ```sh
   sops updatekeys -y secrets/*.env
   for f in secrets/*.env; do sops rotate -i "$f"; done   # new data key
   ```
3. Commit.
4. **Rotate the actual secrets** (database passwords, API tokens, and so on) and save the new values with `sops edit`.

Step 4 is the step that actually cuts them off, and no encryption tool can skip it. The former developer has already seen the plaintext values. Old commits in git history are also still encrypted to their key. Re-encrypting stops them from reading future changes, but only rotating the credentials makes the values they already know useless.

---

## Alternatives I considered
- **git-crypt**: decrypts files automatically when you check them out, which is convenient. But removing a user means re-keying the whole repo, which is awkward. It also usually depends on GPG, and the encrypted files show up in diffs as unreadable binary.
- **dotenvx**: easy to use for `.env` files, but it normally uses one shared private key per environment, not one key per person. Offboarding then means rotating that key for everyone.
- **Plain age or agebox**: works, but encrypts whole files. You'd lose the per-value diffs and the editing workflow SOPS gives you.

**Optional:** add a pre-commit check, such as [gitleaks](https://github.com/gitleaks/gitleaks), to catch anyone committing a plaintext `.env` by mistake.