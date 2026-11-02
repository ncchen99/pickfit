# Recommendation: Colima + the open-source Docker CLI

Use **[Colima](https://github.com/abiosoft/colima)** (MIT license). It runs a small Linux VM on your Mac with the open-source Docker Engine (Moby) inside it. You then use the Homebrew `docker` and `docker compose` command-line tools against that VM. Your existing commands, `docker-compose.yml` files and arm64 images work as before. It's terminal-only, and Docker Desktop's subscription terms don't apply to it.

**Why it fits:**
- **Same commands:** `docker`, `docker compose` and `docker buildx` keep working, because it's the real Docker CLI talking to a real Docker Engine.
- **arm64 by default:** On Apple silicon the VM is arm64, so arm64 images run natively. amd64 images also run, through Rosetta.
- **Fast:** It uses Apple's Virtualization.framework (`vz`) and virtiofs for file sharing.
- **Free and open source:** No license fees and no account needed.

## Install

I'm assuming you use Homebrew and are on a recent macOS. Colima's `vz` mode needs macOS 13 or later.

1. **Quit and uninstall Docker Desktop first.** Use Docker Desktop → Troubleshoot → Uninstall, or drag it from Applications to the Trash. Otherwise its `/usr/local/bin/docker` links can clash with the Homebrew tools.

2. **Install the tools:**
   ```sh
   brew install colima docker docker-compose docker-buildx
   ```

3. **Make `docker compose` (with a space) and `docker buildx` work.** Homebrew installs them as CLI plugins, so add this to `~/.docker/config.json`. Create the file if it doesn't exist, and merge this in if it does:
   ```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   }
   ```
   If the file has a `"credsStore": "desktop"` line left over from Docker Desktop, delete that line. Otherwise `docker login` and `docker pull` may fail.

4. **(Optional) Install Rosetta** so amd64-only images also run fast:
   ```sh
   softwareupdate --install-rosetta --agree-to-license
   ```

## First run

```sh
# Start the VM. Adjust CPU, memory (GB) and disk (GB) to suit your machine.
colima start --vm-type vz --vz-rosetta --mount-type virtiofs --cpu 4 --memory 8 --disk 100

# Check it's working
docker context ls          # "colima" should be the active context (marked *)
docker run --rm hello-world
docker run --rm alpine uname -m    # should print: aarch64
docker compose version

# In a project folder
docker compose up -d
```

**Everyday commands:**
- `colima stop` and `colima start`: start reuses your saved settings.
- `colima status`
- `colima list`
- `brew services start colima`: starts Colima automatically when you log in.
- `colima start --edit`: changes the CPU, memory or disk settings later.

**If a tool can't find Docker:** some tools, such as Testcontainers or certain IDE plugins, look for `/var/run/docker.sock` instead of using Docker contexts. Point them at Colima's socket by adding this to `~/.zshrc`:
```sh
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
```

**Running an amd64 image:** add `--platform linux/amd64` to the command, or `platform: linux/amd64` in your compose file.

## Alternatives

- **Rancher Desktop** (Apache 2.0, by SUSE): free and open source, with a graphical app. Pick the "dockerd (moby)" engine and the normal `docker` and `docker compose` commands work. Choose this if your teammates want a GUI similar to Docker Desktop.
- **Podman** (Apache 2.0): `brew install podman && podman machine init && podman machine start`. It can imitate the Docker socket, but it isn't Docker underneath, so compose, networking and build behavior can occasionally differ. It works, but it doesn't drop in as cleanly as Colima.
- **Apple's `container` tool**: open source and arm64-native, but it uses its own commands, not `docker` or `docker compose`. It doesn't meet your requirement yet.
- **Avoid OrbStack:** it's polished but not open source, and it needs a paid license for commercial use.

Since your company is now over the threshold, it's worth telling IT or legal you've switched, so they know Docker Desktop is fully removed.