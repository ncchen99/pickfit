The niche is not empty. **[protoprimer](https://github.com/uvsmtid/protoprimer)** (MIT license, by uvsmtid) is very close to what you describe, so I'd review it and contribute to it before writing your own.

## Main recommendation: protoprimer

**How it matches your list**
- **Pure Python, runs before anything exists.** You put one file, `proto_kernel.py`, in your repo. It starts with whatever `python` is first on `PATH`, needs no packages and no venv, and is meant to [replace fragile pre-venv shell scripts](https://pypi.org/project/protoprimer/).
- **Brings the environment to a required state.** It switches to the required Python version, creates a venv for each environment, installs pinned dependencies, makes editable installs of local packages, and handles login for internal package indexes. It restarts itself between stages and checks its preconditions as a dependency graph ([docs intro](https://protoprimer.readthedocs.io/latest/intro.html)).
- **Config.** It reads repo-wide config plus per-environment config. You pick the environment with `./prime --env dst/<env>`, and `./prime eval` prints the final merged config.
- **Hands over to the venv.** After setup it calls your function inside the venv, for example `boot_env("local_repo.cmd_prime_env:custom_main")`. That's where things like git hooks, SDK setup and generated code are meant to go. You can also add your own steps to the graph.
- **Other topics the docs cover:** log verbosity, pip vs uv, lock files, monorepos, container use, intranet certificates, and the kernel updating itself from PyPI.
- **Project status:** about 23 stars, 128 commits, an empty GitHub Releases page, and PyPI versions up to around 0.12.x. It's small and run by one maintainer, so your contributions would matter.

**Install and first run** (taken from the docs; I haven't run these)
1. Copy `src/proto_code/proto_kernel.py` from the GitHub repo into your repo. The docs' example puts it at `./cmd/proto_code/proto_kernel.py`, and both the path and the name can be changed ([kernel copy](https://protoprimer.readthedocs.io/latest/feature_topic/FT_87_17_49_36.kernel_copy.html)).
2. Add an executable entry script `./prime` at the repo root. Start from the [sample `prime`](https://protoprimer.readthedocs.io/latest/_downloads/23dbbf0348ccfdca9177a12b138cad86/prime) in the docs. It loads the kernel with `importlib` and calls `proto_kernel.boot_env("<your_module>:<your_func>")`. Then run `chmod +x prime` and commit both files.
3. After a clone or pull:
   ```
   ./prime                    # bootstrap the default environment
   ./prime --env dst/prod     # bootstrap a specific environment
   ./prime eval               # print the merged config
   ./prime shell              # open a shell with the venv activated
   ./prime reset              # rebuild the venv, re-solve and re-pin dependencies
   ./prime start "pkg.mod:func" -- args
   ```
4. The config file names and format are covered in the docs' **Config** and **Tutorial** pages ("Init flat repo", "Boot env"). I couldn't load those pages, so check them for the exact layout. The repo has a `gconf` folder, which looks like where the global config lives.

## Lighter option from the same author
**[instant_python_bootstrap](https://github.com/uvsmtid/instant_python_bootstrap)** is a single `bootstrap.py` that you place next to `pyproject.toml` and run with `./bootstrap.py`. It takes no arguments, needs no packages and uses no config. It's meant for simple cases until you need protoprimer.

## Why the usual tools don't fit
- **uv, hatch, pdm, nox, tox, pipx** all have to be installed before they can run, so they work after the bootstrap, not as the bootstrap. The protoprimer docs explain this in "Why not uv?" and "Alternative".
- **cookiecutter and PyScaffold** generate a project once. They don't bring an existing clone to a required state.
- pickfit's list of tested tools also had nothing that fit. It only suggested a plain `python -m venv` plus `pip` script, which is the wheel you're trying not to reinvent.

**My assumption:** you're on macOS or Linux with some Python 3 on `PATH`. Windows support isn't clear from what I found.

**Next step:** read the docs' **Alternative** and **Background** pages and the [open issues](https://www.goodfirstissue.org/uvsmtid/protoprimer). If its approach (restarting itself, a dependency graph, a single kernel file) suits you, contributing there is a better use of your time than starting a competing project.

Sources:
- [protoprimer on GitHub](https://github.com/uvsmtid/protoprimer)
- [protoprimer docs intro](https://protoprimer.readthedocs.io/latest/intro.html)
- [protoprimer docs index](https://protoprimer.readthedocs.io/latest/)
- [Kernel copy feature topic](https://protoprimer.readthedocs.io/latest/feature_topic/FT_87_17_49_36.kernel_copy.html)
- [proto_code feature topic](https://protoprimer.readthedocs.io/latest/feature_topic/FT_90_65_67_62.proto_code.html)
- [Sample `prime` entry script](https://protoprimer.readthedocs.io/latest/_downloads/23dbbf0348ccfdca9177a12b138cad86/prime)
- [protoprimer on PyPI](https://pypi.org/project/protoprimer/)
- [instant_python_bootstrap](https://github.com/uvsmtid/instant_python_bootstrap)
- [goodfirstissue: protoprimer](https://www.goodfirstissue.org/uvsmtid/protoprimer)