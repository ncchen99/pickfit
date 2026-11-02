# Use Colima with the Docker CLI and Compose from Homebrew

Install **[Colima](https://github.com/abiosoft/colima)** (MIT license) and use the open-source Docker CLI, Compose and Buildx from Homebrew. Colima runs a small Linux VM that hosts the real Docker Engine, so your existing `docker ...` and `docker compose ...` commands work unchanged. On Apple silicon the VM is arm64, so arm64 images run natively. If you need amd64 images, they can run through Rosetta.

**Why this fits:**
- **License:** Docker's paid subscription covers only Docker Desktop. The Docker CLI, Docker Engine (Moby), Compose and Buildx are Apache-2.0 open source. Colima, and Lima underneath it, are free and open source. (This isn't legal advice. Check with your legal or procurement team if you need a formal answer.)
- **Compatibility:** It's the same Docker Engine and API, so Compose files, volumes, port mapping and `docker buildx` behave the way you're used to.
- **Terminal only:** There's no GUI and no background app, which suits the workflow you described.

**Assumptions:** You use Homebrew, your Mac runs macOS 13 or later (needed for Apple's Virtualization.framework, "vz"), and your current setup is Docker Desktop.

---

## Install

1. **Quit and uninstall Docker Desktop.** Use its *Troubleshoot → Uninstall*, or drag it to the Trash. This frees the `docker` command and the socket so they don't conflict. Your existing Desktop images and volumes won't carry over, so push or export anything you need first.

2. **Install the tools:**
   ```bash
   brew install colima docker docker-compose docker-buildx
   ```

3. **Make `docker compose` (with a space) work.** Homebrew installs Compose and Buildx as CLI plugins, and the Docker CLI needs to know where they are. Add this to `~/.docker/config.json`, creating the file if it doesn't exist:
   ```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   }
   ```
   If the file already has a `"credsStore": "desktop"` line left over from Docker Desktop, remove it. Otherwise `docker pull` and `docker login` may fail with a credential-helper error.

## First run

4. **Start the VM** (adjust CPU, memory in GB and disk in GB to suit your machine):
   ```bash
   colima start --vm-type vz --vz-rosetta --cpu 4 --memory 8 --disk 60
   ```
   - `--vm-type vz` uses Apple's native hypervisor, which is fast and uses little memory.
   - `--vz-rosetta` is optional. It lets `--platform linux/amd64` images run reasonably fast through Rosetta.
   - Colima creates and switches to a Docker context called `colima` automatically.

5. **Check that everything works:**
   ```bash
   docker context ls          # "colima" should be marked active (*)
   docker info --format '{{.Architecture}}'   # expect: aarch64
   docker run --rm hello-world
   docker compose version
   ```

6. **Use your projects as normal:**
   ```bash
   cd your-project && docker compose up -d
   ```

## Day to day

- Stop or start the VM with `colima stop` and `colima start`. Your settings are saved in `~/.colima/default/colima.yaml`, which you can also edit with `colima start --edit`.
- To start it automatically at login, run `brew services start colima`.
- Some tools expect `/var/run/docker.sock`, for example Testcontainers and some IDE plugins. You can point them at Colima's socket:
  ```bash
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
  ```
  Put that in `~/.zshrc`. Alternatively, run `sudo ln -sf $HOME/.colima/default/docker.sock /var/run/docker.sock`.
- **Bind mounts:** By default, Colima shares only your home directory with the VM. If you mount paths outside it, add them under `mounts:` in `colima.yaml`.
- **Changing resources:** CPU and memory can be changed with `colima stop` and then `colima start --cpu N --memory N`. Disk can only grow.

---

## Alternatives

| Option | License | Notes |
|---|---|---|
| **Rancher Desktop** | Apache-2.0 | Has a GUI. Choose the "dockerd (moby)" engine and it provides `docker` and `docker compose`. Good if teammates want a Desktop-style app. |
| **Podman + `podman machine`** | Apache-2.0 | Daemonless. It can serve a Docker-compatible socket, so the `docker` CLI and Compose work, but it's not 100% identical to Docker (networking, some Compose edge cases). |
| **Lima** (directly) | Apache-2.0 | The layer under Colima. More manual setup. |
| OrbStack | Proprietary | Excellent, but **commercial use requires a paid license**, so it doesn't meet your "free" requirement. |

For a terminal-only setup where `docker` and `docker compose` keep working without changes, Colima is the most direct replacement.