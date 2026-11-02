## Recommendation: Bruno

I recommend **[Bruno](https://www.usebruno.com/)**. It is MIT-licensed, has no accounts or cloud sync, and runs fully offline. You get a desktop app for your Mac and a CLI (`bru`) for Linux CI.

- **Plain-text files in your repo:** A collection is just a folder. Each request is one small text file: `.bru` files by default, and recent versions also offer a YAML format. You commit the folder like any other code, and a changed header or assertion shows up as a one-line diff in review.
- **Tests that fail the build:** Assertions and test scripts live in the same request file. `bru run` runs the collection and marks failures. It can also write JUnit XML that most CI systems can display.

I assumed you're moving off Postman or something similar, and that your Linux CI runners have Node 18 or newer.

### Install and first run on your Mac
```bash
brew install --cask bruno          # desktop app
npm install -g @usebruno/cli       # CLI (Node 18+); check with: bru --version
```
1. Open Bruno, choose **Create Collection**, and pick a folder inside your repo, for example `api-tests/`.
2. Add a request. Then add a `local` environment for things like `baseUrl`. Keep secrets out of the repo by using Bruno's secret variables or a git-ignored `.env` file.
3. A request file looks roughly like this:
   ```
   meta { name: Get user  type: http  seq: 1 }
   get { url: {{baseUrl}}/users/1 }
   assert {
     res.status: eq 200
     res.body.id: eq 1
   }
   ```
4. Run it from the terminal:
   ```bash
   cd api-tests && bru run --env local
   ```

### Linux CI (GitHub Actions example)
```yaml
- uses: actions/setup-node@v4
  with: { node-version: 20 }
- run: npm install -g @usebruno/cli
- run: cd api-tests && bru run --env ci --reporter-junit results.xml
```
`bru` exits with a non-zero code when a request or assertion fails, which fails the job. Bruno's docs don't state this exit-code behaviour, so make one assertion fail on purpose in a first CI run to confirm it. Pin the CLI version in CI so it matches the app version the team uses. Since v3, scripts run in "Safe Mode" by default; add `--sandbox=developer` only if your scripts need npm modules or filesystem access.

## Alternative: Hurl
If you don't need a GUI, **[Hurl](https://hurl.dev)** (Apache-2.0, from Orange) is also a strong fit. It's a single binary, and each `.hurl` file holds plain HTTP requests with assertions underneath, which gives very clean diffs.
```bash
brew install hurl
hurl --test --variable baseUrl=http://localhost:8080 api-tests/*.hurl
```
`hurl --test` exits non-zero when an assertion fails and supports `--report-junit`. In CI, use the release binary, the `.deb` package, or the `ghcr.io/orange-opensource/hurl` Docker image. Pick Hurl over Bruno if the team is happy writing requests by hand and wants as few dependencies as possible (no Node).

**About the sources:** I checked pickfit's catalogue of tested tools first, but it had nothing relevant to this job, so this recommendation is my own. I confirmed Bruno's CLI install command, `--env` and `--reporter-junit` flags, the Node 18+ recommendation and the v3 Safe Mode default in Bruno's docs. I didn't run anything on your machine.

Sources:
- [Bruno CLI overview](https://docs.usebruno.com/bru-cli/overview)
- [Bruno CLI quick start](https://docs.usebruno.com/bru-cli/quick-start)
- [Hurl](https://hurl.dev)