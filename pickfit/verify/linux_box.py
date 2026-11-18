"""LinuxBox: the Box interface on one provider's fresh Linux machine (machine.Machine).

Everything here happens inside the machine, through root commands the provider carries, so it is the same on
every provider. ModalBox (modal_box.py) is this box on Modal; the measurements below were made there.

- The machine's CPU, memory and lifetime are the provider's caps (Machine.start); every command also runs
  under an in-box `timeout -s KILL`.
- Commands run as uid 1000 through `setpriv` (no capabilities, no new
  privileges), with an empty environment except BOX_ENV, and `ulimit` caps on
  processes, open files and file size: a provider may have no pids or disk parameter (Modal has none).
- Network: the machine starts with outbound traffic limited to public IPv4 ranges (machine.ONLINE_CIDRS);
  cloud metadata (169.254.0.0/16) and private ranges are never reachable. set_network(False) has the provider
  close egress (Machine.set_egress), and each runtime also closes DNS itself (below): Modal's resolver
  172.21.0.1 still answers with an empty allowlist (both runtimes), and another provider's may too.
- gVisor (measured 2026-10-31): root has neither CAP_NET_ADMIN nor CAP_SYS_ADMIN and gVisor has no netfilter, so no
  rule, route or link change can close the resolver. Instead the box user never touches the box's own network:
  NET_UID makes a user and network namespace at start (root writes its maps: NET_UID is root inside it, the box
  user is itself, nothing else is mapped, so NET_UID has no power over root's or the display uid's files and
  processes), and every box-user command runs in it. Its only way out is slirp4netns, run as NET_UID (seccomp on,
  no route to the box's loopback, MTU 65520 on both ends: a tap left at 1500 stalls TCP); it carries the box user's
  traffic, DNS included, through the box's network and Modal's allowlist. set_network(False) kills every NET_UID
  process except the namespace's holder and checks that the uplink's device is gone, the holder holds nothing but
  its standard streams and every box-user process is in the holder's namespace: the box user then has loopback
  only, so localhost servers, including ones started online, still answer. The box user cannot enter another
  network namespace, change a route or signal NET_UID's processes. Downloads through it ran at the box's direct
  speed (CDNs 80-190 MB/s, a slow far server 1.2 MB/s either way).
- Image: sandbox.Dockerfile plus image_recipe()'s packages and commands for the kind of box (vm, gui, audio,
  build). The provider builds and names it; the recipe and its tag are the same everywhere.
- runtime="vm" (a microVM with its own kernel) is the same box otherwise, hardened by root before the box
  user runs anything (measured 2026-10-31): unprivileged user namespaces and io_uring are switched off; every
  box-user command runs under a seccomp filter that refuses AF_VSOCK sockets (the host's vsock port 52
  accepted the box user's connection); and while the network is off, an nftables rule drops the box user's
  DNS (a VM has netfilter; with user namespaces off, the gVisor way is closed to it). A VM gives 1 vCPU per
  requested core.
- display=True adds GUI_PACKAGES to the image; root starts Xvfb as a separate uid (DISPLAY_UID), which the box user
  can draw on but cannot kill or replace. Xvfb and every display-uid command run in the display's own network
  namespace, loopback only, held by root (gVisor: with a user namespace mapping root, the box user and the display
  uid; a VM: root's network namespace): a box-user SetFontPath request made Xvfb resolve a font server's name
  through Modal's resolver offline (review 2026-11-01). The box user's apps reach Xvfb by its socket file, which a
  network namespace does not hide. Evidence (window list, screenshot, its hash and copy) is made by root and
  DISPLAY_UID through harness_exec, by absolute path, in a directory the box user cannot open.
- display=True also installs flatpak, so a Flathub app installs the way its page says, as the box user
  (`flatpak install --user`; bubblewrap needs user namespaces, so only under gVisor). Root starts a system D-Bus as
  messagebus (via setpriv) with no service activation and no name anyone may own: a desktop has one, and flatpak's
  parental-controls check fails without it but passes when it finds no accounts service. Under gVisor flatpak runs
  bubblewrap through BWRAP_SHIM (FLATPAK_BWRAP): gVisor cannot bring up the loopback of a network namespace made in
  the box user's, nor bind-mount /proc/self/ns/user, so the shim drops --unshare-net and that bind and the app shares
  the box user's network namespace, which the offline cut covers. Measured 2026-11-01: a GNOME app installed in 43 s
  and showed its window offline.
- gpu="T4" (or L4, A10) asks Modal for an NVIDIA card. Modal gives one only under gVisor (measured 2026-11-02:
  runtime="vm" with a GPU is refused, "GPUs are not supported with the VM runtime"): gVisor's nvproxy adds
  /dev/nvidiactl, /dev/nvidiaN, /dev/nvidia-uvm and /dev/nvidia-uvm-tools (mode 0666) and passes only the driver
  calls it knows to the host's driver; Modal mounts the driver's libraries and nvidia-smi (no CUDA toolkit). The
  box user reaches the card from its network namespace with no capabilities; nothing else about the box changes.
  Root reads the card's name with nvidia-smi at start (the run records it), and a box whose card does not answer
  fails to start. The limits test's gpu_contained probe checks the box user's devices.
- audio=True adds AUDIO_PACKAGES and a simulated microphone (audio.py): root starts PulseAudio as DISPLAY_UID in the
  display's network namespace (made for an audio box without a display too); the box user's apps reach it by its
  socket file, as they reach Xvfb.
- Commands name their programs by absolute path: the box user's ~/.local/bin comes first on its PATH.

"""

from __future__ import annotations

import hashlib
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass

from pickfit.verify.audio import AUDIO_PACKAGES, PULSE_SERVER, pulse_script
from pickfit.verify.box import (
    BOX_ENV,
    BOX_HOME,
    BOX_WORKDIR,
    GO_VERSION,
    OUTPUT_HEAD_BYTES,
    OUTPUT_TAIL_BYTES,
    RUST_VERSION,
    SANDBOX_DOCKERFILE,
    Box,
    BoxError,
    BoxLimits,
    ExecResult,
    _Capture,
)
from pickfit.verify.gui import DISPLAY, DISPLAY_UID, EVIDENCE_DIR, GUI_PACKAGES, HARNESS_PATH, PYTHON, xvfb_script
from pickfit.verify.machine import RUNTIMES, Machine

READ_TIMEOUT_S = 20  # read_file: a FIFO or a device would block `head` forever
# Root, at start: the card the run records, and its driver (Flathub's NVIDIA GL extension must match it).
GPU_NAME = "/usr/bin/nvidia-smi --query-gpu=name,driver_version --format=csv,noheader"
# Display images: VirtualGL (wxWindows Library Licence), so a GPU box's apps can draw with OpenGL on the card. Xvfb's
# own OpenGL is software (llvmpipe), and NVIDIA's GLX needs NVIDIA's X server; VirtualGL's EGL back end sends an
# app's GLX calls to the card's headless EGL (measured 2026-11-02: OpenGL 4.6 on the T4 under gVisor; Vulkan fails).
VGL_DEB = "https://github.com/VirtualGL/virtualgl/releases/download/3.1.5/virtualgl_3.1.5_amd64.deb"
VGL_SHA256 = "df3f7788ce41b182a47c0d298e5cd6d2d63579522cb41825970b7726e825485e"
VGL_INSTALL = (f"curl -fsSL -o /tmp/virtualgl.deb {VGL_DEB} && echo '{VGL_SHA256}  /tmp/virtualgl.deb' | sha256sum -c - "
               "&& apt-get update && apt-get install -y --no-install-recommends /tmp/virtualgl.deb "
               "&& rm -rf /var/lib/apt/lists/* /tmp/virtualgl.deb && ln -sf /opt/VirtualGL/bin/vglrun /usr/local/bin/vglrun")
BOX_UID = 1000
NET_UID = 1002  # gVisor: owns the box user's network namespace and runs its uplink; root only inside that namespace
UPLINK = "/usr/bin/slirp4netns"
TAP = "tap0"
# slirp4netns's defaults: the namespace is 10.0.2.100/24, the gateway (slirp itself) 10.0.2.2.
UPLINK_MTU = 65520
TAP_CONFIG = (f"/usr/bin/ip link set {TAP} mtu {UPLINK_MTU} up && /usr/bin/ip addr add 10.0.2.100/24 dev {TAP} && "
              f"/usr/bin/ip route add default via 10.0.2.2 dev {TAP}")
UPLINK_LOG = "/var/log/pickfit-uplink.log"
# Display boxes: Flathub apps and the system bus a desktop has (flatpak's parental-controls check asks it).
FLATPAK_PACKAGES = ("flatpak", "dbus")
SYSTEM_BUS_CONF = "/usr/local/lib/pickfit/system-bus.conf"
SYSTEM_BUS_SOCKET = "/run/dbus/system_bus_socket"
SYSTEM_BUS_LOG = "/var/log/pickfit-system-bus.log"
# No servicedir, so nothing is ever activated (flatpak's system helper would run as root); nobody may own a name.
SYSTEM_BUS_CONF_SOURCE = """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>system</type>
  <listen>unix:path=/run/dbus/system_bus_socket</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow user="*"/>
    <deny own="*"/>
    <allow send_type="method_call"/>
    <allow send_type="signal"/>
    <allow send_requested_reply="true" send_type="method_return"/>
    <allow send_requested_reply="true" send_type="error"/>
    <allow receive_type="method_call"/>
    <allow receive_type="method_return"/>
    <allow receive_type="error"/>
    <allow receive_type="signal"/>
  </policy>
</busconfig>
"""
# Root: the config, then the bus as messagebus, detached like the display. setpriv drops to messagebus: dbus-daemon's
# own drop (<user>) needs capabilities root lacks under gVisor.
SYSTEM_BUS = ("/usr/bin/install -d -m 0755 /usr/local/lib/pickfit && "
              "/usr/bin/install -d -m 0755 -o messagebus -g messagebus /run/dbus && "
              f"/usr/bin/install -m 0644 /dev/stdin {SYSTEM_BUS_CONF} && "
              "{ /usr/bin/setsid /usr/bin/setpriv --reuid=messagebus --regid=messagebus --clear-groups --inh-caps=-all "
              f"--no-new-privs -- /usr/bin/dbus-daemon --config-file={SYSTEM_BUS_CONF} --nofork --nopidfile "
              f"> {SYSTEM_BUS_LOG} 2>&1 < /dev/null & }}; "
              f"for i in $(/usr/bin/seq 1 50); do [ -S {SYSTEM_BUS_SOCKET} ] && break; /usr/bin/sleep 0.1; done; "
              "/usr/bin/sleep 0.5; /usr/bin/pgrep -x dbus-daemon > /dev/null && echo system_bus_up || "
              f"/usr/bin/tail -5 {SYSTEM_BUS_LOG}")
# gVisor display boxes: flatpak's bubblewrap, less what gVisor cannot do inside the box user's namespaces.
BWRAP_SHIM = "/usr/local/lib/pickfit/bwrap-gvisor"
BWRAP_SHIM_SOURCE = f"""#!{PYTHON} -IS
# pickfit: bubblewrap for flatpak in a gVisor box. The same arguments without --unshare-net (gVisor cannot bring
# up the loopback of a network namespace made inside the box user's) and without binds of /proc/self/ns/* (gVisor
# cannot bind-mount them). Arguments flatpak passes through --args FD are rewritten into a memfd.
import os, sys
ALL = [b"--unshare-user-try", b"--unshare-ipc", b"--unshare-pid", b"--unshare-uts", b"--unshare-cgroup-try"]
BINDS = (b"--bind", b"--ro-bind", b"--bind-try", b"--ro-bind-try", b"--dev-bind", b"--dev-bind-try")
def options(args):
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a == b"--":
            return out + args[i:]
        if a in BINDS and i + 1 < len(args) and args[i + 1].startswith(b"/proc/self/ns/"):
            i += 3
            continue
        if a == b"--args" and i + 1 < len(args):
            fd, data = int(args[i + 1]), b""
            while chunk := os.read(fd, 65536):
                data += chunk
            os.close(fd)
            mem = os.memfd_create("bwrap-args", 0)
            os.write(mem, b"".join(x + b"\\0" for x in options(data.split(b"\\0")[:-1])))
            os.lseek(mem, 0, os.SEEK_SET)
            out += [b"--args", str(mem).encode()]
            i += 2
            continue
        if a != b"--unshare-net":
            out += ALL if a == b"--unshare-all" else [a]
        i += 1
    return out
if __name__ == "__main__":
    os.execv("/usr/bin/bwrap", [b"bwrap", *options([os.fsencode(a) for a in sys.argv[1:]])])
"""
INSTALL_BWRAP_SHIM = (f"/usr/bin/install -d -m 0755 /usr/local/lib/pickfit && "
                      f"/usr/bin/install -m 0755 /dev/stdin {BWRAP_SHIM}")
VM_PACKAGES = ("nftables",)  # root's offline DNS rule (VM only: gVisor has no netfilter)
# A build box (--toolchain): what "build from source" assumes a developer's machine already has. The C and C++
# compilers, make, cmake and the usual -dev headers are Debian's packages. Rust and Go are their projects' own
# releases, each checked against a pinned SHA-256 before it is unpacked, because a project's minimum version is
# often newer than a distribution's (box.RUST_VERSION, box.GO_VERSION).
TOOLCHAIN_PACKAGES = ("build-essential", "clang", "cmake", "ninja-build", "pkg-config", "autoconf", "automake",
                      "libtool", "perl", "libssl-dev", "zlib1g-dev", "libffi-dev", "libsqlite3-dev", "libclang-dev",
                      "protobuf-compiler")
RUST_URL = f"https://static.rust-lang.org/dist/2026-11-12/rust-{RUST_VERSION}-x86_64-unknown-linux-gnu.tar.xz"
RUST_SHA256 = "98ee6bec240e1cfe944f17e7092412dc5ef6e008484bb668c6936d35a7d15acd"
GO_URL = f"https://go.dev/dl/go{GO_VERSION}.linux-amd64.tar.gz"
GO_SHA256 = "7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840"
# Rust's standalone installer puts rustc, cargo and the standard library under /usr/local (no rustup, nothing in
# the box user's home); Go unpacks to /usr/local/go. The last line fails the build when one of them does not run.
TOOLCHAIN_INSTALL = (
    f"curl -fsSL -o /tmp/rust.tar.xz {RUST_URL} && echo '{RUST_SHA256}  /tmp/rust.tar.xz' | sha256sum -c - "
    "&& mkdir /tmp/rust && tar -xJf /tmp/rust.tar.xz -C /tmp/rust --strip-components=1 "
    "&& /tmp/rust/install.sh --prefix=/usr/local --components=rustc,cargo,rust-std-x86_64-unknown-linux-gnu "
    "&& rm -rf /tmp/rust /tmp/rust.tar.xz "
    f"&& curl -fsSL -o /tmp/go.tgz {GO_URL} && echo '{GO_SHA256}  /tmp/go.tgz' | sha256sum -c - "
    "&& tar -xzf /tmp/go.tgz -C /usr/local && rm /tmp/go.tgz "
    "&& ln -s /usr/local/go/bin/go /usr/local/go/bin/gofmt /usr/local/bin/ "
    "&& rustc --version && cargo --version && go version && cc --version && cmake --version")
# Drops the box user's DNS (to Modal's resolver or anywhere) while the network is off; root sets it.
DNS_TABLE = "pickfit_offline"
DNS_BLOCK = (f"/usr/sbin/nft add table inet {DNS_TABLE} && /usr/sbin/nft add chain inet {DNS_TABLE} out "
             "'{ type filter hook output priority 0; policy accept; }' && "
             f"/usr/sbin/nft add rule inet {DNS_TABLE} out meta skuid {BOX_UID} udp dport 53 drop && "
             f"/usr/sbin/nft add rule inet {DNS_TABLE} out meta skuid {BOX_UID} tcp dport 53 drop")
DNS_UNBLOCK = f"/usr/sbin/nft delete table inet {DNS_TABLE}"
# Root, before the box user runs anything in a VM (gVisor keeps user namespaces inside its own kernel).
VM_HARDEN = ("/usr/sbin/sysctl -qw user.max_user_namespaces=0 && "
             "{ /usr/sbin/sysctl -qw kernel.io_uring_disabled=2 2>/dev/null || true; } && "
             "/usr/bin/install -d -m 0755 /usr/local/lib/pickfit && "
             "/usr/bin/install -m 0644 /dev/stdin /usr/local/lib/pickfit/no_vsock.py")
NO_VSOCK = "/usr/local/lib/pickfit/no_vsock.py"
# A seccomp filter (x86_64): socket(AF_VSOCK, ...) fails with EAFNOSUPPORT, io_uring_setup/enter/register
# (425-427) with EPERM, other ABIs are killed; then exec. Inherited by every child and cannot be removed;
# setpriv has already set no_new_privs. The box user's commands, Xvfb and the watcher all run under it.
NO_VSOCK_SOURCE = r"""import ctypes, os, struct, sys
LD, JEQ, JGE, RET = 0x20, 0x15, 0x35, 0x06
ALLOW, ERRNO, KILL = 0x7FFF0000, 0x00050000, 0x80000000
prog = [(LD, 0, 0, 4), (JEQ, 0, 10, 0xC000003E), (LD, 0, 0, 0), (JGE, 8, 0, 0x40000000), (JEQ, 0, 2, 41),
        (LD, 0, 0, 16), (JEQ, 3, 2, 40), (JGE, 0, 1, 425), (JGE, 0, 2, 428), (RET, 0, 0, ALLOW),
        (RET, 0, 0, ERRNO | 97), (RET, 0, 0, ERRNO | 1), (RET, 0, 0, KILL)]
raw = b"".join(struct.pack("HBBI", *ins) for ins in prog)
buf = ctypes.create_string_buffer(raw, len(raw))
class Prog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, ctypes.byref(Prog(len(prog), ctypes.addressof(buf))), 0, 0):
    sys.exit(f"pickfit: seccomp failed: {os.strerror(ctypes.get_errno())}")
os.execv(sys.argv[1], sys.argv[1:])
"""


@dataclass(frozen=True)
class ImageRecipe:
    """What a kind of box adds to sandbox.Dockerfile: the same on every provider that builds the image."""

    kinds: tuple[str, ...]  # of vm, gui, audio, build
    packages: tuple[str, ...]  # Debian packages, installed with apt
    commands: tuple[str, ...]  # run as root after the packages: what is not a package (VirtualGL, Rust and Go)

    def tag(self, plain: str) -> str:
        """The image's name. The plain box keeps `plain` (sandbox.Dockerfile's own tag); a variant hashes the
        Dockerfile, its packages and its commands."""
        if not self.packages:
            return plain
        extra = "".join("\n" + command for command in self.commands)
        digest = hashlib.sha256(SANDBOX_DOCKERFILE.read_bytes()
                                + ("\n".join(self.packages) + extra).encode()).hexdigest()[:12]
        return f"pickfit-sbx-{'-'.join(self.kinds)}:{digest}"


def image_recipe(runtime: str = "gvisor", display: bool = False, audio: bool = False,
                 toolchain: bool = False) -> ImageRecipe:
    """The packages and commands a kind of box needs on top of sandbox.Dockerfile."""
    packages = (*(VM_PACKAGES if runtime == "vm" else ()), *(GUI_PACKAGES if display else ()),
                *(FLATPAK_PACKAGES if display else ()), *(AUDIO_PACKAGES if audio else ()),
                *(TOOLCHAIN_PACKAGES if toolchain else ()))
    kinds = tuple(k for k, on in (("vm", runtime == "vm"), ("gui", display), ("audio", audio),
                                  ("build", toolchain)) if on)
    commands = (*((VGL_INSTALL,) if display else ()), *((TOOLCHAIN_INSTALL,) if toolchain else ()))
    return ImageRecipe(kinds, packages, commands)


def gl_env(driver: str) -> list[str]:
    """A GPU display box's environment for OpenGL on the card: flatpak learns the driver from FLATPAK_GL_DRIVERS
    (gVisor has no /proc/driver/nvidia), so installing an app brings Flathub's matching NVIDIA GL extension, as on a
    desktop with that driver."""
    return [f"FLATPAK_GL_DRIVERS=nvidia-{driver.replace('.', '-')}:default"]


VGL_HOME = f"{BOX_HOME}/.pickfit-vgl"
# Root, at start of a GPU display box: VirtualGL's two libraries in the box user's home, and flatpak's global override
# for the box user, so every Flatpak app sees them and draws through VirtualGL's EGL back end (measured 2026-11-02:
# Vimix, which refuses software rendering, showed its window on the T4). A native app uses vglrun -d egl.
VGL_OVERRIDE = (f"[Context]\nfilesystems={VGL_HOME}:ro;\n\n[Environment]\n"
                f"LD_PRELOAD={VGL_HOME}/libdlfaker.so:{VGL_HOME}/libvglfaker.so\nVGL_DISPLAY=egl\n")
VGL_SETUP = (f"/usr/bin/install -d -m 0755 -o {BOX_UID} -g {BOX_UID} {VGL_HOME} {BOX_HOME}/.local/share/flatpak/overrides "
             f"&& /usr/bin/install -m 0644 -o {BOX_UID} -g {BOX_UID} /usr/lib/libdlfaker.so /usr/lib/libvglfaker.so {VGL_HOME}/ "
             f"&& /usr/bin/install -m 0644 -o {BOX_UID} -g {BOX_UID} /dev/stdin {BOX_HOME}/.local/share/flatpak/overrides/global "
             f"&& /usr/bin/chown {BOX_UID}:{BOX_UID} {BOX_HOME}/.local {BOX_HOME}/.local/share {BOX_HOME}/.local/share/flatpak")


def _drop_to(uid: int) -> list[str]:
    return ["/usr/bin/setpriv", f"--reuid={uid}", f"--regid={uid}", "--clear-groups", "--inh-caps=-all",
            "--no-new-privs", "--"]


# The maps go in one write each: the kernel takes a map from a single write, and bash's printf writes per line.
_MAP_PY = ("import sys\nfor name in ('uid_map', 'gid_map'):\n    with open(f'/proc/{sys.argv[1]}/{name}', 'w') as f:\n"
           "        f.write(sys.argv[2].replace(',', '\\n') + '\\n')\n")
NETNS_MAPS = f"0 {NET_UID} 1,{BOX_UID} {BOX_UID} 1"  # NET_UID is root inside; nothing of root's or the display's
# The display's namespace (gVisor) is root's: root enters it and drops to the display uid; the box user's uid is
# mapped so that the watcher reads its processes' uids from /proc.
DISPLAY_MAPS = f"0 0 1,{BOX_UID} {BOX_UID} 1,{DISPLAY_UID} {DISPLAY_UID} 1"


def holder_script(drop: list[str], namespaces: str, maps: str | None) -> str:
    """Root: a holder process (sleep, as `drop`'s uid) in new `namespaces`; with `maps`, root writes the uid and gid
    maps. Prints `netns_pid N` once the holder has its own network namespace."""
    write = f"{PYTHON} -I -S -c {shlex.quote(_MAP_PY)} $P {shlex.quote(maps)} && " if maps else ""
    return (f"{{ /usr/bin/setsid {' '.join(drop)} /usr/bin/unshare {namespaces} -- /usr/bin/sleep infinity "
            "> /dev/null 2>&1 < /dev/null & }; P=$!; "
            "for i in $(/usr/bin/seq 1 50); do "
            "[ \"$(/usr/bin/readlink /proc/$P/ns/net)\" != \"$(/usr/bin/readlink /proc/self/ns/net)\" ] && break; "
            "/usr/bin/sleep 0.1; done; "
            "[ \"$(/usr/bin/readlink /proc/$P/ns/net)\" != \"$(/usr/bin/readlink /proc/self/ns/net)\" ] && "
            f"{write}echo \"netns_pid $P\"")


def netns_script() -> str:
    """Root (gVisor): NET_UID makes the box user's user and network namespace, kept by a holder process; root maps
    NET_UID to root inside it and the box user to itself."""
    return holder_script(_drop_to(NET_UID), "--user --net", NETNS_MAPS)


def display_netns_script(runtime: str) -> str:
    """Root: the display's network namespace, loopback only, for Xvfb and every display-uid command (a box-user
    X request can make Xvfb resolve a font server's name). gVisor needs a user namespace for it (root has no
    CAP_SYS_ADMIN); a VM has user namespaces off and root can make a network namespace alone."""
    return holder_script([], "--user --net", DISPLAY_MAPS) if runtime == "gvisor" else holder_script([], "--net", None)


# Root, at the cut: every process of the box user's is in the holder's network namespace (none was started
# outside it or moved out). Its sockets are not checked: gVisor's /proc/net tables are not per namespace.
SAME_NETNS_PY = r"""import os, sys
holder, uid = sys.argv[1], sys.argv[2]
want, bad = os.readlink(f"/proc/{holder}/ns/net"), []
for p in filter(str.isdigit, os.listdir("/proc")):
    try:
        status = open(f"/proc/{p}/status").read().splitlines()
        if uid not in next(l.split()[1:] for l in status if l.startswith("Uid:")):
            continue
        if any(l.split()[1:2] == ["Z"] for l in status if l.startswith("State:")):
            continue
        ns = os.readlink(f"/proc/{p}/ns/net")
    except (FileNotFoundError, ProcessLookupError):
        continue
    except OSError as e:
        bad.append(f"{p}: {e}")
        continue
    if ns != want:
        bad.append(f"{p} is in {ns}")
if bad:
    sys.exit("box-user processes outside their network namespace: " + "; ".join(bad)[:300])
"""


def uplink_script(netns_pid: int, enabled: bool) -> str:
    """Root (gVisor): start slirp4netns as NET_UID and route the namespace through it; or kill every NET_UID process
    but the holder and check that the device is gone (a namespace that cannot be listed is an error, not "gone"),
    nothing else of NET_UID's runs, the holder holds only its standard streams (no socket handed to it from outside
    the namespace), and every box-user process is in the holder's network namespace."""
    drop = " ".join(_drop_to(NET_UID))
    inside = f"{drop} /usr/bin/nsenter --target={netns_pid} --user --net --"
    if enabled:
        return (f"{{ /usr/bin/setsid {drop} {UPLINK} --mtu={UPLINK_MTU} --disable-host-loopback --enable-seccomp "
                f"{netns_pid} {TAP} >> {UPLINK_LOG} 2>&1 < /dev/null & }}; "
                f"for i in $(/usr/bin/seq 1 50); do {inside} /usr/bin/ip link show {TAP} > /dev/null 2>&1 && break; "
                f"/usr/bin/sleep 0.1; done; {inside} /usr/bin/bash -c {shlex.quote(TAP_CONFIG)} || "
                f"{{ /usr/bin/tail -5 {UPLINK_LOG}; exit 1; }}")
    links = (f"links=\"$({inside} /usr/bin/ip -o link show)\" || "
             "{ echo \"cannot list the box user's links: $links\"; exit 1; }; ")
    return (f"for p in $(/usr/bin/pgrep -u {NET_UID}); do [ \"$p\" = {netns_pid} ] || kill -KILL \"$p\"; done; "
            f"for i in $(/usr/bin/seq 1 50); do {links}"
            f"echo \"$links\" | /usr/bin/grep -q ' {TAP}[:@]' || break; /usr/bin/sleep 0.1; done; {links}"
            f"echo \"$links\" | /usr/bin/grep -q ' {TAP}[:@]' && {{ echo '{TAP} is still there'; exit 1; }}; "
            f"left=\"$(/usr/bin/pgrep -u {NET_UID})\"; "
            f"[ \"$left\" = {netns_pid} ] || {{ echo \"NET_UID processes left: $left\"; exit 1; }}; "
            f"fds=\"$(/usr/bin/ls /proc/{netns_pid}/fd)\"; [ \"$(echo $fds)\" = '0 1 2' ] || "
            f"{{ echo \"the holder holds fds $(echo $fds)\"; exit 1; }}; "
            f"{PYTHON} -I -S -c {shlex.quote(SAME_NETNS_PY)} {netns_pid} {BOX_UID}")


class LinuxBox(Box):
    """A provider's machine (gVisor, or a VM) hardened into a box and driven like a DockerBox."""

    runner = "linux"
    detach = "/usr/bin/setsid /usr/bin/nohup"
    read_timeout_s = READ_TIMEOUT_S

    def __init__(self, machine: Machine, *, limits: BoxLimits = BoxLimits(), display: bool = False,
                 audio: bool = False, toolchain: bool = False, log: Callable[[str], None] = print) -> None:
        if machine.runtime not in RUNTIMES:
            raise ValueError(f"runtime must be one of {RUNTIMES}, got {machine.runtime!r}")
        self.machine = machine
        self.xvfb_pid: int | None = None
        self.limits = limits
        self.runner = f"{machine.provider}-{machine.runtime}"
        self.display = DISPLAY if display else None
        self.audio = audio
        self.toolchain = toolchain
        self.image = machine.image
        self.log = log
        self.started = False
        self.start_s: float | None = None
        self.network_enabled = True
        self.netns_pid: int | None = None  # gVisor: the holder of the box user's network namespace
        self.gpu_driver: str | None = None  # GPU boxes: the driver version nvidia-smi printed, e.g. 610.57.04
        self.display_netns_pid: int | None = None  # display and audio boxes: the holder of the harness's namespace
        self.pulse_pid: int | None = None  # audio boxes: pickfit's PulseAudio server

    # The machine says how it isolates and whether it has a card; the box only reads them.

    @property
    def runtime(self) -> str:
        return self.machine.runtime

    @runtime.setter
    def runtime(self, value: str) -> None:
        self.machine.runtime = value

    @property
    def gpu(self) -> str | None:  # type: ignore[override]
        return self.machine.gpu

    @gpu.setter
    def gpu(self, value: str | None) -> None:
        self.machine.gpu = value

    # -- lifecycle

    def start(self) -> None:
        if self.started:
            return
        began = time.monotonic()
        self.machine.start()
        self.image = self.machine.image
        self.started = True
        steps: list[tuple[str, ExecResult]] = []
        if self.runtime == "vm":
            steps.append(("VM hardening", self._exec_raw(["/usr/bin/bash", "-c", VM_HARDEN], 60, as_root=True,
                                                         stdin=NO_VSOCK_SOURCE.encode())))
        else:  # before the box user runs anything: it never has the box's own network
            netns = self._exec_raw(["/usr/bin/bash", "-c", netns_script()], 60, as_root=True)
            pid = next((line.split()[1] for line in netns.stdout.splitlines() if line.startswith("netns_pid ")), "")
            self.netns_pid = int(pid) if pid.isdigit() else None
            steps.append(("the box user's network namespace", netns))
            self._fail_on(steps, missing=self.netns_pid is None)
            steps.append(("the network uplink", self._uplink(True)))
        self._fail_on(steps)
        steps.append(("box setup", self._exec_raw(["/usr/bin/mkdir", "-p", BOX_WORKDIR, f"{BOX_HOME}/.local/bin"], 60,
                                                  as_root=True)))
        steps.append(("box setup", self._exec_raw(["/usr/bin/chown", "-R", f"{BOX_UID}:{BOX_UID}", BOX_HOME], 60,
                                                  as_root=True)))
        if self.gpu:  # the card the provider attached, as its driver names it; none answering is a failed start
            card = self._exec_raw(["/usr/bin/bash", "-c", GPU_NAME], 60, as_root=True)
            steps.append(("the GPU", card))
            first = next((line.split(",") for line in card.stdout.splitlines() if line.strip()), [""])
            self.gpu_name = first[0].strip() or None
            self.gpu_driver = first[1].strip() if len(first) > 1 else None
            self._fail_on(steps, missing=not self.gpu_name)
        if self.display or self.audio:  # the harness's own network namespace, loopback only
            held = self._exec_raw(["/usr/bin/bash", "-c", display_netns_script(self.runtime)], 60, as_root=True)
            pid = next((line.split()[1] for line in held.stdout.splitlines() if line.startswith("netns_pid ")), "")
            self.display_netns_pid = int(pid) if pid.isdigit() else None
            steps.append(("the display's network namespace", held))
            self._fail_on(steps, missing=self.display_netns_pid is None)
        if self.display:  # root starts it as DISPLAY_UID: the box user can draw on it, not kill or replace it
            script = xvfb_script(tuple(self.seccomp()), tuple(self.display_enter()))
            xvfb = self._exec_raw(["/usr/bin/bash", "-c", script], 60, as_root=True)
            steps.append(("the virtual display", xvfb))
            pid = next((line.split()[1] for line in xvfb.stdout.splitlines() if line.startswith("xvfb_pid ")), "")
            self.xvfb_pid = int(pid) if pid.isdigit() else None
            self._fail_on(steps, missing=self.xvfb_pid is None)
            bus = self._exec_raw(["/usr/bin/bash", "-c", SYSTEM_BUS], 30, as_root=True,
                                 stdin=SYSTEM_BUS_CONF_SOURCE.encode())
            steps.append(("the system bus", bus))
            self._fail_on(steps, missing="system_bus_up" not in bus.stdout)
            if self.runtime == "gvisor":
                steps.append(("flatpak's bubblewrap", self._exec_raw(["/usr/bin/bash", "-c", INSTALL_BWRAP_SHIM], 30,
                                                                     as_root=True, stdin=BWRAP_SHIM_SOURCE.encode())))
        if self.audio:  # root starts it as DISPLAY_UID: the box user records from it, cannot reconfigure or stop it
            drop = (*self.display_enter(), *_drop_to(DISPLAY_UID), *self.seccomp(), "/usr/bin/env", "-i",
                    f"PATH={HARNESS_PATH}", f"HOME={EVIDENCE_DIR}", "LANG=C.UTF-8")
            pulse = self._exec_raw(["/usr/bin/bash", "-c", pulse_script(drop)], 60, as_root=True)
            steps.append(("the simulated microphone", pulse))
            pid = next((line.split()[1] for line in pulse.stdout.splitlines() if line.startswith("pulse_pid ")), "")
            self.pulse_pid = int(pid) if pid.isdigit() else None
            self._fail_on(steps, missing=self.pulse_pid is None)
        if self.display and self.gpu:  # OpenGL on the card for Flatpak apps (VGL_SETUP)
            steps.append(("VirtualGL for Flatpak apps", self._exec_raw(["/usr/bin/bash", "-c", VGL_SETUP], 30,
                                                                      as_root=True, stdin=VGL_OVERRIDE.encode())))
        self._fail_on(steps, missing=bool(self.display and self.xvfb_pid is None))
        self.start_s = round(time.monotonic() - began, 2)

    def _fail_on(self, steps: list[tuple[str, ExecResult]], *, missing: bool = False) -> None:
        """Close the box and raise if a setup step failed (or, with `missing`, if the last one gave nothing)."""
        failed = next(((what, r) for what, r in steps if r.exit_code != 0), None)
        if failed or missing:
            self.close()
            what, r = failed or steps[-1]
            raise BoxError(f"{what} failed: {(r.stdout + r.stderr).strip()[-500:]}")

    def close(self) -> None:
        if not self.started:
            return
        try:
            self.machine.close()
        except Exception as err:  # already gone; the provider's lifetime cap reaps it anyway
            self.log(f"{self.machine.provider} close: {type(err).__name__}: {err}")
        self.started = False

    def usd_per_second(self) -> float:
        return self.machine.usd_per_second()

    # -- commands and files

    def _require_started(self) -> None:
        if not self.started:
            raise BoxError("box is not started")

    def user_argv(self, command: str, timeout_s: int, cwd: str) -> list[str]:
        """argv that runs `command` as the box user with the limits (separate so tests can check it)."""
        lim = self.limits
        guard = (f"ulimit -u {lim.pids} -n {lim.nofile} -f {lim.home_mb * 1024} && cd {shlex.quote(cwd)} && "
                 f"exec /usr/bin/timeout -s KILL {timeout_s} /usr/bin/bash -c {shlex.quote(command)}")
        env = [f"{key}={value}" for key, value in BOX_ENV.items()]
        if self.display and self.runtime == "gvisor":
            env.append(f"FLATPAK_BWRAP={BWRAP_SHIM}")
        if self.audio:
            env.append(f"PULSE_SERVER={PULSE_SERVER}")
        if self.display and self.gpu and self.gpu_driver:  # OpenGL on the card (gl_env)
            env += gl_env(self.gpu_driver)
        return [*self.enter(), *_drop_to(BOX_UID), *self.seccomp(), "/usr/bin/env", "-i", *env, "/usr/bin/bash", "-c",
                guard]

    def seccomp(self) -> list[str]:
        """The argv prefix that runs a command under the no-vsock, no-io_uring filter (a VM box; gVisor has
        neither vsock nor these host-kernel paths)."""
        return [PYTHON, "-I", "-S", NO_VSOCK] if self.runtime == "vm" else []

    def enter(self) -> list[str]:
        """The argv prefix that puts a command in the box user's network namespace, as NET_UID (root there) until
        the next setpriv (a gVisor box; a VM closes DNS with nftables). Fails closed before the namespace exists."""
        if self.runtime != "gvisor":
            return []
        if self.netns_pid is None:
            raise BoxError("the box user's network namespace is not set up")
        return [*_drop_to(NET_UID), "/usr/bin/nsenter", f"--target={self.netns_pid}", "--user", "--net", "--"]

    def display_enter(self) -> list[str]:
        """Root's argv prefix into the display's network namespace (loopback only), before it drops to the display
        uid. Fails closed before the namespace exists."""
        if self.display_netns_pid is None:
            raise BoxError("the display's network namespace is not set up")
        user = ["--user"] if self.runtime == "gvisor" else []
        return ["/usr/bin/nsenter", f"--target={self.display_netns_pid}", *user, "--net", "--"]

    def _uplink(self, enabled: bool) -> ExecResult:
        assert self.netns_pid is not None
        return self._exec_raw(["/usr/bin/bash", "-c", uplink_script(self.netns_pid, enabled)], 30, as_root=True)

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        """Run argv for pickfit itself: as root, or as `as_uid` with an empty environment (no box-user PATH)."""
        self._require_started()
        if as_uid == BOX_UID:
            raise ValueError("the box user's commands go through exec (its network namespace and limits)")
        if as_uid is not None:  # in the display's namespace: no network at all, and not the box user's
            argv = [*self.display_enter(), *_drop_to(as_uid), *self.seccomp(), "/usr/bin/env", "-i",
                    f"PATH={HARNESS_PATH}", f"HOME={EVIDENCE_DIR}", "LANG=C.UTF-8", *argv]
        return self._exec_raw(argv, timeout_s, stdin=stdin, as_root=True)

    def harness_read(self, path: str, max_bytes: int) -> bytes:
        """A file as root reads it (pickfit's evidence), up to max_bytes; BoxError if it cannot."""
        self._require_started()
        timeout_s = self.read_timeout_s
        code, out, err, gave_up = self._run(["/usr/bin/head", "-c", str(int(max_bytes)), "--", path],
                                            timeout_s, head=max_bytes, tail=0)
        if code != 0 or gave_up:
            raise BoxError(f"cannot read {path}: {err.text().strip()[-300:] or 'timed out'}")
        return bytes(out.head)

    def _run(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None,
             head: int = OUTPUT_HEAD_BYTES, tail: int = OUTPUT_TAIL_BYTES) -> tuple[int, _Capture, _Capture, bool]:
        """Run argv as root in the machine; (exit code, stdout, stderr, host gave up). See Machine.run."""
        return self.machine.run(argv, timeout_s, stdin=stdin, head=head, tail=tail)

    def _exec_raw(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None,
                  as_root: bool = False) -> ExecResult:
        """Run argv in the sandbox, keeping the head and tail of its output."""
        began = time.monotonic()
        code, out, err, gave_up = self._run(argv, timeout_s, stdin=stdin)
        seconds = round(time.monotonic() - began, 2)
        stderr = err.text()
        if gave_up:
            stderr += (f"\n[pickfit stopped waiting after {seconds:.0f}s: the command did not exit, or something "
                       "it started still holds its output open; start servers and daemons with run_background]")
        return ExecResult(command=" ".join(argv) if as_root else argv[-1], exit_code=code,
                          stdout=out.text(), stderr=stderr, seconds=seconds, timed_out=gave_up,
                          truncated=bool(out.dropped or err.dropped))

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self._require_started()
        timeout_s = max(1, min(int(timeout_s), self.limits.max_command_s))
        result = self._exec_raw(self.user_argv(command, timeout_s, cwd or self.workdir), timeout_s)
        # `timeout -s KILL` exits 137; Modal's own backstop reports -1 or 124-ish codes.
        timed_out = result.timed_out or (result.exit_code in (124, 137, -1) and result.seconds >= timeout_s - 0.5)
        return ExecResult(command=command, exit_code=result.exit_code, stdout=result.stdout,
                          stderr=result.stderr, seconds=result.seconds, timed_out=timed_out,
                          truncated=result.truncated)

    def write_file(self, path: str, content: str | bytes) -> None:
        self._require_started()
        data = content.encode("utf-8") if isinstance(content, str) else content
        # The path is passed as $1, never spliced into the script.
        script = '/usr/bin/mkdir -p -- "$(/usr/bin/dirname -- "$1")" && /usr/bin/cat > "$1"'
        argv = self.user_argv(f"/usr/bin/bash -c {shlex.quote(script)} sh {shlex.quote(path)}", 60, self.workdir)
        result = self._exec_raw(argv, 60, stdin=data)
        if result.exit_code != 0:
            raise BoxError(f"cannot write {path}: {result.stderr.strip()[-300:]}")

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        self._require_started()
        timeout_s = self.read_timeout_s
        argv = self.user_argv(f"/usr/bin/head -c {int(max_bytes)} -- {shlex.quote(path)}", timeout_s, self.workdir)
        code, out, err, gave_up = self._run(argv, timeout_s, head=max_bytes, tail=0)
        if code != 0 or gave_up:
            raise BoxError(f"cannot read {path}: {err.text().strip()[-300:] or 'timed out'}")
        return bytes(out.head)

    def set_network(self, enabled: bool) -> None:
        self._require_started()
        if enabled == self.network_enabled:
            return
        if not enabled and self.runtime == "gvisor":  # the box user's only way out, DNS included
            self._check_rule(self._uplink(False), "cutting the network uplink")
        self.machine.set_egress(enabled)  # the provider's own cut, outside the machine; BoxError if it was not made
        self.network_enabled = enabled
        if self.runtime == "vm":  # a provider's resolver may answer with egress closed (Modal's does); root closes it
            rule = self._exec_raw(["/usr/bin/bash", "-c", DNS_UNBLOCK if enabled else DNS_BLOCK], 30, as_root=True)
            self._check_rule(rule, "offline DNS rule")
        elif enabled:
            self._check_rule(self._uplink(True), "the network uplink")

    @staticmethod
    def _check_rule(result: ExecResult, what: str) -> None:
        if result.exit_code != 0:
            raise BoxError(f"{what} failed: {(result.stdout + result.stderr).strip()[-300:]}")
