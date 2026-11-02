# My recommendation: Colima with the open-source Docker CLI

**Colima** (MIT license) runs a small Linux VM on your Mac using Apple's Virtualization.framework. The Docker Engine runs inside that VM. You keep using the standard `docker`, `docker compose` and `docker buildx` commands, which are Apache-2.0 and free for any company size. Images run as native arm64 by default. For amd64-only images, Rosetta can translate them so they run at near-native speed.

I checked pickfit's tested catalog first. It had no relevant match: it returned AI tools, not container runtimes. So this recommendation comes from my own knowledge and was not tested by pickfit. I didn't run anything on your machine.

**Assumptions:** you use Homebrew, and you only need the terminal, not a GUI.

## Install

1. **Quit Docker Desktop and uninstall it.** Its `/usr/local/bin/docker` symlinks and its credential helper can conflict with the Homebrew versions. Your Docker Desktop images and volumes won't carry over, so re-pull or rebuild them. Export any volume data you need before uninstalling.
2. Install the runtime and the CLI tools:
   ```bash
   brew install colima docker docker-compose docker-buildx
   ```
3. Make `docker compose` (with a space) and `docker buildx` work as plugins. Add this to `~/.docker/config.json`, merging it with any keys already there:
   ```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   }
   ```
   If the file still has `"credsStore": "desktop"` from Docker Desktop, remove that line or change it to `"osxkeychain"` (that also needs `brew install docker-credential-helper`). Otherwise `docker login` and `docker pull` may fail.

## First run

```bash
# Start the VM: Apple's virtualization, Rosetta for amd64 images; adjust the sizes
colima start --vm-type vz --vz-rosetta --cpu 4 --memory 8 --disk 100

docker context ls                 # "colima" should be active (*)
docker run --rm hello-world
docker run --rm alpine uname -m   # should print aarch64
docker run --rm --platform linux/amd64 alpine uname -m   # x86_64, via Rosetta
docker compose version
```

Then run `docker compose up` in one of your projects to confirm your usual workflow works.

**Useful extras:**
- `brew services start colima` starts it automatically at login. Otherwise run `colima start` / `colima stop` yourself.
- `colima stop`, then `colima start --cpu 6 --memory 12` resizes CPU and memory. Changing the disk size or VM type may need `colima delete`, which erases the VM's images and volumes.
- Some tools expect `/var/run/docker.sock`, for example Testcontainers and some IDE plugins. You can point them at Colima with `export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"`. Or create the symlink: `sudo ln -sf ~/.colima/default/docker.sock /var/run/docker.sock`. That needs sudo, so decide whether you want it.
- Bind mounts work for paths under your home directory by default.

## Other options

| Option | License | When to pick it |
|---|---|---|
| **Rancher Desktop** | Apache-2.0 | You want a GUI. Choose the "dockerd (moby)" engine in its settings and the `docker` and `docker compose` commands work as usual. |
| **Podman** (+ `podman machine`) | Apache-2.0 | You prefer daemonless or rootless containers. It's mostly Docker-compatible through `podman-mac-helper` and Docker's compose binary, but Compose and BuildKit have more small differences. |
| **Lima** (the layer Colima is built on) | Apache-2.0 | You want to configure the VM yourself. More setup work. |

Two options to skip for your case:
- **OrbStack** is fast but closed-source, and commercial use needs a paid license.
- **Apple's `container` tool** is open source, but it isn't a drop-in for `docker` or `docker compose` commands.

Check with your legal or IT team that installing these tools fits company policy. Docker Desktop's paid-license rule applies once a company has more than 250 employees or more than $10M in annual revenue. The Docker Engine and CLI on their own don't have that rule.