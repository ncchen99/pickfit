I recommend **Bruno**, a desktop API client with a CLI. If your team doesn't need a GUI, **Hurl** is a text-only alternative and is described below.

My assumptions: you're moving off Postman or something like it, your team wants a GUI on their Macs, and your CI runner can install Node (or use a Node Docker image). pickfit has no tested pick for this request and named only Hurl, without checking it. So everything below comes from the tools' docs and my own knowledge, not from a sandbox test. I didn't run anything on your machine.

## Main pick: Bruno (MIT licence, free, offline)

**Why it fits:**
- **Text files in your repo:** each request is a plain-text file (`.bru`, and newer versions can also save collections as YAML) inside a normal folder. You commit them like code, and the diffs are easy to read in review.
- **No account:** there's no sign-in and no cloud sync. Collections are just folders on disk.
- **Same files in CI:** the `bru` CLI runs those files on Linux. It supports `--env` and has `--reporter-junit` for test reports. As far as I know it exits with a non-zero code when an assertion or test fails, which fails the build. Check this once with a deliberately broken test (step 4).
- **Caveat:** Bruno also sells paid editions. You don't need them for this; you can use plain `git` from the terminal.

**Install on your Mac:**
```bash
brew install --cask bruno          # desktop app
npm install -g @usebruno/cli       # optional: the CLI, to run tests locally
```

**First run:**
1. Open Bruno, choose **Create Collection**, and pick a folder inside your repo (for example `api/`).
2. Add a request. Under its **Assert** tab, add something like `res.status eq 200`, or write a `test()` block in **Tests**.
3. Add an environment (for example `ci`) with `baseUrl`. Keep secrets out of git by putting them in a `.env` file listed in `.gitignore`, or pass them with `--env-var`.
4. Run it from the terminal and check that a broken test fails:
   ```bash
   cd api && bru run --env ci ; echo "exit=$?"
   ```
   Change an assertion so it fails and confirm the exit code is no longer 0.

**CI (GitHub Actions example):**
```yaml
- uses: actions/setup-node@v4
  with: { node-version: 20 }
- run: npm install -g @usebruno/cli
- run: bru run --env ci --reporter-junit results.xml
  working-directory: api
```

## Alternative: Hurl (Apache-2.0, CLI only)

This is a better fit if your team is happy working in a text editor with no GUI. A `.hurl` file holds the requests and their assertions together in very readable text. Hurl is a single Rust binary, so CI doesn't need Node.

```bash
brew install hurl
```
`smoke.hurl`:
```
GET {{base_url}}/health
HTTP 200
[Asserts]
jsonpath "$.status" == "ok"
```
```bash
hurl --test --variable base_url=http://localhost:8080 --report-junit results.xml *.hurl
```
`--test` exits with a non-zero code when an assertion fails. On Linux CI, use the official release binary or the `ghcr.io/orange-opensource/hurl` image.

**How to choose:** pick Bruno if people want a Postman-style app to explore APIs and you also want CI tests. Pick Hurl if you want the simplest files and the lightest CI setup.

Sources:
- [Bruno CLI options](https://docs.usebruno.com/bru-cli/commandOptions)
- [Bruno](https://www.usebruno.com/)
- [Hurl](https://hurl.dev/)