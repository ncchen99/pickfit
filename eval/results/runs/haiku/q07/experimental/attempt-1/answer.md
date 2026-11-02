**Recommendation: Hurl.** It's free, open source (Apache-2.0), and runs entirely from the command line with no account. Each request is a plain `.hurl` text file with its assertions in the same file, so diffs in code review are easy to read. `hurl --test` returns a non-zero exit code when an assertion fails, which fails the CI job.

**Caveats**
- "Offline" means the tool needs no sign-in or network service. The APIs you test still have to be reachable, so for a fully offline run you'd point the files at a local server or mock.
- Hurl has no GUI. If teammates want a visual client, they'll need a separate app.
- My search results were mostly third-party guides. Check the exit code and flags against the official docs at [hurl.dev](https://hurl.dev) before you rely on them.

**Install (Mac)**
1. Show the command to your team before you run it. Then run `brew install hurl`.
2. Verify with `hurl --version`.

**Install (Linux CI)**
Use the official Linux packages or release tarball from the Hurl install page on hurl.dev. Pin a version so CI doesn't change under you. Avoid piping an install script into a shell.

**First run**
1. Create `tests/users.hurl` in your repo:
   ```
   GET https://api.example.com/users/1

   HTTP 200
   [Asserts]
   jsonpath "$.id" == 1
   ```
2. Run it locally: `hurl --test tests/users.hurl`. A failing assertion prints the actual response and exits non-zero.
3. In CI, run the whole folder and write a JUnit report:
   `hurl --test --report-junit report.xml tests/*.hurl`
   Hurl also supports `--variables-file` for per-environment values and `--parallel` for speed.

**Runner-up: Bruno CLI**
Bruno is a free, open-source GUI client whose collections are plain-text files in a folder you can commit. The CLI (`npm install -g @usebruno/cli`, which requires Node) runs them with `bru run`, and it supports `--env`, `--bail`, and JUnit/HTML reports. Choose it if your team wants a GUI and JavaScript assertions. Its CLI flags have changed across versions, so check the current reference first. Also, secret variables aren't exposed to the CLI, so you pass them explicitly.

I didn't run any commands or change anything on this machine.

Sources:
- [Hurl HTTP testing CLI guide 2026](https://qaskills.sh/blog/hurl-http-testing-cli-guide-2026)
- [Hurl skill page (version and exit-code notes)](https://www.typingmind.com/skills/damusix-hurl)
- [Bruno CLI overview](https://docs.usebruno.com/bru-cli/overview)
- [Bruno CLI quick start](https://docs.usebruno.com/bru-cli/quick-start)
- [Bruno CLI blog](https://blog.usebruno.com/bruno-cli)