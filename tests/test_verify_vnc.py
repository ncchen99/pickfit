"""The RFB client against a fake VNC server on localhost: DES, authentication, frames and input."""

from __future__ import annotations

import io
import socket
import struct
import threading
from collections.abc import Iterator

import pytest
from PIL import Image

import zlib

from pickfit.verify.vnc import COMMAND, MODIFIERS, OPTION, WINDOWS_MODIFIERS, VncClient, VncError, des_encrypt, \
    parse_key, parse_url, vnc_response, vnc_stored_password

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
                 encoding: int = 0, zrle: bool = False) -> None:
        self.password, self.extra, self.encoding = password, extra_before_frame, encoding
        self.zrle = zrle  # answer in ZRLE when the client asks for it, as TightVNC does
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
        self.connections_frames = 0
        deflate = None
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
                    if self.zrle and 16 in self.encodings:  # one raw tile of CPIXELs, in the connection's zlib stream
                        deflate = deflate if self.connections_frames else zlib.compressobj()
                        self.connections_frames += 1
                        tile = b"\x00" + b"".join(pixels[i:i + 3] for i in range(0, len(pixels), 4))
                        data = deflate.compress(tile) + deflate.flush(zlib.Z_SYNC_FLUSH)
                        conn.sendall(self.extra + struct.pack(">BxH", 0, 1) + struct.pack(">HHHHi", 0, 0, W, H, 16)
                                     + struct.pack(">I", len(data)) + data)
                        continue
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


def test_the_displays_right_click_presses_the_right_button(server: FakeServer):
    from pickfit.verify.gui_mac import VncDisplay
    from pickfit.verify.vnc import BUTTON_RIGHT

    display = VncDisplay(f"vnc://:{PASSWORD}@127.0.0.1:{server.port}")
    display.right_click(2, 1)
    _wait(server, 3)
    assert [e for e in server.events if e[0] == "pointer"] == [
        ("pointer", 0, 2, 1), ("pointer", BUTTON_RIGHT, 2, 1), ("pointer", 0, 2, 1)]
    display.close()


def test_stored_password_is_the_well_known_one():
    # What a VNC server keeps for "password" (RealVNC's and TightVNC's registry value, quoted by every decoder).
    assert vnc_stored_password("password").hex() == "dbd83cfd727a1458"
    assert vnc_stored_password("passwordX") == vnc_stored_password("password")  # eight characters count


def test_windows_keys_name_windows_modifiers():
    assert parse_key("alt+F4", WINDOWS_MODIFIERS) == (0xFFC1, (0xFFE9,))  # Alt_L, not the Mac's Option (Meta_L)
    assert parse_key("win+r", WINDOWS_MODIFIERS) == (ord("r"), (0xFFEB,))
    assert parse_key("cmd+s", WINDOWS_MODIFIERS) == (ord("s"), (0xFFE3,))  # the Mac's name: Ctrl here
    assert parse_key("ctrl+plus", WINDOWS_MODIFIERS) == (ord("+"), (0xFFE3,)) and parse_key("Menu")[0] == 0xFF67


def _zrle_client(w: int, h: int) -> VncClient:
    client = VncClient("127.0.0.1", 1, "x", compress=True)
    client.width, client.height, client.frame = w, h, bytearray(w * h * 4)
    return client


def test_zrle_tiles_of_every_kind_decode():
    red, green, blue = b"\x00\x00\xff", b"\x00\xff\x00", b"\xff\x00\x00"  # CPIXELs: B, G, R
    px = {red: b"\x00\x00\xff\x00", green: b"\x00\xff\x00\x00", blue: b"\xff\x00\x00\x00"}
    cases = {
        "raw": (b"\x00" + red + green + blue + red, [red, green, blue, red]),
        "solid": (b"\x01" + green, [green] * 4),
        "palette": (b"\x02" + red + blue + bytes([0b01000000, 0b10000000]), [red, blue, blue, red]),
        "rle": (b"\x80" + red + b"\x02" + blue + b"\x00", [red, red, red, blue]),
        "palette rle": (bytes([130]) + green + red + bytes([0x80, 0x01, 0x01, 0x00]), [green, green, red, green]),
    }
    for name, (data, want) in cases.items():
        client = _zrle_client(2, 2)
        client._zrle(0, 0, 2, 2, data)
        assert bytes(client.frame) == b"".join(px[c] for c in want), name
    long_run = _zrle_client(70, 1)  # two tiles across; a run longer than 255 is 255s and the rest
    long_run.width = 70
    long_run._zrle(0, 0, 70, 1, b"\x80" + red + bytes([63]) + b"\x80" + green + bytes([5]))
    assert bytes(long_run.frame) == px[red] * 64 + px[green] * 6
    with pytest.raises(VncError, match="ended early"):
        _zrle_client(2, 2)._zrle(0, 0, 2, 2, b"\x00" + red)
    with pytest.raises(VncError, match="subencoding 17"):
        _zrle_client(2, 2)._zrle(0, 0, 2, 2, b"\x11")


def test_a_compressed_connection_asks_for_zrle_and_keeps_one_zlib_stream():
    srv = FakeServer(zrle=True)
    client = VncClient("127.0.0.1", srv.port, PASSWORD, compress=True).connect()
    first = client.frame_now()
    assert srv.encodings[0] == 16 and first[:2] == (W, H)
    assert client.frame_now() == first  # the second frame inflates in the same stream
    assert first[2][:4] == bytes([0, 0, 255, 0]) and srv.connections == 1  # one connection, kept
    client.close()
    plain = VncClient("127.0.0.1", srv.port, PASSWORD).connect()
    plain.frame_now()
    assert 16 not in srv.encodings  # not asked for, never sent
    plain.close()
    srv.sock.close()


def test_a_frame_and_a_pointer_move_carry_when_they_happened(server: FakeServer):
    import time

    client = VncClient("127.0.0.1", server.port, PASSWORD)
    assert client.answered_at == 0.0 and client.pointer_at == 0.0
    before = time.time()
    client.capture()  # the server rings the bell first; the frame's answer is what is stamped
    assert before <= client.answered_at <= time.time()
    client.click(3, 1)  # a recording draws the pointer there only on frames due after this (record.VncRecorder)
    moved = client.pointer_at
    assert client.answered_at <= moved <= time.time()
    client.click(3, 1)
    assert client.pointer_at == moved  # the same place again is not a move
    client.close()
