Yes, and I'd use **Bruno** for this. It's free and open source under the MIT license. It has no cloud workspace and no sign-in, and it works fully offline. It saves each request as a plain-text `.bru` file in a folder you commit to git, so changes show up as normal diffs in code review. Its CLI (`bru`) runs the same files as tests in Linux CI and exits with a non-zero code when an assertion fails, which fails the build.

I'm assuming you want a desktop app for day-to-day work as well as the CLI. If you only need CLI and CI, see **Hurl** under "Alternatives."

## Install (Mac)

```bash
brew install bruno                 # desktop app (or download the .dmg from usebruno.com)
npm install -g @usebruno/cli       # the `bru` CLI, needs Node.js
```

## First run

1. Open Bruno, choose **Create Collection**, and pick a folder inside your repo, such as `api/`.
2. Add a request. Under **Assert** or **Tests**, add checks. A `.bru` file looks roughly like this:
   ```
   meta { name: Get user  type: http  seq: 1 }
   get { url: {{baseUrl}}/users/1 }
   assert {
     res.status: eq 200
     res.body.id: eq 1
   }
   ```
3. Create an environment, such as `local`, that sets `baseUrl`. Keep secrets out of git: use Bruno's secret variables, or a `.env` file that's in your `.gitignore` and read through `{{process.env.X}}`.
4. Run it locally from the collection folder:
   ```bash
   cd api
   bru run --env local
   ```
5. Commit the folder.

## CI (Linux, GitHub Actions example)

```yaml
- uses: actions/setup-node@v4
  with: { node-version: 20 }
- run: npm install -g @usebruno/cli
- run: bru run --env ci --reporter-junit results.xml
  working-directory: api
```

The step fails if any assertion fails. You can feed `results.xml` to a JUnit test reporter, and the CLI can also write JSON and HTML reports. Bruno also publishes an official GitHub Action.

Things to know:
- In CLI v3, tests run in a restricted "Safe Mode" sandbox by default. If your test scripts use Node built-ins or npm modules, add `--sandbox developer`.
- Pin the CLI version in CI so local and CI behavior stay the same.

## Alternatives
- **[Hurl](https://hurl.dev)** (open source, single Rust binary): it has no GUI, but its `.hurl` text format is very easy to read in diffs, and it was built for CI. Install with `brew install hurl` on Mac or a `.deb`/binary on Linux, then run `hurl --test *.hurl`. Pick this if your team is happy working only in text files.
- **httpyac**: runs `.http` files, the same format as the VS Code and JetBrains REST clients, from a CLI. It's a good fit if your team already uses those editor plugins.

Sources:
- [@usebruno/cli on npm](https://npmjs.com/package/@usebruno/cli)
- [Bruno docs – GitHub Actions overview](https://docs.usebruno.com/bru-cli/github-actions/overview)
- [Bruno docs – GitHub Actions manual setup](https://docs.usebruno.com/bru-cli/github-actions/manual-setup)
- [bruno-cli-action](https://awesome.ecosyste.ms/projects/github.com%2Fusebruno%2Fbruno-cli-action)
- [DEV Community – Bruno CLI vs Apidog CLI](https://dev.to/hassann/bruno-cli-vs-apidog-cli-run-api-tests-in-ci-30cn)