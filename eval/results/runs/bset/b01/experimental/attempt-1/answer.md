I'd use **nsjail** (github.com/google/nsjail), running as root so it can set up the jail and then drop each bot to an unprivileged user. Google maintains it and uses it in kCTF, its CTF hosting setup. It was built for this kind of job: CTF challenges and online judges that run untrusted code and talk to it over stdin/stdout.

I didn't test anything for this answer. pickfit had no tested tool for this request; it also suggested nsjail but hadn't installed it either. What follows is from my own knowledge, so check the flags against `nsjail --help` for your version.

## Why nsjail fits
- **Files:** each bot gets its own empty filesystem. You read-only mount just what Python needs (`/usr`, `/lib*`) plus the bot's script. There's no `/home`, `/etc`, `/proc`, `/tmp` or other bots' code, and nothing it can write to.
- **Network:** each bot gets its own network namespace by default, with only a private loopback. It can't reach the internet, your host's localhost services, or other bots. Unix sockets on the host aren't visible because they aren't mounted.
- **Extra layer:** seccomp, a kernel filter on system calls, can block socket creation altogether.
- **Limits:** CPU, memory, number of processes and file size, through rlimits and cgroups v2.
- **I/O:** in `-Mo` mode it runs one process and passes your controller's stdin/stdout pipes straight through.

## Install
On Debian/Ubuntu, `sudo apt install nsjail` may work if your release has the package. Otherwise build it from source:
```bash
sudo apt install autoconf bison flex gcc g++ git libprotobuf-dev libnl-route-3-dev \
                 libtool make pkg-config protobuf-compiler
git clone https://github.com/google/nsjail.git
cd nsjail && make
sudo install -m 755 nsjail /usr/local/bin/
```
Two things to watch for:
- **Ubuntu 23.10+ / 24.04** blocks unprivileged user namespaces through AppArmor. Running nsjail as root from your controller avoids this.
- **cgroups v2** (default on current distros) need `--use_cgroupv2`. That's easiest when nsjail runs as root.

## First run: the launch command your controller uses
```bash
nsjail -Mo --quiet \
  --user 65534 --group 65534 \
  --hostname bot \
  --disable_proc \
  -R /usr -R /lib -R /lib64 -R /bin \
  -R /srv/bots/BOT_ID/bot.py:/bot/bot.py \
  --cwd /bot \
  --rlimit_as 1024 --rlimit_cpu 600 --rlimit_fsize 0 --rlimit_nofile 16 \
  --use_cgroupv2 --cgroup_mem_max $((512*1024*1024)) --cgroup_pids_max 4 \
  --seccomp_string 'ERRNO(1) { socket, socketpair } DEFAULT ALLOW' \
  -- /usr/bin/python3 -I -S -u /bot/bot.py
```
What the less obvious parts do:
- `-I` stops Python from loading code from the current directory or reading environment variables.
- `-S` skips `site`, so there are no user site-packages.
- `-u` turns off output buffering so moves arrive right away.
- If your distro has no `/lib64`, drop that mount.

Your controller starts this as a subprocess with stdin/stdout as pipes, exactly as it starts plain Python now.

**Check it works** by uploading a hostile test bot that tries each of these, and confirm every one fails:
```python
import os, socket
for f in (lambda: open('/etc/passwd').read(),
          lambda: os.listdir('/home'),
          lambda: socket.create_connection(('1.1.1.1', 80), 2),
          lambda: open('/bot/x', 'w'),
          lambda: os.fork()):
    try: f(); print("ESCAPED", flush=True)
    except Exception as e: print("blocked:", type(e).__name__, flush=True)
```
Then check that a normal bot still plays a full game.

## Caveats
- **Python's own files are readable.** Bots can read the read-only `/usr`, which has no secrets. To hide even that, unpack a self-contained Python build (for example python-build-standalone) into its own directory and mount only that.
- **No preinstalled libraries.** Bots only get the standard library unless you mount a fixed set of packages, read-only. Tell participants which ones.
- **Your controller has to enforce some things itself:**
  - a wall-clock timeout per move, because rlimits only count CPU time and a sleeping bot uses none;
  - a cap on line length and total output;
  - killing the jail when the game ends (nsjail's `--time_limit` sets a wall-clock cap for the whole run).
- **Kernel bugs.** A sandbox like this shares the host's kernel, so a kernel exploit could get out. Keep the kernel patched. For defense in depth, run the whole tournament runner on a separate VM with no secrets, or add **gVisor** (`runsc`), which places a user-space kernel between the bots and the host.

## Alternatives
- **isolate** (github.com/ioi/isolate) is the sandbox used for programming olympiads, through their contest management system. It's maintained and designed for contestant programs that use stdin/stdout. Version 2.x needs cgroup v2 and a root setup service. Its options are fewer and more opinionated than nsjail's; that's a good thing if its defaults suit you.
- **bubblewrap** (`bwrap`) is maintained and packaged everywhere because Flatpak uses it. `--unshare-all` plus read-only binds of `/usr` gives similar isolation. It has no built-in resource limits, so you'd add those with `systemd-run --scope -p MemoryMax=… -p TasksMax=…` or prlimit.
- **Docker/Podman** with `--network none --read-only --cap-drop ALL --pids-limit --memory`, optionally with the gVisor runtime. It works, but starts more slowly for each bot process.

My default would be nsjail running as root, ideally on a dedicated VM. If you'd rather use a sandbox that programming contests already rely on, use isolate.