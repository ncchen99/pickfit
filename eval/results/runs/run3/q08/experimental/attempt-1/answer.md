# Recommendation: Colima with the open-source Docker CLI and Compose

Use **[Colima](https://github.com/abiosoft/colima)**. It's MIT-licensed and runs from the terminal. It starts a small Linux VM on your Mac (using Apple's Virtualization.framework through Lima) with the real Docker engine inside. On Apple silicon it runs arm64 images natively. Your existing `docker` and `docker compose` commands work unchanged because Colima sets up a Docker context that points at its VM.

**About the license:** the paid requirement covers the **Docker Desktop** app only. The `docker` CLI, the Docker engine and Docker Compose are open source (Apache 2.0) and free for any company size. You keep the same tools and swap only what runs them.

**How I checked this:** I asked the pickfit tool for verified alternatives and it had none in its tested catalog. It also named Colima, but marked it as not installed or tested by pickfit. The steps below come from my own knowledge of Colima, not from a guide someone tested. As you asked, I haven't run anything on your machine.

**What I assumed:** you use Homebrew (`/opt/homebrew`), you're on a recent macOS (13 or later), and you don't need a GUI.

---

## Install

1. **If Docker Desktop is installed, quit it and uninstall it.** Use Troubleshoot → Uninstall, or delete the app. Then open `~/.docker/config.json`. If it has `"credsStore": "desktop"`, change it to `"osxkeychain"` or delete that line. If you skip this, `docker login` and image pulls break after Desktop is gone.

2. **Install the tools:**
   ```sh
   brew install colima docker docker-compose docker-buildx docker-credential-helper
   ```

3. **Let the Docker CLI find the Compose and Buildx plugins.** Homebrew puts them somewhere the CLI doesn't look by default. Add this to `~/.docker/config.json`, merging with whatever is already there:
   ```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"],
     "credsStore": "osxkeychain"
   }
   ```

## First run

```sh
# Start the VM. vz = Apple's native hypervisor; --vz-rosetta speeds up any amd64 images
colima start --vm-type vz --vz-rosetta --cpu 4 --memory 8 --disk 60

# Check that it works
docker context ls          # "colima" should be marked active (*)
docker version             # Server should report linux/arm64
docker run --rm hello-world
docker compose version
```

Then go to one of your projects and run `docker compose up` as usual.

**Day-to-day commands:**
- `colima stop` / `colima start`: stop and start the VM. It remembers your settings.
- `colima status`: check whether it's running.
- `brew services start colima`: start it automatically at login.
- `colima start --edit`: change CPU, memory or disk later.

**Possible problems:**
- **Tools that look for `/var/run/docker.sock`** (Testcontainers, some IDE plugins) may not find Colima. Fix it with:
  ```sh
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
  ```
  For Testcontainers, also set:
  ```sh
  export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock
  ```
- **Images that only exist for amd64** still run through Rosetta, but slower. You can force one with `--platform linux/amd64`.
- **Bind-mounted volumes** work for paths under your home folder by default.

---

## Other options

| Tool | When to choose it | Notes |
|---|---|---|
| **Podman** (`brew install podman`, then `podman machine init && podman machine start`) | Your company prefers Red Hat tooling or rootless containers | Apache 2.0. The commands are almost the same as Docker's. To use the `docker` CLI with it you need extra setup (`podman-mac-helper` or `DOCKER_HOST`). Compose works through `podman compose` or `docker-compose`, but less smoothly than with Colima. |
| **Rancher Desktop** | You want a GUI like Docker Desktop's | Apache 2.0. Choose the "dockerd (moby)" engine for Docker CLI and Compose compatibility. It's heavier and comes with Kubernetes. |
| OrbStack | — | Fast and polished, but **not open source** and paid for commercial use, so it doesn't meet your requirements. |
| Apple `container` | — | Open source and arm64-native, but it doesn't speak the Docker API, so `docker compose` won't work with it. |

**Bottom line:** Colima plus Homebrew's `docker` and `docker-compose` packages is the closest drop-in replacement. It's free and open source, terminal-only, runs arm64 natively, and you keep the commands you already use.