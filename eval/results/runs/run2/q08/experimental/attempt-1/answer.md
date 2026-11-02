I recommend **Colima** with the free, open-source Docker CLI and Compose plugin from Homebrew.

Colima (MIT license) runs a small Linux VM on your Mac with the Docker engine inside it. The `docker` and `docker compose` commands you already use talk to that engine through a Docker "context," so your commands and compose files stay the same. On Apple silicon the VM is arm64, so arm64 images run natively. Docker's license applies to the Docker Desktop app, not to the Docker CLI or engine, which are Apache-2.0.

**How I checked:** the recommendation tool I used (pickfit) has no tested option for this. It named Colima as the closest match, but it hasn't installed or tested it. The steps below come from my own knowledge of Colima's usual setup and haven't been run on your machine. I'm assuming you use Homebrew and macOS 13 or later.

## Install

1. **Quit Docker Desktop and uninstall it** (Troubleshoot → Uninstall, or drag it to the Trash). This stops it from owning `/usr/local/bin/docker` and the `docker.sock` symlink. Your old Desktop images and volumes won't carry over. Rebuild or re-pull them, or `docker save` anything important before uninstalling.
2. Install the tools:
   ```sh
   brew install colima docker docker-compose docker-buildx docker-credential-helper
   ```
3. Tell the Docker CLI where Homebrew put the plugins, so `docker compose` and `docker buildx` work as subcommands. Add this to `~/.docker/config.json`:
   ```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   }
   ```
   If the file already has a `"credsStore": "desktop"` line left over from Docker Desktop, change it to `"osxkeychain"` or delete it. Otherwise `docker login` and pulls will fail.

## First run

```sh
# Start the VM with Apple's Virtualization framework; Rosetta speeds up any amd64 images
colima start --cpu 4 --memory 8 --disk 100 --vm-type vz --vz-rosetta

docker context ls          # "colima" should be marked active (*)
docker run --rm hello-world
docker run --rm alpine uname -m   # should print aarch64
docker compose version
```

Then go to one of your projects and run `docker compose up` as usual.

**Day-to-day commands:**
- Stop and start: `colima stop` / `colima start` (it remembers your settings).
- Start automatically at login: `brew services start colima`.
- Change CPU, memory or disk later: `colima stop`, then `colima start --edit`.
- To run a single amd64 image: `docker run --platform linux/amd64 …`

**Things to watch for:**
- **Tools that expect `/var/run/docker.sock`** (Testcontainers, some IDE plugins): point them at Colima's socket with `export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"`. For Testcontainers, also set `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`.
- **Bind mounts:** by default only your home directory is mounted into the VM. To use bind mounts from other paths, add them under `mounts:` with `colima start --edit`.
- **Ports:** forwarding to `localhost` works automatically.

## Alternatives if Colima doesn't suit you
- **Rancher Desktop** (Apache-2.0, free): a GUI app. Pick the "dockerd (moby)" engine and the docker and compose commands work the same way. It's a good choice if you also want a local Kubernetes cluster.
- **Podman** (Apache-2.0): run `podman machine init --rootful && podman machine start`. `docker compose` can talk to its Docker-compatible socket, but it's a little less of a drop-in replacement than Colima.
- **Not free for you:** OrbStack needs a paid license for commercial use. Apple's open-source `container` tool doesn't work with the `docker` or `compose` commands.