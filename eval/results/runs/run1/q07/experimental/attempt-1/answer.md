I checked pickfit, which keeps a catalog of tools it has actually installed and tested. None of the 18 tools it has verified fits this request. It did name Hurl as a likely fit but hasn't tested it. Everything below comes from my own knowledge, not a test run, so check the details against the official docs. As you asked, I didn't run any commands on your machine.

**My assumption:** you're moving off Postman or something like it, and your team wants a desktop app on Mac plus a CLI in CI. If your team is happy working only in the terminal, see option 2.

## Main recommendation: Bruno (MIT-licensed, offline, no account)

- **Git-friendly files:** each request is one plain-text file (`.bru`) inside a normal folder. You commit the folder to your repo, and each changed request shows up as a small, readable diff. Newer versions also offer a YAML-based format.
- **Works offline:** the desktop app has no cloud workspace and needs no sign-in.
- **CI:** the `bru` CLI runs the same files on Linux. If any assertion fails, it exits with a non-zero code, so the build fails. It can also write JUnit reports.
- **Cost:** the core app and CLI are free and open source. There's an optional paid "Golden Edition", but you don't need it for this.

### Install (Mac)
```bash
brew install --cask bruno          # desktop app
npm install -g @usebruno/cli       # CLI (needs Node 18+), command is `bru`
```

### First run
1. Open Bruno, click **Create Collection**, and pick a folder inside your repo, e.g. `api-tests/`.
2. Add a request. Bruno saves it as a file like this:
   ```
   meta { name: Get user  type: http  seq: 1 }

   get {
     url: {{baseUrl}}/users/1
   }

   assert {
     res.status: eq 200
     res.body.id: eq 1
   }

   tests {
     test("has email", function() {
       expect(res.getBody().email).to.be.a("string");
     });
   }
   ```
3. Create an environment (stored as `environments/ci.bru`) that sets `baseUrl`. Keep secrets out of git: reference them as `{{process.env.API_TOKEN}}` and put the real values in a `.env` file listed in `.gitignore`.
4. Run it locally the same way CI will:
   ```bash
   cd api-tests
   bru run --env ci
   ```
5. CI step, shown for GitHub Actions (other CI systems work the same way):
   ```yaml
   - run: npm install -g @usebruno/cli
   - run: bru run --env ci --reporter-junit results.xml
     working-directory: api-tests
     env:
       API_TOKEN: ${{ secrets.API_TOKEN }}
   ```
   The reporter flag has changed between CLI versions (older versions used `--output results.xml --format junit`). Run `bru run --help` on the version you install to confirm. Also pin the CLI version in CI so local and CI runs behave the same.

## Option 2: Hurl (Apache-2.0, CLI only)
Hurl suits you if you don't need a desktop app. Each `.hurl` file is a plain-text list of requests with assertions written underneath. It's a single fast binary written in Rust (no Node needed), and its files diff very cleanly.
```bash
brew install hurl
hurl --test --report-junit results.xml tests/*.hurl
```
Example file:
```
GET {{base_url}}/users/1
HTTP 200
[Asserts]
jsonpath "$.id" == 1
```
On Linux CI, use the `.deb` package, the release tarball or the Docker image `ghcr.io/orange-opensource/hurl`.

## Other options
- **httpYac:** runs standard `.http` / `.rest` files. It has a VS Code extension and a CLI (`httpyac send --all`) that works in CI. It's a good fit if your team already writes `.http` files.

**Bottom line:** choose Bruno if people want a Postman-style app. Choose Hurl if everyone is comfortable in the terminal and you want the simplest CI setup.