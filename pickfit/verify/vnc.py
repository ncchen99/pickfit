"""A small RFB (VNC) client: screenshots and input for a tart VM's display, from the host.

`tart run --vnc-experimental` serves the VM's framebuffer with Virtualization.framework's own VNC server on
the host (measured 2026-11-01: RFB 3.8, VNC authentication only, a random password printed once in the run
log). Nothing runs in the guest for it: no Screen Sharing, no Screen Recording or Accessibility permission,
and an app in the guest cannot hand pickfit a different picture than the one on its display. The guest
cannot reach the port either: softnet blocks the host (tart_box.HOST_BLOCK).

Written from RFC 6143 (RFB 3.8) and FIPS 46-3 (DES, which VNC authentication uses); no third-party code.
Only the Raw encoding is asked for: the server is on this Mac, so a 1280x800 frame (4 MB) costs nothing.
"""

from __future__ import annotations

import io
import socket
import struct
import time
from typing import Any

PROTOCOL = b"RFB 003.008\n"
SEC_NONE, SEC_VNC = 1, 2
ENC_RAW, ENC_DESKTOP_SIZE = 0, -223
BUTTON_LEFT, BUTTON_RIGHT = 1, 4
MAX_SIDE = 8192  # a frame bigger than this is not a display pickfit configured

# X11 keysyms (RFB key events carry them). Names follow xdotool, with a few aliases.
KEYSYMS: dict[str, int] = {
    "return": 0xFF0D, "enter": 0xFF0D, "tab": 0xFF09, "escape": 0xFF1B, "esc": 0xFF1B, "backspace": 0xFF08,
    "delete": 0xFFFF, "del": 0xFFFF, "home": 0xFF50, "left": 0xFF51, "up": 0xFF52, "right": 0xFF53,
    "down": 0xFF54, "page_up": 0xFF55, "pageup": 0xFF55, "prior": 0xFF55, "page_down": 0xFF56,
    "pagedown": 0xFF56, "next": 0xFF56, "end": 0xFF57, "insert": 0xFF63, "space": 0x20,
    **{f"f{n}": 0xFFBE + n - 1 for n in range(1, 13)},
}
# Virtualization.framework's server maps Alt to the Mac's Command key and Meta to Option; Super and Hyper do
# nothing (measured 2026-11-01 with modifier+Backspace in TextEdit). Names are the Mac's keys.
COMMAND, OPTION = 0xFFE9, 0xFFE7
MODIFIERS: dict[str, int] = {
    "shift": 0xFFE1, "ctrl": 0xFFE3, "control": 0xFFE3, "alt": OPTION, "option": OPTION, "opt": OPTION,
    "cmd": COMMAND, "command": COMMAND, "meta": COMMAND, "super": COMMAND, "win": COMMAND,
}
SHIFTED = set('~!@#$%^&*()_+{}|:"<>?') | {chr(c) for c in range(ord("A"), ord("Z") + 1)}


class VncError(Exception):
    """The VNC server refused, closed or sent something this client does not understand."""


# ---------------------------------------------------------------- DES (FIPS 46-3), encrypt only

_IP = (58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6,
       64, 56, 48, 40, 32, 24, 16, 8, 57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3,
       61, 53, 45, 37, 29, 21, 13, 5, 63, 55, 47, 39, 31, 23, 15, 7)
_FP = (40, 8, 48, 16, 56, 24, 64, 32, 39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30,
       37, 5, 45, 13, 53, 21, 61, 29, 36, 4, 44, 12, 52, 20, 60, 28, 35, 3, 43, 11, 51, 19, 59, 27,
       34, 2, 42, 10, 50, 18, 58, 26, 33, 1, 41, 9, 49, 17, 57, 25)
_E = (32, 1, 2, 3, 4, 5, 4, 5, 6, 7, 8, 9, 8, 9, 10, 11, 12, 13, 12, 13, 14, 15, 16, 17,
      16, 17, 18, 19, 20, 21, 20, 21, 22, 23, 24, 25, 24, 25, 26, 27, 28, 29, 28, 29, 30, 31, 32, 1)
_P = (16, 7, 20, 21, 29, 12, 28, 17, 1, 15, 23, 26, 5, 18, 31, 10,
      2, 8, 24, 14, 32, 27, 3, 9, 19, 13, 30, 6, 22, 11, 4, 25)
_PC1 = (57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 27,
        19, 11, 3, 60, 52, 44, 36, 63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22,
        14, 6, 61, 53, 45, 37, 29, 21, 13, 5, 28, 20, 12, 4)
_PC2 = (14, 17, 11, 24, 1, 5, 3, 28, 15, 6, 21, 10, 23, 19, 12, 4, 26, 8, 16, 7, 27, 20, 13, 2,
        41, 52, 31, 37, 47, 55, 30, 40, 51, 45, 33, 48, 44, 49, 39, 56, 34, 53, 46, 42, 50, 36, 29, 32)
_SHIFTS = (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1)
_S = (
    (14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7, 0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
     4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0, 15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13),
    (15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10, 3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5,
     0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15, 13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9),
    (10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8, 13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
     13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7, 1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12),
    (7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15, 13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
     10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4, 3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14),
    (2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9, 14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
     4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14, 11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3),
    (12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11, 10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
     9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6, 4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13),
    (4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1, 13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
     1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2, 6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12),
    (13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7, 1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
     7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8, 2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11),
)


def _permute(value: int, table: tuple[int, ...], bits: int) -> int:
    out = 0
    for pos in table:
        out = (out << 1) | ((value >> (bits - pos)) & 1)
    return out


def _subkeys(key: bytes) -> list[int]:
    cd = _permute(int.from_bytes(key, "big"), _PC1, 64)
    c, d = cd >> 28, cd & 0xFFFFFFF
    keys = []
    for shift in _SHIFTS:
        c = ((c << shift) | (c >> (28 - shift))) & 0xFFFFFFF
        d = ((d << shift) | (d >> (28 - shift))) & 0xFFFFFFF
        keys.append(_permute((c << 28) | d, _PC2, 56))
    return keys


def des_encrypt(key: bytes, block: bytes) -> bytes:
    """One 8-byte block, DES-ECB."""
    if len(key) != 8 or len(block) != 8:
        raise ValueError("DES takes an 8-byte key and 8-byte blocks")
    bits = _permute(int.from_bytes(block, "big"), _IP, 64)
    left, right = bits >> 32, bits & 0xFFFFFFFF
    for sub in _subkeys(key):
        x = _permute(right, _E, 32) ^ sub
        out = 0
        for i in range(8):
            six = (x >> (42 - 6 * i)) & 0x3F
            row, col = ((six >> 4) & 2) | (six & 1), (six >> 1) & 0xF  # outer bits pick the row
            out = (out << 4) | _S[i][row * 16 + col]
        left, right = right, left ^ _permute(out, _P, 32)
    return _permute((right << 32) | left, _FP, 64).to_bytes(8, "big")


def vnc_response(password: str, challenge: bytes) -> bytes:
    """VNC authentication: the challenge DES-encrypted with the password's first 8 bytes, each bit-reversed."""
    key = bytes(int(f"{b:08b}"[::-1], 2) for b in password.encode("latin-1", "replace")[:8].ljust(8, b"\0"))
    return des_encrypt(key, challenge[:8]) + des_encrypt(key, challenge[8:16])


# ---------------------------------------------------------------- the client


def parse_url(url: str) -> tuple[str, int, str]:
    """`vnc://:password@host:port` (what tart prints) -> (host, port, password)."""
    rest = url.removeprefix("vnc://")
    cred, _, hostport = rest.rpartition("@")
    password = cred.split(":", 1)[1] if ":" in cred else cred
    host, _, port = hostport.rpartition(":")
    if not host or not port.isdigit():
        raise VncError(f"not a VNC address: {url.split('@')[-1]!r}")
    return host.strip("[]"), int(port), password


class VncClient:
    """One RFB connection: full-frame screenshots, pointer clicks and key events."""

    def __init__(self, host: str, port: int, password: str, *, timeout_s: float = 20) -> None:
        self.host, self.port, self.password, self.timeout_s = host, port, password, timeout_s
        self.sock: socket.socket | None = None
        self.width = self.height = 0
        self.name = ""
        self.frame = bytearray()
        self.pointer = (0, 0)

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> VncClient:
        host, port, password = parse_url(url)
        return cls(host, port, password, **kwargs)

    # -- wire

    def _recv(self, n: int) -> bytes:
        assert self.sock is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(min(n - len(buf), 1 << 20))
            if not chunk:
                raise VncError("the VNC server closed the connection")
            buf += chunk
        return bytes(buf)

    def _send(self, data: bytes) -> None:
        if self.sock is None:
            self.connect()
        assert self.sock is not None
        try:
            self.sock.sendall(data)
        except OSError as err:
            raise VncError(f"VNC send failed: {err}") from err

    def connect(self) -> VncClient:
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
            self._handshake()
        except (OSError, struct.error) as err:
            self.close()
            raise VncError(f"VNC connection to {self.host}:{self.port} failed: {err}") from err
        except VncError:
            self.close()
            raise
        return self

    def _handshake(self) -> None:
        version = self._recv(12)
        if not version.startswith(b"RFB 003."):
            raise VncError(f"not an RFB server: {version!r}")
        self._send(PROTOCOL)
        count = self._recv(1)[0]
        if count == 0:
            reason = self._recv(struct.unpack(">I", self._recv(4))[0])
            raise VncError(f"the VNC server refused: {reason.decode(errors='replace')}")
        types = self._recv(count)
        if SEC_VNC in types:
            self._send(bytes([SEC_VNC]))
            self._send(vnc_response(self.password, self._recv(16)))
        elif SEC_NONE in types:
            self._send(bytes([SEC_NONE]))
        else:
            raise VncError(f"no supported security type (server offers {list(types)})")
        if struct.unpack(">I", self._recv(4))[0] != 0:
            raise VncError("VNC authentication failed")
        self._send(b"\x01")  # ClientInit: shared
        self.width, self.height = struct.unpack(">HH", self._recv(4))
        self._recv(16)  # the server's pixel format; ours replaces it
        self.name = self._recv(struct.unpack(">I", self._recv(4))[0]).decode(errors="replace")
        # 32 bpp, depth 24, little endian, true colour, 8 bits per channel: bytes arrive as B, G, R, X.
        self._send(struct.pack(">B3xBBBBHHHBBB3x", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
        self._send(struct.pack(">BxHii", 2, 2, ENC_RAW, ENC_DESKTOP_SIZE))
        self._check_size(self.width, self.height)
        self.frame = bytearray(self.width * self.height * 4)

    def _check_size(self, width: int, height: int) -> None:
        if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
            raise VncError(f"the display reports an odd size {width}x{height}")

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def __enter__(self) -> VncClient:
        return self.connect() if self.sock is None else self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- framebuffer

    def _read_update(self) -> None:
        """Read server messages until one FramebufferUpdate has been applied."""
        while True:
            kind = self._recv(1)[0]
            if kind == 0:
                self._recv(1)
                for _ in range(struct.unpack(">H", self._recv(2))[0]):
                    x, y, w, h, enc = struct.unpack(">HHHHi", self._recv(12))
                    if enc == ENC_RAW:
                        self._blit(x, y, w, h, self._recv(w * h * 4))
                    elif enc == ENC_DESKTOP_SIZE:
                        self._check_size(w, h)
                        self.width, self.height = w, h
                        self.frame = bytearray(w * h * 4)
                    else:
                        raise VncError(f"the server sent encoding {enc}, which was not asked for")
                return
            if kind == 1:  # SetColourMapEntries (not used with true colour, but legal)
                _, count = struct.unpack(">xHH", self._recv(5))
                self._recv(count * 6)
            elif kind == 2:  # Bell
                continue
            elif kind == 3:  # ServerCutText
                self._recv(3)
                self._recv(struct.unpack(">I", self._recv(4))[0])
            else:
                raise VncError(f"unknown server message type {kind}")

    def _blit(self, x: int, y: int, w: int, h: int, data: bytes) -> None:
        if x + w > self.width or y + h > self.height:
            raise VncError(f"a rectangle {w}x{h}+{x}+{y} falls outside the {self.width}x{self.height} display")
        row = w * 4
        for i in range(h):
            start = ((y + i) * self.width + x) * 4
            self.frame[start:start + row] = data[i * row:(i + 1) * row]

    def _frame(self) -> bytes:
        self._send(struct.pack(">BBHHHH", 3, 0, 0, 0, self.width, self.height))
        self._read_update()
        return bytes(self.frame)

    def capture(self) -> tuple[int, int, bytes]:
        """The whole display now, as (width, height, BGRX bytes), from the first frame of a new connection.

        Virtualization.framework's server treats every request after a connection's first like an
        incremental one: it answers only once the screen changes, and on a connection that sat idle it first
        sends a frame from before the change (measured 11/1: TextEdit open for 8 s, the first frame on the
        old connection without it, a new connection's first frame with it; a second request on a quiet
        screen got no answer in 20 s). A new connection's first frame is the screen as it is now.
        """
        self.close()
        self.connect()
        try:
            self._frame()
        except (OSError, struct.error) as err:
            raise VncError(f"VNC screenshot failed: {err}") from err
        finally:
            self.close()  # input reconnects; nothing is left waiting on this one
        return self.width, self.height, bytes(self.frame)

    def screenshot(self) -> bytes:
        """The whole display as PNG bytes."""
        from PIL import Image

        width, height, data = self.capture()
        out = io.BytesIO()
        Image.frombytes("RGB", (width, height), data, "raw", "BGRX").save(out, "PNG")
        return out.getvalue()

    # -- input

    def _pointer(self, x: int, y: int, mask: int) -> None:
        x, y = max(0, min(int(x), self.width - 1)), max(0, min(int(y), self.height - 1))
        self._send(struct.pack(">BBHH", 5, mask, x, y))
        self.pointer = (x, y)

    def move(self, x: int, y: int) -> None:
        self._pointer(x, y, 0)

    def click(self, x: int, y: int, *, button: str = "left", count: int = 1, pause_s: float = 0.06) -> None:
        mask = BUTTON_RIGHT if button == "right" else BUTTON_LEFT
        self._pointer(x, y, 0)
        time.sleep(pause_s)
        for _ in range(max(1, count)):
            self._pointer(x, y, mask)
            time.sleep(pause_s)
            self._pointer(x, y, 0)
            time.sleep(pause_s)

    def _key(self, keysym: int, down: bool) -> None:
        self._send(struct.pack(">BBxxI", 4, 1 if down else 0, keysym))

    def tap(self, keysym: int, *, mods: tuple[int, ...] = (), pause_s: float = 0.03) -> None:
        for mod in mods:
            self._key(mod, True)
        self._key(keysym, True)
        time.sleep(pause_s)
        self._key(keysym, False)
        for mod in reversed(mods):
            self._key(mod, False)
        time.sleep(pause_s)

    def type_text(self, text: str, *, pause_s: float = 0.03) -> None:
        """Type characters as a US keyboard would (shift held for capitals and shifted symbols)."""
        for ch in text:
            if ch == "\n":
                self.tap(KEYSYMS["return"], pause_s=pause_s)
            elif ch == "\t":
                self.tap(KEYSYMS["tab"], pause_s=pause_s)
            else:
                cp = ord(ch)
                keysym = cp if 0x20 <= cp <= 0xFF else 0x01000000 | cp
                self.tap(keysym, mods=(MODIFIERS["shift"],) if ch in SHIFTED else (), pause_s=pause_s)

    def key(self, name: str) -> None:
        """A key or chord by name: `Return`, `Tab`, `cmd+s`, `ctrl+shift+t`, `a`."""
        keysym, mods = parse_key(name)
        self.tap(keysym, mods=mods)


def parse_key(name: str) -> tuple[int, tuple[int, ...]]:
    """`cmd+shift+s` -> (keysym of s, (Meta, Shift)); raises ValueError for a name it does not know."""
    parts = [p for p in name.strip().split("+") if p] or ([name] if name else [])
    if not parts:
        raise ValueError("an empty key name")
    *mods, last = parts
    try:
        mod_syms = tuple(MODIFIERS[m.strip().lower()] for m in mods)
    except KeyError as err:
        raise ValueError(f"unknown modifier {err.args[0]!r} in {name!r}") from None
    low = last.strip().lower()
    if low in KEYSYMS:
        return KEYSYMS[low], mod_syms
    if low in MODIFIERS:
        return MODIFIERS[low], mod_syms
    if len(last) == 1 and 0x20 <= ord(last) <= 0x7E:
        return ord(last.lower()) if mod_syms else ord(last), mod_syms
    raise ValueError(f"unknown key {last!r} in {name!r}")
