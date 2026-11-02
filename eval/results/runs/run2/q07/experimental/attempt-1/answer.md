I'd go with **Bruno**. It's an MIT-licensed desktop app and CLI. Collections are plain-text files in a folder you commit, there's no account or cloud sync, and `bru run` exits non-zero when an assertion fails, which fails the CI job.

I haven't run any of this. The pickfit catalog had no tested tool for this request and only named Bruno from general knowledge, so this recommendation comes from Bruno's docs, not from a test install. Check the commands against the current docs before you rely on them.

## Why Bruno fits
- **Plain text in git:** newer collections use the OpenCollection YAML format, which Bruno's docs describe as readable, diffable files built for code review. Older collections use `.bru` text files, which still work and can be converted. Each request is its own file, so a pull request shows one small diff per changed request.
- **Offline, no sign-in:** the Mac app opens a folder from disk and doesn't need an account. Some extras are in a paid "Golden Edition," but the app, the CLI and assertions are free.
- **CI:** `@usebruno/cli` runs the same collection folder on Linux. Exit code 0 means everything passed; any failed assertion or request gives a non-zero code. There's an official GitHub Action and a Docker image. The docs also cover GitLab CI, Jenkins, Azure DevOps and Bitbucket.

## Install and first run (Mac)
1. Install the app: `brew install --cask bruno`, or download it from usebruno.com.
2. Install the CLI: `npm install -g @usebruno/cli` (needs Node.js; `brew install node` if you don't have it).
3. Make a collection: in the app, create a collection and save it inside your repo, e.g. `api/`. Add one request and open its **Assert** tab. For example, `res.status` `eq` `200`.
4. Add an environment, e.g. `local`, for base URLs. Keep secrets out of git: use a `.env` file listed in `.gitignore`, or Bruno's secret variables.
5. Run it from the terminal:
   ```sh
   cd api
   bru run --env local
   echo $?   # 0 = all assertions passed
   ```
   Change the assertion to `eq 500`, run it again, and check that the exit code is non-zero.
6. Commit the folder, and in your next pull request look at how the diff of one changed request reads.

## CI (Linux)
Generic version for any CI system:
```sh
npm install -g @usebruno/cli
cd api && bru run --env ci --reporter-junit results.xml
```
I'm going from memory on the JUnit flag, so confirm it with `bru run --help`. On GitHub Actions you can use the official `usebruno/bruno-cli-action` instead. Note that it adds `bru` for you, so its command is `run --env ci`, not `bru run --env ci`.

## Alternative if you don't need a GUI: Hurl
Hurl (Apache-2.0, by Orange) is a single binary. Its `.hurl` files hold the requests and assertions in one very readable text file, and `hurl --test *.hurl` fails the build when an assertion fails. Install with `brew install hurl` on Mac, or use the release binary or Docker image on Linux. Choose it if your team is happy working only in an editor. Choose Bruno if people want a Postman-style app for exploring APIs.

**My assumptions:** your team is moving off Postman or something similar, Node.js is available in CI or you can use Bruno's Docker image, and you need HTTP/REST rather than gRPC or WebSocket testing.

Sources:
- [Bruno CLI – GitHub Actions overview](https://docs.usebruno.com/bru-cli/github-actions/overview)
- [Bruno CLI quick start](https://docs.usebruno.com/bru-cli/quick-start)
- [Bruno getting-started tutorial](https://blog.usebruno.com/bruno-tutorial)