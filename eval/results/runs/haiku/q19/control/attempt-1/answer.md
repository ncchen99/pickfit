**Recommendation: Aider.** It's Apache-2.0, runs in the terminal, edits files in your repo through diffs, and can point at any OpenAI-compatible endpoint. Its analytics are opt-in and can be turned off with a flag. Its one real drawback is that it's built around git, and your repo isn't one yet, so I'd `git init` first. That gives you a diff and undo for every change the agent makes.

**Alternative: OpenCode.** It also works with a self-hosted OpenAI-compatible server through `opencode.json`. I'd rank it second because I could not confirm its telemetry behavior from official docs. The only evidence I found is a third-party binary audit from March 2026, which may be out of date. Its documented disable flags are `OPENCODE_DISABLE_AUTOUPDATE`, `OPENCODE_DISABLE_SHARE`, and `OPENCODE_DISABLE_MODELS_FETCH`. If you pick it, check its current docs and watch its outbound traffic with a network monitor before approving it.

## Install (Aider)

Assumptions: macOS or Linux, a shell that reads `~/.zshrc` or `~/.bashrc`, an internal server at `https://llm.internal.example/v1` serving a model named `your-model`, and an API key only if your server requires one.

1. Install with pipx, which keeps it isolated: `pipx install aider-chat`. Check the aider docs for the supported Python version first.
2. In the repo, run `git init` and commit your current files, so later agent edits show up as a clean diff.
3. Create `~/.aider.conf.yml`:
   ```yaml
   model: openai/your-model
   openai-api-base: https://llm.internal.example/v1
   analytics-disable: true
   no-check-update: true
   no-show-release-notes: true
   ```
   Confirm the flag names with `aider --help`, since I checked only `analytics-disable` against the docs.
4. Add to your shell profile, so LiteLLM (the library Aider uses to talk to models) doesn't fetch its pricing map from GitHub at startup:
   ```sh
   export LITELLM_LOCAL_MODEL_COST_MAP=True
   export OPENAI_API_KEY=placeholder   # any value if your server ignores keys
   ```
5. Set the model's context window. For an unrecognized model name Aider assumes a small default, so give it the real limit using Aider's model metadata file, which is described in its docs.

## First run

1. Check the endpoint directly: `curl https://llm.internal.example/v1/models`. This should return your model list.
2. From the repo root, run `aider --no-git` only if you choose not to use git. Otherwise run `aider path/to/file1.py path/to/file2.py` to add files to the chat, then ask a small, reversible task such as "add a docstring to this function."
3. Review the diff Aider shows. Use `/undo` to revert, or `git diff` to inspect.
4. Before relying on it for sensitive code, run your OS's network monitor (or a firewall log) during a session to confirm the only outbound connection is to your server.

## Caveats

- Aider's privacy settings are verified only for analytics and update checks. Any other outbound calls depend on your versions and configuration, so the network check in step 4 is the real test.
- Small or quantized local models often struggle with Aider's edit format. If edits fail, try `--edit-format whole` or a larger model.

Sources:
- [Aider: OpenAI-compatible APIs](https://aider.chat/docs/llms/openai-compat.html)
- [Aider: Analytics](https://aider.chat/docs/more/analytics.html)
- [Opper: Aider integration](https://docs.opper.ai/integrations/coding-agents/aider)
- [OpenCode: custom provider setup (haimaker)](https://haimaker.ai/blog/opencode-custom-provider-setup/)
- [OpenCode telemetry audit (Reddit snapshot)](https://reddit.sentinel-team.org/posts/1s2q4et/snapshots/2026-03-27T22%3A19%3A49.793866Z)