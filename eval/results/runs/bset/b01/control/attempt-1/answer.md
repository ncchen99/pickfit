I recommend **nsjail** (github.com/google/nsjail), Google's process sandbox. It fits your setup closely: it starts one program, hands it your stdin/stdout, and restricts everything else. It's actively maintained. The latest release is 3.6, which fixed a seccomp bug that made 3.5 unsafe, so use 3.6 or newer.

My assumptions: you're on a modern distro (Debian/Ubuntu or similar, kernel 5.x+ with cgroup v2), and your controller can start nsjail as root or with enough privileges. I haven't run any of this; the commands below are for you to adapt and test.

## Why nsjail fits

- **No network:** by default it gives each process its own empty network namespace. There are no interfaces (not even a working loopback), so the bot can't reach the internet, other machines, localhost services or the host's abstract Unix sockets.
- **Almost no files:** the bot gets a fresh, empty root filesystem. Only what you explicitly mount appears, read-only: the Python install and that one bot's file. It can't see `/home`, `/etc`, your controller or other bots. Python has to read its own standard library, so "no file access" in practice means "nothing except a read-only interpreter."
- **Isolation from other processes:** separate PID, IPC, UTS and user namespaces. Inside the jail the bot runs as an unprivileged user ID that maps to nobody on the host.
- **Resource limits:** rlimits plus cgroup caps on memory, process count and CPU, so fork bombs and memory hogs don't take down the server.
- **Optional seccomp syscall filter** for extra hardening.
- **stdin/stdout passed straight through** in `-Mo` ("run once") mode. Other inherited file descriptors are closed unless you pass them on purpose.

## Install

Debian 12+/Ubuntu 22.04+ package it, but check the version:
```bash
sudo apt install nsjail
nsjail --help | head -1
```
If the packaged version is older than 3.6, build from source instead:
```bash
sudo apt install autoconf bison flex gcc g++ git libprotobuf-dev libnl-route-3-dev \
                 libtool make pkg-config protobuf-compiler
git clone https://github.com/google/nsjail.git
cd nsjail && git checkout 3.6   # or newest tag
make
sudo cp nsjail /usr/local/bin/
```

## First run

1. Save each upload to its own directory, e.g. `/srv/bots/<id>/bot.py`, owned by root and not writable by the bot.
2. Have your controller start the bot like this instead of calling `python3 bot.py` directly:

```bash
nsjail -Mo --quiet \
  --use_cgroupv2 \
  --cgroup_mem_max $((512*1024*1024)) \
  --cgroup_pids_max 16 \
  --cgroup_cpu_ms_per_sec 1000 \
  --rlimit_as soft --rlimit_cpu 300 --rlimit_fsize 0 --rlimit_nofile 32 \
  --time_limit 1800 \
  --user 65534 --group 65534 \
  --hostname bot \
  -R /usr -R /lib -R /lib64 -R /bin \
  -R /dev/urandom -R /dev/null \
  -R /srv/bots/123/bot.py:/bot/bot.py \
  --cwd /bot \
  -- /usr/bin/python3 -I -B /bot/bot.py
```

What the flags do:
- `-I` runs Python in isolated mode: it ignores `PYTHON*` environment variables, user site-packages and the current directory on `sys.path`. `-B` stops it from trying to write `.pyc` files.
- `--rlimit_fsize 0` blocks writing files. If bots need scratch space, add `-T /tmp`, but count that tmpfs against the memory limit.
- Network isolation is on by default. Don't add `--disable_clone_newnet`.
- If the server uses a venv or a non-system Python, also mount that directory read-only with `-R`. Never mount anything writable that's shared between bots.
- `--use_cgroupv2` needs either root or a delegated cgroup subtree (e.g. `systemd-run --scope -p Delegate=yes`).
- On Ubuntu 23.10+/24.04, AppArmor blocks unprivileged user namespaces. Run nsjail as root (it drops privileges itself) or add an AppArmor profile for it.

3. **Check the sandbox with hostile test bots** before going live. Each of these should fail or be killed:
   - `open('/etc/passwd')` and `os.listdir('/srv/bots')`
   - `socket.create_connection(('1.1.1.1', 80))` and connecting to `127.0.0.1:<port of a service you run>`
   - a fork bomb (`while True: os.fork()`)
   - a memory hog (`x = 'a' * 10**10`) and an infinite CPU loop
   - `open('/bot/x', 'w')`

4. Optional hardening: add a seccomp policy with `--seccomp_string` or `--seccomp_policy`. The repo's `configs/` directory has examples, and you can also put all of the options above in a config file.

## Your controller still needs to protect itself

The sandbox only limits what the bot can reach. Your controller has to handle bad output:
- Put a wall-clock timeout on every read, and read with a maximum line length. Don't call `readline()` with no limit.
- Treat every move as hostile input: parse it strictly and forfeit or kill the bot on any protocol violation.
- Send stderr to a size-capped log, or `/dev/null`. Don't let a full pipe deadlock you.
- Start a fresh jail for each match, kill the whole jail when the match ends, and never reuse a bot process across opponents.

## Alternatives

- **isolate** (github.com/ioi/isolate): the sandbox used by programming-contest judges, built for exactly this "run untrusted contestant code" case and still maintained (it uses tags, not GitHub releases). It's a good choice if you like its box/cgroup model. It's a bit more opinionated and needs root setup.
- **bubblewrap (`bwrap`)**: maintained (it's what Flatpak uses) and gives similar namespace isolation with `--unshare-all`, but it has no built-in resource limits. You'd need to add `systemd-run`/`prlimit` yourself.
- **gVisor (`runsc`)**: use this on top if you're worried about Linux kernel exploits, which namespace sandboxes can't stop. It runs the bot against a user-space kernel. The cheapest version of that protection is running the whole tournament on a dedicated, disposable VM with nothing else on it, which I'd recommend anyway.
- **Skip** firejail (setuid, large attack surface, designed for desktop apps) and pure-Python sandboxes like RestrictedPython or pysandbox (escapable, and the reason so many of these projects were abandoned).

Sources:
- [nsjail releases](https://github.com/google/nsjail/releases)
- [ioi/isolate](https://github.com/ioi/isolate)