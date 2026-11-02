**Recommendation: Bruno**, a free, MIT-licensed, open-source API client. It runs offline with no account, stores each request as a plain-text `.bru` file, and has a CLI (`bru`) that runs the same collection as CI tests and exits non-zero when an assertion fails.

Runner-up: **Hurl**, if you want a text-only tool with no GUI. Its `.hurl` files are plain text and it fails the build on assertion errors, but it has no Mac app for exploring requests.

I haven't run anything or checked current docs, so confirm flags against `bru run --help` for the version you install.

## Install (recommended, not run)

**On your Mac:**
```sh
brew install --cask bruno
```

**In Linux CI** (needs Node 18+):
```sh
npm install -g @usebruno/cli
```

## First-run steps

1. Open Bruno and choose **Open Collection**. Point it at a new folder in your repo, e.g. `api-tests/`. Bruno creates `bruno.json` and one `.bru` file per request.
2. Create an environment (e.g. `Local`) with `baseUrl`. Keep secrets out of git: mark them as secret in the environment, or pass them in CI as environment variables.
3. Add a request, then an **Assert** tab entry such as `res.status` `eq` `200`, or a body check like `res.body.id` `eq` `1`.
4. Commit the folder. Reviewers see plain-text diffs of URLs, headers, and assertions.
5. Test from the terminal on your Mac:
   ```sh
   cd api-tests
   bru run --env Local
   ```
6. Add a CI step on Linux:
   ```sh
   cd api-tests
   bru run --env CI --bail
   ```
   The job fails when an assertion fails. Check `bru run --help` for a JUnit reporter option if your CI needs one.

Example `.bru` request:
```
meta {
  name: Get user
  type: http
  seq: 1
}

get {
  url: {{baseUrl}}/users/1
  body: none
  auth: none
}

assert {
  res.status: eq 200
  res.body.id: eq 1
}
```

## Hurl alternative

- **Install:** `brew install hurl` on the Mac; on Linux, use the release package or binary from its GitHub releases.
- **Example `get-user.hurl`:**
  ```
  GET {{base_url}}/users/1
  HTTP 200
  [Asserts]
  jsonpath "$.id" == 1
  ```
- **Run:** `hurl --test --variable base_url=https://api.example.com api-tests/*.hurl`. Assertion failures return a non-zero exit code.

Bruno is the better fit if your team wants a GUI for writing requests. Hurl is better if you want only text files and a CLI.

Sources: none. This is from my own knowledge, not a live check.