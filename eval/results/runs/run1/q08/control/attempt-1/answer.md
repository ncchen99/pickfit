# Recommendation: Colima + the open-source Docker CLI

**Use [Colima](https://github.com/abiosoft/colima) (MIT license) with the Homebrew `docker`, `docker-compose`, and `docker-buildx` packages.** Colima runs a small Linux VM with the real Docker Engine (Moby) inside it, using Apple's Virtualization.framework. The Docker CLI and Compose are Apache-2.0 and free to use at any company size. Only Docker Desktop has the paid license. So your existing `docker ...` and `docker compose ...` commands, scripts and compose files keep working as they are, and arm64 images run natively.

**My assumptions:** you have Homebrew, macOS 13 or later, and you're fine re-pulling images. Images and volumes stored in Docker Desktop don't carry over.

## Install

1. **Quit and uninstall Docker Desktop first.** Its `/usr/local/bin/docker*` symlinks and credential helper can conflict with the new setup. Use Troubleshoot → Uninstall in the app, then delete `Docker.app`. Then edit `~/.docker/config.json` and remove `"credsStore": "desktop"` if it's there. If you leave it, every `docker pull` or `docker login` will fail.

2. **Install the packages:**
   ```bash
   brew install colima docker docker-compose docker-buildx
   ```

3. **Make `docker compose` (with a space) work, not just `docker-compose`.** Add this to `~/.docker/config.json`:
   ```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   }
   ```
   If the file already has other keys, add this key alongside them.

## First run

```bash
# Start the VM: native arm64, VZ virtualization, Rosetta for any amd64 images, virtiofs mounts
colima start --vm-type vz --vz-rosetta --mount-type virtiofs --cpu 4 --memory 8 --disk 100

# Colima creates and selects a "colima" docker context automatically
docker context ls

# Check that it works
docker run --rm hello-world
docker run --rm alpine uname -m        # should print aarch64
docker compose version
docker buildx version
```

Then run `docker compose up` in one of your projects as usual.

## Daily use

- **Start and stop:** `colima start` and `colima stop`. The settings you used the first time are saved, and you can change them with `colima start --edit`.
- **Start at login (optional):** `brew services start colima`
- **Check status or troubleshoot:** `colima status`, `colima ssh`, `colima delete` (this wipes the VM)
- **amd64-only images:** `docker run --platform linux/amd64 ...` runs them through Rosetta.
- **Tools that expect `/var/run/docker.sock`** (Testcontainers, some IDEs): set this in your shell profile:
  ```bash
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
  ```
  For Testcontainers, also set `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`.
- **Port forwarding:** this happens automatically, so `-p 8080:80` is reachable at `localhost:8080`.

## Alternatives (if Colima doesn't suit you)

| Option | License | Notes |
|---|---|---|
| **Rancher Desktop** | Apache-2.0 | Free, with a GUI. Choose the "dockerd (moby)" engine for full `docker` and `docker compose` compatibility. It's heavier because it bundles Kubernetes, which you can turn off. Good if your team wants a Docker Desktop-style app. |
| **Podman / Podman Desktop** | Apache-2.0 | Free and daemonless. It offers a Docker-compatible socket, but `podman compose` and Docker API compatibility have occasional rough edges, so it's less of a drop-in replacement. |
| Apple `container` | Apache-2.0 | Apple's own open-source tool. Its CLI isn't Docker-compatible and it has no Compose, so it doesn't meet your requirements. |
| OrbStack | Proprietary | Very good, but **not open source**, and commercial use requires a paid license. |

**Bottom line:** Colima keeps your current `docker` and `docker compose` workflow with the least change. Uninstall Docker Desktop, run the `brew install` line, add the plugin directory to your config, and run `colima start`.