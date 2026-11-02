## My recommendation: SOPS with age keys

**[SOPS](https://github.com/getsops/sops)** (Mozilla Public License 2.0, a CNCF project) together with **[age](https://github.com/FiloSottile/age)** (BSD-3) covers everything you asked for:

- **Encrypted in git:** SOPS reads `.env` files natively. It encrypts each value but leaves the key names readable, so diffs and merges still make sense.
- **Each developer has their own key:** everyone makes an age keypair and shares only the public key (`age1…`). The file is encrypted to every listed public key, and the private keys never leave each person's laptop.
- **Clean revocation:** remove the person's public key, re-encrypt, commit.
- **No server, no hosted service, free and open source,** and it runs on macOS and Linux.

A note on how I checked: I asked pickfit, a tool that recommends software it has test-installed. It had no tested tool that fit and also suggested SOPS, but it hasn't installed or verified SOPS itself. The steps below come from my own knowledge of the tools. I haven't run them here, so check them against the SOPS README once.

### Install (each developer)

- **macOS:** `brew install sops age`
- **Linux:**
  - age: `sudo apt install age` (Debian 11+ / Ubuntu 22.04+) or `sudo dnf install age`
  - sops: get the binary from the [GitHub releases page](https://github.com/getsops/sops/releases), or use Homebrew on Linux (`brew install sops`)
- Check both: `sops --version` and `age --version`

### One-time setup

**1. Each developer creates a key:**
```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```
- The command prints a `Public key: age1…` line. Post that line in chat; public keys are safe to share. Never share `keys.txt`.
- I'm assuming everyone puts the key in the same place. On macOS, SOPS looks under `~/Library/Application Support/sops/age/` by default, so add `export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt` to your shell profile on both operating systems.

**2. One person adds `.sops.yaml` to the root of the repo:**
```yaml
creation_rules:
  - path_regex: \.enc\.env$
    age: >-
      age1alice...,
      age1bob...,
      age1carol...,
      age1dave...
```

**3. Create the encrypted file and keep plaintext out of git:**
```bash
echo ".env" >> .gitignore
sops secrets.enc.env          # opens $EDITOR; paste your KEY=value lines, save
git add .sops.yaml secrets.enc.env .gitignore && git commit -m "Add encrypted secrets"
```
- I'm assuming the committed file is called `secrets.enc.env`. The `.env` ending tells SOPS it's a dotenv file, and the `.enc` part matches the rule above.

**4. Optional: readable `git diff` for people who have a key:**
```bash
echo '*.enc.env diff=sopsdiffer' >> .gitattributes
git config diff.sopsdiffer.textconv "sops decrypt"
```

### Daily use

| Task | Command |
|---|---|
| Edit secrets | `sops secrets.enc.env` |
| Run the app without writing plaintext to disk | `sops exec-env secrets.enc.env 'npm run dev'` |
| Write a local `.env` (it's gitignored) | `sops decrypt secrets.enc.env > .env` |

### Adding or removing a person

- **New person:** add their `age1…` key to `.sops.yaml`, then a current member runs `sops updatekeys secrets.enc.env` and commits.
- **Someone leaves:**
  1. Delete their key from `.sops.yaml`.
  2. Run `sops updatekeys secrets.enc.env`. This re-encrypts to the remaining keys.
  3. Run `sops rotate -i secrets.enc.env`. This replaces the file's internal data key; on older versions the command is `sops -r -i`.
  4. Commit.
  5. **Change the actual secrets** (API keys, database passwords), then update them with `sops secrets.enc.env`.

  Step 5 matters. The person who left already saw the values, and old commits can still be decrypted with their key. No encrypt-in-git tool can take back what someone has already seen, so changing the real credentials is what actually cuts them off.

### Alternatives I didn't pick
- **git-crypt:** encrypts files transparently using GPG keys. GPG is painful to set up, and there's no built-in way to remove a user; you have to re-key the repo by hand. That makes it weak on your "cut someone off cleanly" requirement.
- **dotenvx:** nice to use, but it's built around one shared private key per environment rather than a key per developer.
- **transcrypt:** uses one shared password, so it can't give each person their own key.