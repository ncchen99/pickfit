"""The RFB client against a fake VNC server on localhost: DES, authentication, frames and input."""

from __future__ import annotations

import io
import socket
import struct
import threading
from collections.abc import Iterator

import pytest
from PIL import Image

from pickfit.verify.vnc import COMMAND, MODIFIERS, OPTION, VncClient, VncError, des_encrypt, parse_key, parse_url, \
    vnc_response

PASSWORD = "cross-net-super-network"
CHALLENGE = bytes(range(16))
W, H = 4, 2


def test_des_matches_the_fips_example():
    assert des_encrypt(bytes.fromhex("133457799BBCDFF1"), bytes.fromhex("0123456789ABCDEF")).hex() == \
        "85e813540f0ab405"


def test_vnc_response_uses_the_first_eight_bytes_bit_reversed():
    # From LibreSSL: openssl enc -des-ecb -nopad, key = "cross-ne" with each byte's bits reversed.
    assert vnc_response(PASSWORD, CHALLENGE).hex() == "b54b82a4e9184b3e6e5618e6c60fdd8a"
    assert vnc_response("cross-ne", CHALLENGE) == vnc_response(PASSWORD, CHALLENGE)


def test_parse_url_reads_what_tart_prints():
    assert parse_url("vnc://:cross-net-super-network@127.0.0.1:54161") == ("127.0.0.1", 54161, PASSWORD)
    with pytest.raises(VncError):
        parse_url("vnc://:pw@127.0.0.1")


def test_keys_name_the_macs_modifiers():
    assert parse_key("Return") == (0xFF0D, ())
    assert parse_key("cmd+s") == (ord("s"), (COMMAND,))
    assert parse_key("ctrl+shift+T") == (ord("t"), (MODIFIERS["ctrl"], MODIFIERS["shift"]))
    assert parse_key("option+Left") == (0xFF51, (OPTION,))
    assert parse_key("super+q") == (ord("q"), (COMMAND,))  # Linux names reach the Mac's Command key
    assert parse_key("A") == (ord("A"), ())
    for bad in ("", "hyper+a", "cmd+nosuchkey"):
        with pytest.raises(ValueError):
            parse_key(bad)


class FakeServer:
    """One RFB 3.8 client at a time: VNC auth, then frames on request; records key and pointer events."""

    def __init__(self, *, password: str = PASSWORD, extra_before_frame: bytes = b"\x02",
                 encoding: int = 0) -> None:
        self.password, self.extra, self.encoding = password, extra_before_frame, encoding
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.events: list[tuple] = []
        self.pixel_format: bytes | None = None
        self.encodings: list[int] = []
        self.connections = 0
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def _recv(self, conn: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise EOFError
            buf += chunk
        return buf

    def serve(self) -> None:
        while True:  # a screenshot takes a connection of its own
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            self.serve_one(conn)

    def serve_one(self, conn: socket.socket) -> None:
        try:
            conn.sendall(b"RFB 003.008\n")
            self._recv(conn, 12)
            conn.sendall(bytes([1, 2]))
            assert self._recv(conn, 1) == b"\x02"
            conn.sendall(CHALLENGE)
            ok = self._recv(conn, 16) == vnc_response(self.password, CHALLENGE)
            conn.sendall(struct.pack(">I", 0 if ok else 1))
            if not ok:
                return
            self._recv(conn, 1)  # ClientInit
            name = b"Virtualization"
            conn.sendall(struct.pack(">HH", W, H) + bytes(16) + struct.pack(">I", len(name)) + name)
            while True:
                kind = self._recv(conn, 1)[0]
                if kind == 0:
                    self.pixel_format = self._recv(conn, 19)[3:]
                elif kind == 2:
                    (n,) = struct.unpack(">xH", self._recv(conn, 3))
                    self.encodings = list(struct.unpack(f">{n}i", self._recv(conn, 4 * n)))
                elif kind == 3:
                    self._recv(conn, 9)
                    pixels = b"".join(bytes([0, 0, 255, 0]) if i % 2 == 0 else bytes([255, 0, 0, 0])
                                      for i in range(W * H))  # BGRX: red, blue, red, blue, ...
                    conn.sendall(self.extra + struct.pack(">BxH", 0, 1)
                                 + struct.pack(">HHHHi", 0, 0, W, H, self.encoding) + pixels)
                elif kind == 4:
                    down, sym = struct.unpack(">BxxI", self._recv(conn, 7))
                    self.events.append(("key", down, sym))
                elif kind == 5:
                    mask, x, y = struct.unpack(">BHH", self._recv(conn, 5))
                    self.events.append(("pointer", mask, x, y))
        except (EOFError, OSError, AssertionError):
            pass
        finally:
            conn.close()


@pytest.fixture
def server() -> Iterator[FakeServer]:
    srv = FakeServer()
    yield srv
    srv.sock.close()


def _wait(srv: FakeServer, count: int) -> None:
    for _ in range(200):
        if len(srv.events) >= count:
            return
        threading.Event().wait(0.01)


def test_screenshot_is_the_frame_as_png(server: FakeServer):
    client = VncClient("127.0.0.1", server.port, PASSWORD).connect()
    assert (client.width, client.height, client.name) == (W, H, "Virtualization")
    image = Image.open(io.BytesIO(client.screenshot()))
    assert image.size == (W, H) and image.getpixel((0, 0)) == (255, 0, 0) and image.getpixel((1, 0)) == (0, 0, 255)
    assert server.pixel_format is not None and server.pixel_format[:4] == bytes([32, 24, 0, 1])  # 32 bpp, LE, true
    assert server.encodings == [0, -223]  # Raw, and DesktopSize
    client.screenshot()
    assert server.connections == 3  # each screenshot is a new connection's first frame
    client.close()


def test_input_reaches_the_server_as_key_and_pointer_events(server: FakeServer):
    client = VncClient("127.0.0.1", server.port, PASSWORD).connect()
    client.click(3, 1)
    client.type_text("a!")
    client.key("cmd+s")
    _wait(server, 3 + 2 + 4 + 4)
    pointer = [e for e in server.events if e[0] == "pointer"]
    assert pointer == [("pointer", 0, 3, 1), ("pointer", 1, 3, 1), ("pointer", 0, 3, 1)]
    keys = [e[1:] for e in server.events if e[0] == "key"]
    shift = MODIFIERS["shift"]
    assert keys == [(1, ord("a")), (0, ord("a")), (1, shift), (1, ord("!")), (0, ord("!")), (0, shift),
                    (1, COMMAND), (1, ord("s")), (0, ord("s")), (0, COMMAND)]
    client.close()


def test_a_wrong_password_fails():
    srv = FakeServer(password="other-password")
    with pytest.raises(VncError, match="authentication failed"):
        VncClient("127.0.0.1", srv.port, PASSWORD).connect()
    srv.sock.close()


def test_an_encoding_not_asked_for_fails():
    srv = FakeServer(encoding=16)  # ZRLE
    client = VncClient("127.0.0.1", srv.port, PASSWORD).connect()
    with pytest.raises(VncError, match="encoding 16"):
        client.capture()
    client.close()
    srv.sock.close()


def test_punctuation_keys_by_x_keysym_name():
    assert parse_key("ctrl+slash") == (ord("/"), (MODIFIERS["ctrl"],))
    assert parse_key("BackSpace") == (0xFF08, ()) and parse_key("Page_Down") == (0xFF56, ())


def test_scroll_sends_wheel_buttons(server: FakeServer):
    client = VncClient("127.0.0.1", server.port, PASSWORD).connect()
    client.scroll(10, 1, "down", notches=2)
    _wait(server, 5)
    assert [e for e in server.events if e[0] == "pointer"] == [
        ("pointer", 0, 3, 1), ("pointer", 16, 3, 1), ("pointer", 0, 3, 1), ("pointer", 16, 3, 1),
        ("pointer", 0, 3, 1)]  # x clamped to the 4-pixel-wide fake screen
    with pytest.raises(ValueError):
        client.scroll(1, 1, "sideways")
    client.close()


def test_the_display_waits_for_two_frames_that_agree(server: FakeServer):
    from pickfit.verify.gui_mac import VncDisplay

    display = VncDisplay(f"vnc://:{PASSWORD}@127.0.0.1:{server.port}")
    png = display.screenshot()
    assert Image.open(io.BytesIO(png)).size == (W, H) and (display.width, display.height) == (W, H)
    assert server.connections == 2  # the first frame, then one that agrees
    assert display.clipboard() is None  # no box, no pasteboard to read
    display.close()
