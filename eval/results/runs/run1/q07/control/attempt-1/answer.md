I'd go with **Bruno**. If your team is fine working only in the CLI, **Hurl** is a strong alternative.

I haven't run anything on this machine. The versions and flags below come from a quick web search, so check them against the official docs before you pin anything.

## Bruno

Bruno is a free, open-source (MIT) desktop API client, similar to Postman. It covers everything you asked for:

- **Plain-text files in git:** each request is its own small text file (`.bru`) inside a normal folder. They diff cleanly in pull requests.
- **Offline, no account:** there's no cloud workspace and no sign-in. The app just reads the folder.
- **Same files in CI:** the CLI (`@usebruno/cli`, command `bru`) runs the same folder on Linux. It exits with a non-zero code when an assertion fails, which fails the build. It can also write JUnit XML for your CI's test report.
- **Paid tier:** there's a paid "Golden Edition" with extra features, but you don't need it for this.

Assumption: Bruno's v3 release (planned for January 2026) adds YAML as a second file format. Either format works in git. Pick one for the whole team.

### Install (Mac)
```bash
brew install bruno            # desktop app
npm install -g @usebruno/cli  # CLI (needs Node.js); gives you `bru`
```

### First run
1. Open Bruno and choose **Create Collection**. Point it at a folder inside your repo, e.g. `api-tests/`.
2. Add an environment, such as `local`. It's saved as `api-tests/environments/local.bru` and holds variables like `baseUrl`. Mark tokens as **secret**: secret values stay on your machine and never go into git.
3. Create a request and add assertions. The saved file looks roughly like this:
   ```
   meta {
     name: Get user
     type: http
     seq: 1
   }

   get {
     url: {{baseUrl}}/users/1
   }

   assert {
     res.status: eq 200
     res.body.id: eq 1
   }

   tests {
     test("has email", function() {
       expect(res.body.email).to.be.a("string");
     });
   }
   ```
4. Run it from the terminal:
   ```bash
   cd api-tests
   bru run --env local
   ```
5. Commit the folder.

### CI (GitHub Actions example)
```yaml
- uses: actions/setup-node@v4
  with: { node-version: 20 }
- run: npm install -g @usebruno/cli@<pinned-version>
- run: bru run --env ci --env-var token=${{ secrets.API_TOKEN }} --reporter-junit results.xml
  working-directory: api-tests
```
If any assertion fails, `bru` exits non-zero and the job fails. Pin the CLI version so local and CI runs match. Guides disagree on the reporter flag (`--reporter-junit` vs. the older `--output … --format junit`), so run `bru run --help` for your version to check.

## Alternative: Hurl

Choose [Hurl](https://hurl.dev) if you don't need a GUI. It's open source, made by Orange, written in Rust, and the latest version I found is 8.0.x. Requests and assertions go in very small `.hurl` text files:
```
GET {{baseUrl}}/users/1
HTTP 200
[Asserts]
jsonpath "$.id" == 1
```
- **Install:** `brew install hurl` on Mac. In CI, use the Linux binary from GitHub releases or the Docker image `ghcr.io/orange-opensource/hurl`. Don't confuse it with an unrelated OCaml package also called "hurl".
- **Run:** `hurl --test --variable baseUrl=http://localhost:8080 api-tests/*.hurl --report-junit results.xml`. It's a single binary with no Node needed, and it exits non-zero when a test fails.
- **Downside:** there's no desktop app, so anyone used to Postman has to learn to work in text files.

**Rule of thumb:** pick Bruno if people want a Postman-like app. Pick Hurl if everyone is comfortable working only in the CLI and you want the smallest files and fastest CI runs.

Sources:
- [Bruno blog – 2025 recap / v3 plans](https://blog.usebruno.com/bruno-2025-from-idea-to-daily-driver)
- [Bruno CLI vs Apidog CLI](https://apidog.com/blog/bruno-cli-vs-apidog-cli/)
- [Bruno API testing guide](https://qaskills.sh/blog/bruno-api-testing-complete-guide)
- [Bruno API client overview](https://yrkan.com/blog/bruno-api-client/)
- [Hurl installation docs](https://hurl.dev/docs/installation.html)
- [Hurl 8.0.0 release](https://newreleases.io/project/github/Orange-OpenSource/hurl/release/8.0.0)
- [Arch Linux hurl 8.0.1 package](https://archlinux.org/packages/extra/x86_64/hurl/)