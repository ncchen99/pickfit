## Recommendation: Colima

[Colima](https://github.com/abiosoft/colima) is MIT-licensed and runs a lightweight Linux VM on macOS using Lima. It provides the Docker engine behind the standard `docker` and `docker compose` CLIs, so existing commands and compose files keep working. On Apple silicon it runs native arm64 containers. The Docker CLI and Compose are Apache-2.0 and remain free. The paid license applies to Docker Desktop, not to these tools.

I assumed you have Homebrew and want a terminal-only setup. I didn't run anything on your machine or check current versions online, so confirm the flags below against `colima start --help` for your installed version.

## Install

1. Quit and uninstall Docker Desktop first so the two don't conflict. Keep your images and volumes in mind; they won't carry over automatically.
2. Install the tools:
   ```sh
   brew install colima docker docker-compose docker-buildx
   ```
   The `docker` formula is the CLI only, not the engine.
3. Let the CLI find the compose and buildx plugins. Edit `~/.docker/config.json` (create it if missing) and add or merge this key, keeping any existing keys such as `credsStore`:
   ```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   }
   ```
   On Apple silicon, Homebrew's prefix is `/opt/homebrew`.

## First run

```sh
colima start --vm-type vz --vz-rosetta --mount-type virtiofs --cpu 4 --memory 8 --disk 60
docker context use colima
docker run --rm hello-world
docker info --format '{{.Architecture}}'   # should print aarch64
docker compose version
```

- `--vm-type vz` uses Apple's Virtualization.framework, which is fast on Apple silicon.
- `--vz-rosetta` lets the VM run `linux/amd64` images through Rosetta. Use `docker run --platform linux/amd64 ...` only when you need it, since emulated containers are slower.
- `--mount-type virtiofs` gives faster bind mounts.
- Adjust `--cpu`, `--memory`, and `--disk` to your machine.

To start Colima automatically at login:
```sh
brew services start colima
```

Day to day: `colima start`, `colima stop`, `colima status`.

## Caveats

- There is no GUI. Use `colima list` and `docker` commands instead.
- Kubernetes is not on by default. Add `--kubernetes` to `colima start` if you need it.
- Check any compose file that uses `host.docker.internal` after the first run.

## Alternatives if Colima doesn't fit

- **Rancher Desktop** (Apache-2.0): has a GUI, a docker-compatible CLI, and a dockerd (moby) engine option. Choose this if your team wants a visual dashboard.
- **Podman** (Apache-2.0): works with `podman compose` and can be aliased to `docker`, but it is not a drop-in replacement for every Docker workflow. Use it only if you're willing to test your compose files.

**Avoid OrbStack** for company use. It is free for personal use but requires a paid commercial license, and it is not open source.