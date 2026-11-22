"""Per-host egress for CLI and MCP boxes: which public hosts a run reached (brief 15.7, gap audit P3-02).

The web guard (web_guard.py) sees a browser's requests; a CLI or an MCP server opens its own sockets, so
the box logs them instead. Three sources, any mix, all plain text read back from the box:

- nftables: a log rule on the output hook (nft_log_rules) writes one kernel line per new connection,
  `... pickfit-egress: ... DST=93.184.216.34 ... DPT=443 ...`, read with EGRESS_LOG_COMMAND.
- ss: `ss -tnH` (or with its header) while the server runs: the peer column of each socket.
- DNS and TLS names: dnsmasq's log-queries lines (`query[A] api.example.com from 127.0.0.1`,
  `reply api.example.com is 93.184.216.34`) and SNI lines (`sni=api.example.com`) name what an IP was.

parse_egress_hosts turns that into host names (an IP whose name the log or dns_map gives) or IPs, lower case,
each once, at most MCP_EGRESS_HOSTS_MAX. Loopback, private, link-local, multicast and unspecified addresses are
dropped: they never leave the machine. Port 53 connections are the box's own resolver, so lookups are recorded
by the names they asked for instead. Pure Python: no box, no network.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping

from pickfit.schema import MCP_EGRESS_HOSTS_MAX

LOG_PREFIX = "pickfit-egress: "
NFT_TABLE = "pickfit_egress"
# Kernel lines with the rule's prefix; dmesg when journald is not running in the box.
EGRESS_LOG_COMMAND = (f"journalctl -k --no-pager -o cat 2>/dev/null | grep -F '{LOG_PREFIX.strip()}' "
                      f"|| dmesg 2>/dev/null | grep -F '{LOG_PREFIX.strip()}'")
SS_COMMAND = "ss -tunH state established 2>/dev/null"

_DST = re.compile(r"\bDST=(?P<ip>[0-9A-Fa-f:.]+)")
_DPT = re.compile(r"\bDPT=(?P<port>\d{1,5})")
_SS_ADDR = re.compile(r"^\[?(?P<ip>[0-9A-Fa-f:.]+?)(?:%[\w.-]+)?\]?:(?P<port>\d{1,5}|\*)$")
_QUERY = re.compile(r"\bquery\[[A-Z0-9]+\]\s+(?P<name>\S+)\s+from\s")
_REPLY = re.compile(r"\b(?:reply|cached|forwarded-reply)\s+(?P<name>\S+)\s+is\s+(?P<ip>[0-9A-Fa-f:.]+)\b")
_SNI = re.compile(r"\bsni[=:]\s*(?P<name>[A-Za-z0-9_.-]+)", re.I)
_NAME = re.compile(r"^[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9])?(?:\.[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9])?)+$")
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".in-addr.arpa", ".ip6.arpa")


def nft_log_rules(prefix: str = LOG_PREFIX, table: str = NFT_TABLE) -> list[str]:
    """Shell commands that log every new outbound connection from the box (not loopback) with prefix.

    The chain only logs and accepts: an offline replay still blocks the network elsewhere. Run as root before
    the server starts; read the lines back with EGRESS_LOG_COMMAND.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+ ?", prefix) or not re.fullmatch(r"[A-Za-z0-9_]+", table):
        raise ValueError("prefix and table must be plain words")
    return [
        f"nft add table inet {table}",
        f"nft 'add chain inet {table} output {{ type filter hook output priority 0; policy accept; }}'",
        f"nft add rule inet {table} output oifname != lo ct state new log prefix '\"{prefix}\"' level info",
    ]


def nft_cleanup(table: str = NFT_TABLE) -> str:
    """The command that removes the log rules again."""
    return f"nft delete table inet {table} 2>/dev/null || true"


def _ip(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        ip = ipaddress.ip_address(text.strip("[]"))
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether a destination leaves the machine and its network: not loopback, private, link-local and the like."""
    return not (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified
                or ip.is_reserved)


def _name(text: str) -> str | None:
    """A DNS name as recorded: lower case, no trailing dot; None for one that is not a public name."""
    name = text.strip().lower().rstrip(".")
    if not _NAME.match(name) or len(name) > 253 or name == "localhost" or name.endswith(_LOCAL_SUFFIXES):
        return None
    if _ip(name) is not None:  # 1.2.3.4 parses as a name too
        return None
    return name


def _ss_peers(line: str) -> Iterable[tuple[str, int | None]]:
    """The peer address of one ss line: the second addr:port column."""
    addrs = []
    for word in line.split():
        m = _SS_ADDR.match(word)
        if m and _ip(m.group("ip")) is not None:
            addrs.append((m.group("ip"), None if m.group("port") == "*" else int(m.group("port"))))
    return addrs[1:2]


def parse_egress_hosts(log_text: str, dns_map: Mapping[str, str] | None = None,
                       limit: int = MCP_EGRESS_HOSTS_MAX) -> list[str]:
    """The public hosts a box's egress log shows, first seen first: names where the log or dns_map name the IP.

    dns_map: IP -> host name from elsewhere (e.g. the box's resolver cache). A log with DNS lookups but no
    connection lines (nothing else was logged) records the names it looked up.
    """
    names: dict[str, str] = {}
    for ip_text, name in (dns_map or {}).items():
        ip, host = _ip(str(ip_text)), _name(str(name))
        if ip is not None and host is not None:
            names.setdefault(str(ip), host)

    found: list[tuple[str, str]] = []  # ("ip", text) or ("name", text), in log order
    queried: list[str] = []
    connections = False
    for line in log_text.splitlines():
        reply = _REPLY.search(line)
        if reply:
            ip, host = _ip(reply.group("ip")), _name(reply.group("name"))
            if ip is not None and host is not None:
                names.setdefault(str(ip), host)
            continue
        query = _QUERY.search(line)
        if query:
            host = _name(query.group("name"))
            if host:
                queried.append(host)
            continue
        sni = _SNI.search(line)
        if sni:
            host = _name(sni.group("name"))
            if host:
                found.append(("name", host))
                connections = True
            continue
        dst = _DST.search(line)
        if dst:
            port = _DPT.search(line)
            peers = [(dst.group("ip"), int(port.group("port")) if port else None)]
        else:
            peers = list(_ss_peers(line))
        for ip_text, port in peers:
            ip = _ip(ip_text)
            if ip is None:
                continue
            connections = True
            if port == 53 or not is_public_ip(ip):
                continue
            found.append(("ip", str(ip)))

    hosts: list[str] = []
    for kind, text in found:
        host = names.get(text, text) if kind == "ip" else text
        if host not in hosts:
            hosts.append(host)
    if not connections:
        hosts = list(dict.fromkeys(queried))
    return hosts[:max(limit, 0)]
