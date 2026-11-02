**Main recommendation: Colima.** It's free and open source (MIT), runs Docker in a lightweight Linux VM on Apple silicon, and exposes the standard `docker` and `docker compose` CLIs. It runs arm64 images natively.

**Caveat:** pickfit did not verify Colima. It has no install guide for it in its data, so the steps below come from public docs and guides, not from a tested run. Pickfit's own search returned no verified replacement and recommended keeping Docker Desktop. Colima is the best-known free option I found, so that's the one I'm recommending.

## Install (run these yourself)

Requires Homebrew and macOS 13 or later.

```sh
brew install colima docker docker-compose
```

- `colima` is the runtime.
- `docker` is the CLI.
- `docker-compose` provides the Compose v2 plugin, so `docker compose` works as a subcommand.

## First run

1. Start the VM with arm64 native images and a sensible resource size:
   ```sh
   colima start --arch aarch64 --vm-type vz --cpu 4 --memory 8
   ```
   `vz` uses Apple's Virtualization framework and is the fastest option on Apple silicon.

2. Let the `docker` CLI find the Compose plugin. Edit `~/.docker/config.json` (create it if it doesn't exist) and add:
   ```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   }
   ```
   Keep any existing keys in the file. On Intel Macs Homebrew's prefix is `/usr/local`, but you're on Apple silicon, so `/opt/homebrew` is correct.

3. Verify:
   ```sh
   docker version
   docker compose version
   docker run --rm hello-world
   docker run --rm alpine uname -m    # should print aarch64
   ```

4. Check your existing project with `docker compose up -d` in its directory.

**Optional:** to run amd64 images, restart with `colima stop && colima start --arch aarch64 --vm-type vz --vz-rosetta`. Rosetta emulation is much faster than QEMU emulation.

**Day to day:** `colima start` and `colima stop`. Colima also creates a `colima` Docker context and switches to it on start.

## Things to check

- **Bind mounts and file sharing:** Colima shares your home directory by default. If you use other paths, add them with `--mount`.
- **Docker Desktop features:** Colima doesn't include Docker Desktop's GUI, Kubernetes toggle, or some extensions. Kubernetes can be enabled with `colima start --kubernetes`.
- **Licensing:** Colima is MIT-licensed, and Homebrew is free. I did not check Docker's current terms myself, so confirm them on docker.com before you rely on them.

## Alternatives (not verified by pickfit)

- **Rancher Desktop:** free, open source, with a GUI and dockerd or containerd backends.
- **Podman Desktop with Podman:** free and open source. Its `docker` CLI compatibility is not complete, so check your Compose files before switching.

Sources:
- [Colima Docker Desktop alternatives overview (oneuptime, 2026)](https://oneuptime.com/blog/post/2026-01-16-docker-desktop-alternatives/view)
- [Colima vs Docker Desktop (1gbits)](https://1gbits.com/blog/docker-desktop-vs-colima/)
- [Install Docker Engine without Docker Desktop on macOS (oneuptime, 2026)](https://oneuptime.com/blog/post/2026-02-08-how-to-install-docker-engine-without-docker-desktop-on-macos/view)
- [Colima + Docker CLI setup guide (codenote)](https://codenote.net/en/posts/colima-docker-cli-setup-macos/)
- [Docker macOS setup with Colima (lucaberton)](https://lucaberton.com/blog/install-docker-macos/)