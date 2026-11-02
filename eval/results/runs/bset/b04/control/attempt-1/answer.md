I've finished checking the main candidate's docs, so here's the answer. I ran no commands and changed no files.

## Recommendation: review **protoprimer** before you build your own

The niche isn't empty. **[protoprimer](https://github.com/uvsmtid/protoprimer)** (MIT, by uvsmtid) is very close to what you describe:

- **Single file, no setup needed:** you commit your own copy of `proto_kernel.py` next to `pyproject.toml`. It starts under whatever `python` is on `PATH`, with no venv and no packages.
- **What it does:** it restarts itself under the required Python version, downloading that version if needed. It then creates the venv, installs pinned dependencies and hands control to your code.
- **Config:** a repo-wide config plus per-environment configs, selected with `./prime --env dst/special_env`. `./prime eval` shows the merged config. The docs have pages on log verbosity, config format, env vars, the requirements lock and pip vs. uv as installer.
- **Extension points:** custom steps run after the venv exists, either through `run_boot_env_client_func(...)` or by adding nodes to its step graph (`ContextBuilder` / `StateNode`). That fits pre-commit setup, generated code and similar jobs.
- **Hand-off:** `./prime start "module:func" -- args` and app entry scripts like `./some_app` run code from the venv without activating it. `./prime shell` opens a shell with the venv active.
- **Idempotent:** you run it after every clone or pull. `./prime reset` rebuilds the venv and re-pins versions.

**How mature it is:** small and young. When I looked it had about 128 commits, 23 stars, 10 open issues, no GitHub releases, and a PyPI package. That's good if you want to contribute and shape it. It's a risk if you need stability, so pin your kernel copy to a specific commit.

The same author also has **[instant_python_bootstrap](https://github.com/uvsmtid/instant_python_bootstrap)**, described as a trivial case of protoprimer: one `bootstrap.py` next to `pyproject.toml`. That link returned 404 when I checked, so it may have been renamed or folded into protoprimer.

### Install and first run
These steps come from the README. I'm guessing where to get the kernel file, so check it against the [tutorial](https://protoprimer.readthedocs.io/latest/intro.html).

1. **Get the kernel.** Copy the protoprimer module file from the GitHub repo at a specific commit, or from the `protoprimer` PyPI package installed in a throwaway venv. Save it in your repo root as `proto_kernel.py`.
2. **Add the entry script** `./prime`, a tiny proxy that calls `proto_kernel.py`. The repo has examples (`prime`, `cmd/boot_env_example`, `cmd/start_app_example`). Make it executable.
3. **Configure** your Python version, dependencies, layout and per-environment overrides in `pyproject.toml`. Check the Config / config_format pages for the exact keys.
4. **Commit** `proto_kernel.py`, `prime` and the config, plus the lock file once one is generated.
5. **First run:**
   ```
   git clone <repo> && cd <repo>
   ./prime            # default env: get Python, create venv, install pinned deps
   ./prime eval       # check the effective config
   ./prime --env dst/special_env   # e.g. test/prod target
   ./prime reset      # rebuild venv, re-pin
   ```
6. **Updating:** the docs say changes to the source module are copied into your kernel copy when you run `./prime`.

**Things to check while reviewing:** how it gets Python (uv or python-build-standalone), whether uv is required or optional, and the lock file format. The overview pages I read didn't say.

## Other options

| Tool | Fit | Gap compared with what you want |
|---|---|---|
| **[pyprojectx](https://pypi.org/project/pyprojectx/)** (`./pw`, like `gradlew`) | Wrapper script committed to the repo, needs only Python 3.7+, config in `[tool.pyprojectx]`, `pw.lock`, aliases | Built to install and run tools and aliases, not to bring a whole dev/test/prod environment up. Doesn't install Python versions. |
| **uv** (`uv sync`, `.python-version`, PEP 723 scripts) | Handles the Python version, venv and lock very well | It's a binary you have to install first, not a script in the repo. Has no idea of per-environment layout or bootstrap hooks. Many wrappers (protoprimer included, it seems) call it from inside. |
| **zc.buildout `bootstrap.py`** | The original "commit one script, run it after clone" | Legacy, tied to buildout. Worth reading for its design history. |
| **Pants `./pants` launcher, "Scripts to Rule Them All"** | Same pattern of committing a bootstrap to the repo | Shell scripts, not Python |
| **mise, devenv/Nix, pixi** | Declarative environment setup | Need an outside tool installed first, so they aren't stand-alone |

## Bottom line
Review protoprimer first, since it matches nearly everything on your list. If its step-graph design feels too heavy, the room left is a *minimal* single-file bootstrapper (stdlib only, maybe 300–500 lines, optional uv). pyprojectx and uv each cover part of that, and protoprimer covers it with more machinery. Even then, opening an issue or PR on protoprimer is probably a better use of your time than starting a new project.

Sources:
- [protoprimer GitHub](https://github.com/uvsmtid/protoprimer)
- [protoprimer docs intro](https://protoprimer.readthedocs.io/latest/intro.html)
- [protoprimer boot_env](https://protoprimer.readthedocs.io/latest/feature_topic/FT_85_17_35_21.boot_env.html)
- [protoprimer bootstrap process](https://protoprimer.readthedocs.io/latest/feature_topic/FT_57_87_94_94.bootstrap_process.html)
- [protoprimer kernel copy](https://protoprimer.readthedocs.io/latest/feature_topic/FT_87_17_49_36.kernel_copy.html)
- [protoprimer on PyPI](https://pypi.org/project/protoprimer/0.0.1/)
- [instant_python_bootstrap](https://github.com/uvsmtid/instant_python_bootstrap)
- [pyprojectx on PyPI](https://pypi.org/project/pyprojectx/)