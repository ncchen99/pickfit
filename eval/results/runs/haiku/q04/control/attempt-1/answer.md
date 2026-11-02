## Recommendation: SOPS + age

Use [SOPS](https://github.com/getsops/sops) to encrypt the `.env` files and [age](https://github.com/FiloSottile/age) for the keys. Both are free, open source, and run as local CLIs with no server. Each developer has their own age key pair. The committed `.sops.yaml` lists every member's **public** key as a recipient, so each person can decrypt with their own private key. Removing someone means removing their public key from that list and re-encrypting.

I'm assuming your secrets are plain `KEY=value` dotenv files and that everyone can use the terminal. I haven't run anything here, so check the current SOPS and age docs for exact flags.

## Install

**macOS**
```sh
brew install sops age
```

**Linux**
- `age`: use your package manager if it's packaged (for example `sudo apt install age`), or download a release binary from the age GitHub releases page.
- `sops`: download the binary or `.deb`/`.rpm` from the SOPS GitHub releases page.

Verify with `sops --version` and `age --version`.

## First-run setup (once, by the person who sets up the repo)

1. **Create your key:**
   ```sh
   mkdir -p ~/.config/sops/age
   age-keygen -o ~/.config/sops/age/keys.txt
   ```
   The output prints a public key starting with `age1...`. On macOS, SOPS also looks in `~/Library/Application Support/sops/age/keys.txt`. Setting `SOPS_AGE_KEY_FILE` to your key path works on both platforms.

2. **Create `.sops.yaml` at the repo root**, with one public key per teammate:
   ```yaml
   creation_rules:
     - path_regex: \.env(\..+)?$
       age: >-
         age1alice...,
         age1bob...,
         age1carol...,
         age1dan...
   ```

3. **Encrypt the existing file and remove the plaintext:**
   ```sh
   sops --encrypt --input-type dotenv --output-type dotenv --in-place .env
   ```
   Commit the encrypted file. Add plaintext `.env` files to `.gitignore` so they can't be committed by accident.

4. **Add a guard against plaintext leaks:** a pre-commit hook such as gitleaks is a good option.

## Daily use

- **Edit secrets:** `sops .env` opens the decrypted file in your editor and re-encrypts on save.
- **Run an app:** `sops exec-env .env 'npm run dev'`. This injects the variables without writing a plaintext file to disk.
- **Decrypt to a file (only if a tool requires one):** `sops decrypt .env > .env.local`, then make sure `.env.local` is in `.gitignore`.

## Onboarding a new developer

1. They run `age-keygen` and send you their **public** key. Public keys are safe to share in chat or a PR.
2. Add the key to `.sops.yaml`.
3. Run `sops updatekeys .env` for each encrypted file. This needs a current member's private key.
4. Commit and push. The new person can now decrypt.

Never share a private key (the `AGE-SECRET-KEY-...` line).

## Offboarding (the part you care most about)

1. Remove their public key from `.sops.yaml`.
2. Run `sops updatekeys` on every encrypted file.
3. Commit and push.
4. **Rotate every secret they could read.** This step matters most. They already have decrypted values, and old commits still contain ciphertext they can decrypt with their key. Removing the key stops future access, but it doesn't undo past access. Rotation is the only real cut-off.

## Other points to plan for

- **CI:** create a dedicated age key for CI, add its public key to `.sops.yaml`, and store the private key as a CI secret.
- **Key backup:** each person should keep a backup of their private key in a password manager. If someone loses their key, they need to be re-added the same way as onboarding.
- **Team size:** with 4 people, the manual `updatekeys` step takes seconds, so no extra tooling is needed.

## Alternatives I'd rule out

- **git-crypt:** it works, but it's built around GPG keyrings, and removing a member cleanly is harder.
- **dotenvx:** it's free and open source, but teams usually share one project private key, which defeats per-person revocation.
- **Hosted tools (Doppler, Infisical Cloud, 1Password, etc.):** you excluded these.

Sources: no web sources used. This is based on my knowledge of the SOPS and age projects, and I didn't verify current versions or flags.