I'd use **Colima** with the open-source Docker CLI and Compose from Homebrew. Your `docker` and `docker compose` commands stay the same; only the engine underneath changes.

The tool I checked (pickfit) has no tested Docker Desktop replacement, so this advice comes from general knowledge, not from an install someone ran for you. Version details may have moved; check `colima version` and `brew info colima` before you depend on a specific flag.

## Why Colima
- **Free and open source (MIT).** Colima runs a small Linux VM with the real Docker Engine (Moby, Apache‑2.0) inside it. The `docker` CLI, Compose and Buildx you get from Homebrew are also Apache‑2.0, so the Docker Desktop license doesn't apply to them.
- **Works with your existing commands.** It creates a `colima` Docker context, so `docker build`, `docker run` and `docker compose up` work unchanged.
- **Runs arm64 natively.** On Apple silicon the VM is arm64, so arm64 images run natively. It can also run amd64 images through Rosetta if you need them.
- **Terminal only.** There's no GUI.

**My assumptions:** you have Homebrew installed, you're on macOS 13 or later (needed for the faster `vz` VM backend), and you're fine with removing Docker Desktop.

## Install

1. **Quit and uninstall Docker Desktop.** You can use the Troubleshoot → Uninstall option in its menu, or drag it to the Trash. This avoids conflicting `docker` binaries and makes it clear for compliance that you no longer use it.
2. **Install the tools:**
   ```sh
   brew install colima docker docker-compose docker-buildx
   ```
3. **Let the Docker CLI find the Compose and Buildx plugins.** Homebrew's install notes for these packages tell you to do this. Add the following to `~/.docker/config.json`, merging it with what's already there:
   ```json
   "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   ```
4. **Remove Docker Desktop's credential helper.** If `~/.docker/config.json` has a `"credsStore": "desktop"` line, delete it or change it to `"osxkeychain"`. If you leave it, `docker login` and pulls from private registries will fail once Docker Desktop is gone.

## First run

```sh
# Start the VM (adjust resources to suit; --vz-rosetta is only needed for amd64 images)
colima start --cpu 4 --memory 8 --disk 60 --vm-type vz --mount-type virtiofs --vz-rosetta

docker context ls                 # "colima" should be marked active
docker run --rm alpine uname -m   # should print: aarch64
docker compose version            # confirms the Compose plugin is found
docker compose up -d              # run this in one of your existing projects
```

Everyday commands:
- `colima stop` and `colima start` to stop and restart the VM.
- `colima status` to check it.
- `brew services start colima` to start it automatically at login.
- To change CPU or memory later, run `colima stop`, then `colima start` with new flags. If that doesn't apply them, `colima delete` and start again, but **that wipes your images and volumes**.

## Things to watch for
- **Tools that expect `/var/run/docker.sock`** (some IDEs, Testcontainers): Colima's socket is at `~/.colima/default/docker.sock`. Point them at it with:
  ```sh
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
  ```
  For Testcontainers, also set:
  ```sh
  export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock
  ```
- **Images and volumes don't carry over** from Docker Desktop. Pull or build them again.
- **Bind mounts:** by default only your home directory is shared with the VM. Projects stored outside `~` need a `--mount` flag.

## Other options
- **Podman (with `podman machine`)**: free (Apache‑2.0) and doesn't need a daemon. Docker compatibility is good but not perfect: Compose runs through `podman compose` or a socket helper, and you'll hit more small differences.
- **Rancher Desktop**: free (Apache‑2.0), a GUI app with a Docker (moby) engine option. A good pick if teammates want a Docker Desktop–style app.
- **Not suitable here:** OrbStack needs a paid license for commercial use. Apple's `container` tool is open source but doesn't work with `docker` or `docker compose` commands.

Before rolling this out company-wide, check it with whoever handles your software licensing. The licensing above is accurate as far as I know, but they should confirm it.