I didn't run anything or change any files on this machine.

## Recommendation: Bruno

[Bruno](https://www.usebruno.com) fits what you asked for. It's a free, open-source (MIT) API client that needs no account or cloud sync. A collection is just a folder of plain-text files that you commit to git. Its CLI, `bru`, runs the same files in Linux CI, and the build fails when an assertion fails.

**What I assumed:** your APIs are HTTP/REST (GraphQL also works), and your CI runner can run Node.js or Docker.

### Why it fits
- **Diffs cleanly:** each request is its own small text file (`.bru`), and environments are separate files too. Bruno's 2025 roadmap said v3 adds native YAML as an option next to `.bru` ([Bruno blog](https://blog.usebruno.com/bruno-2025-from-idea-to-daily-driver)). Either format works for code review. Choose one when you create the collection.
- **Works offline:** the desktop app reads from and writes to your local folder. There's no sign-in.
- **CI:** `bru run` runs a whole collection, a folder or a single file. A failed assertion or test gives a non-zero exit code, and it can write a JUnit report your CI can display.
- **Cost:** the core app and CLI are free. There's a paid edition with extra features, but you don't need it for this.

### Install (Mac)
```bash
brew install --cask bruno        # desktop app (or download from usebruno.com)
npm install -g @usebruno/cli     # optional: CLI for running locally
```

### First run
1. Open Bruno, choose **Create Collection**, and save it to a folder inside your repo, such as `api/`.
2. Add a request. The file on disk looks roughly like this:
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
   ```
   For more complex checks, add a `tests { ... }` block with JavaScript (`expect(res.status).to.equal(200)`).
3. Create environments such as `local` and `ci`. Each one is saved as a file under `api/environments/`.
4. **Keep secrets out of git:** put them in a `.env` file in the collection folder and reference them as `{{process.env.API_TOKEN}}`. Add `.env` to `.gitignore`, and give CI the values as secret environment variables.
5. Run it locally:
   ```bash
   cd api
   bru run --env local
   ```
6. Commit the folder.

### CI example (GitHub Actions; other CI systems work the same way)
```yaml
- uses: actions/setup-node@v4
  with: { node-version: 20 }
- run: npm install -g @usebruno/cli
- run: bru run --env ci --reporter-junit results.xml
  working-directory: api
  env:
    API_TOKEN: ${{ secrets.API_TOKEN }}
```
If an assertion fails, `bru` exits non-zero and the job fails. Bruno also publishes a CLI Docker image if you'd rather not install Node. CLI flags have changed between versions, so check the [official CLI docs](https://docs.usebruno.com) against the version you pin. In CI, use `npm install -g @usebruno/cli@<version>` rather than the latest release.

## Alternatives
- **[Hurl](https://hurl.dev)** (open source, written in Rust, `brew install hurl`): has no GUI. Requests and assertions live together in very readable `.hurl` text files, and `hurl --test *.hurl` fails the build on errors. It has no Node dependency and is easy to run in CI. Choose it if your team is comfortable working only from the CLI.
- **[httpYac](https://httpyac.github.io)**: uses standard `.http` files, which VS Code and JetBrains users may already know. It has a CLI (`httpyac send --all`) that you can use in CI.

Sources:
- [Bruno 2025: from idea to daily driver (official blog)](https://blog.usebruno.com/bruno-2025-from-idea-to-daily-driver)
- [Bruno CLI vs Apidog CLI](https://apidog.com/blog/bruno-cli-vs-apidog-cli/)
- [Bruno API testing complete guide](https://qaskills.sh/blog/bruno-api-testing-complete-guide)
- [Bruno API client overview](https://yrkan.com/blog/bruno-api-client/)