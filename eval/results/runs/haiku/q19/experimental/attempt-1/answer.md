**Main recommendation: Aider** (Apache-2.0, free, terminal-based). It's a well-known tool, not one pickfit verified. pickfit's checks found Aider's claims unverified, so the setup below is from general knowledge of its docs. Confirm the flags against the current docs before rolling it out.

Why it fits:
- It reads and edits files in your repo and works from the terminal.
- It connects to any OpenAI-compatible endpoint through `OPENAI_API_BASE`. No vendor account or key is needed beyond a dummy value.
- It doesn't need the server to support function calling. It uses text-based edit formats.
- It works without git (`--no-git`), which matters if your repo isn't under version control.

**Install (macOS)**, assuming Python 3.9 or newer:
```sh
brew install pipx
pipx ensurepath
pipx install aider-chat
```
Restart the shell, then run `aider --version` to confirm.

**Configure** (in the repo root, `.aider.conf.yml`):
```yaml
openai-api-base: http://your-model-host:8000/v1
model: openai/your-served-model-name
no-analytics: true
no-check-update: true
no-show-release-notes: true
no-git: true
```
Set a dummy key in your shell so the client doesn't complain:
```sh
export OPENAI_API_KEY=not-needed
```
Use the model name your server exposes, with the `openai/` prefix.

**First run:**
```sh
cd /path/to/your/repo
aider --message "List the top-level files and summarize what this project does" --yes-always
```
Then start interactively with `aider`, add files with `/add path/to/file`, and make a small edit to confirm it writes files. If your model struggles with diff edits, add `edit-format: whole` to the config.

**Checking the no-telemetry claim:** Aider's analytics is off by default and the flags above turn off the update check. Still, watch outbound connections during the first run (for example, Little Snitch or `nettop`). Also confirm that model-metadata lookups stay on your network.

**Alternative: Nedster** (MIT, free). It's the only option pickfit verified on macOS, but only as an install. The read-edit-test loop was never run, it needs Ollama rather than an OpenAI-compatible endpoint, it's alpha, and it needs at least 8 GB RAM. I'd only consider it if Aider doesn't work with your server.

Sources:
- [Nedster repo](https://github.com/unrealumanga/Nedster)
- [orangu repo](https://github.com/mnemosyne-systems/orangu) (not recommended: verified on Linux only, and it doesn't state OpenAI-compatible client support)
- Aider docs (not checked in this session): https://aider.chat/docs/