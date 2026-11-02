## Recommendation: SOPS with age keys

Use **SOPS** (Mozilla's former project, now `getsops`, Apache-2.0) with **age** as the encryption backend. Each developer has an age keypair. The repo holds one encrypted file that's encrypted to all team public keys. SOPS keeps keys readable and encrypts only the values, so git diffs are reviewable. Nothing needs a server.

I haven't verified these steps with pickfit or checked current release versions, so confirm the install method against the SOPS and age release pages.

## Install (each developer, macOS and Linux)

**macOS (Homebrew):**
```sh
brew install sops age
```

**Linux:**
- `age`: `sudo apt install age` on recent Debian/Ubuntu, or download from github.com/FiloSottile/age/releases.
- `sops`: download the binary for your architecture from github.com/getsops/sops/releases and verify its checksum. Put it on your `PATH`.

## First-run setup

1. **Each developer generates a key** (never share the private key):
   ```sh
   mkdir -p ~/.config/sops/age          # Linux default
   age-keygen -o ~/.config/sops/age/keys.txt
   ```
   On macOS, SOPS looks in `~/Library/Application Support/sops/age/keys.txt` by default. Either path works if you set `SOPS_AGE_KEY_FILE` to it. The `age-keygen` output prints a public key starting with `age1...`. Send that public key to the team lead. Public keys are safe to share in chat.

2. **Lead creates `.sops.yaml` at the repo root:**
   ```yaml
   creation_rules:
     - path_regex: secrets\.enc\.env$
       age: >-
         age1alice...,
         age1bob...,
         age1carol...,
         age1dan...
   ```

3. **Lead encrypts the existing `.env`:**
   ```sh
   sops --filename-override secrets.enc.env \
     --input-type dotenv --output-type dotenv \
     -e .env > secrets.enc.env
   ```
   `--filename-override` makes the `path_regex` match, since the input is `.env`.

4. **Update `.gitignore`** so plaintext never gets committed:
   ```
   .env
   .env.*
   !secrets.enc.env
   ```
   Then delete the plaintext `.env` from the chat history you control, and rotate any secret that was pasted in chat.

5. **Commit** `.sops.yaml` and `secrets.enc.env`. Do not commit any private key.

## Daily use

- **Edit secrets:** `sops secrets.enc.env` (opens in `$EDITOR`, re-encrypts on save).
- **Run an app without writing plaintext to disk:**
  ```sh
  sops exec-env secrets.enc.env './run-app.sh'
  ```
- **Export to a plaintext file** (only if a tool requires one, and keep it gitignored):
  ```sh
  sops --decrypt --input-type dotenv --output-type dotenv secrets.enc.env > .env
  ```

## Adding someone

Add their public key to `.sops.yaml`, then run:
```sh
sops updatekeys secrets.enc.env
```
Confirm the prompt and commit both files.

## Removing someone cleanly

This is the step people get wrong, so do all three:

1. Remove their public key from `.sops.yaml`, run `sops updatekeys secrets.enc.env`, and commit. New versions are no longer readable by them.
2. **Rotate every secret value they could have seen.** This is required. Their key still decrypts every older commit in git history, so removing the key only stops future access. Rotate the credentials at their source (API keys, database passwords, tokens), then edit the file with new values.
3. Revoke their repo, cloud, and CI access separately. SOPS doesn't control those.

Optionally run `sops rotate -i secrets.enc.env` to rotate the data key after removal. This doesn't protect old commits, so it isn't a substitute for step 2.

## Optional extras

- **CI:** create a dedicated age key for CI, add its public key to `.sops.yaml`, and store the private key as a CI secret.
- **Leak guard:** gitleaks (MIT) as a pre-commit hook to catch plaintext `.env` files.

## Alternatives I'd skip for your case

- **git-crypt:** works, but relies on GPG key management and has the same re-keying work when someone leaves. More friction for a 4-person team.
- **dotenvx:** nice developer experience, but it's built around a single decryption key per environment, which makes per-person revocation awkward.
- **Ansible Vault or any shared password:** offboarding means changing the password and telling everyone else. That's the problem you're trying to escape.

Sources (from my own knowledge, not fetched in this session):
- SOPS: github.com/getsops/sops
- age: github.com/FiloSottile/age