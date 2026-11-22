"""Per-host egress for CLI and MCP boxes (pickfit/verify/egress.py): nftables, ss and DNS/SNI lines to public hosts."""

from __future__ import annotations

import pytest

from pickfit.schema import MCP_EGRESS_HOSTS_MAX, McpHandshake
from pickfit.verify.egress import (
    EGRESS_LOG_COMMAND,
    LOG_PREFIX,
    is_public_ip,
    nft_cleanup,
    nft_log_rules,
    parse_egress_hosts,
)


def nft(dst: str, port: int = 443, proto: str = "TCP") -> str:
    return (f"[ 101.5] {LOG_PREFIX}IN= OUT=eth0 SRC=10.0.2.15 DST={dst} LEN=60 TOS=0x00 TTL=64 ID=1 DF "
            f"PROTO={proto} SPT=51234 DPT={port} WINDOW=64240 SYN")


def test_nftables_destinations_in_log_order() -> None:
    log = "\n".join([nft("93.184.216.34"), nft("140.82.112.3"), nft("93.184.216.34", 80)])
    assert parse_egress_hosts(log) == ["93.184.216.34", "140.82.112.3"]


def test_ipv6_and_mapped_destinations() -> None:
    log = "\n".join([nft("2606:4700:4700::1111"), nft("::ffff:93.184.216.34"), nft("2606:4700:4700:0::1111")])
    assert parse_egress_hosts(log) == ["2606:4700:4700::1111", "93.184.216.34"]


@pytest.mark.parametrize("dst", [
    "127.0.0.1", "127.8.9.1", "::1", "10.1.2.3", "172.16.0.9", "172.31.255.1", "192.168.1.20", "169.254.169.254",
    "fe80::1", "fd00::5", "0.0.0.0", "224.0.0.251", "::ffff:127.0.0.1",
])
def test_loopback_private_and_link_local_are_dropped(dst: str) -> None:
    assert parse_egress_hosts(nft(dst)) == []


def test_public_neighbours_of_private_ranges_stay() -> None:
    log = "\n".join([nft("172.15.0.1"), nft("172.32.0.1"), nft("11.0.0.1")])
    assert parse_egress_hosts(log) == ["172.15.0.1", "172.32.0.1", "11.0.0.1"]


def test_dns_replies_name_the_ips_and_port_53_is_the_resolver() -> None:
    log = "\n".join([
        "dnsmasq[88]: query[A] API.GitHub.com. from 127.0.0.1",
        "dnsmasq[88]: forwarded api.github.com to 8.8.8.8",
        "dnsmasq[88]: reply api.github.com is 140.82.112.5",
        "dnsmasq[88]: reply api.github.com is <CNAME>",
        nft("8.8.8.8", 53, "UDP"),
        nft("140.82.112.5"),
        nft("151.101.1.69"),
    ])
    assert parse_egress_hosts(log) == ["api.github.com", "151.101.1.69"]


def test_dns_map_names_ips_and_bad_entries_are_ignored() -> None:
    dns = {"151.101.1.69": "Registry.npmjs.org.", "140.82.112.5": "not a name", "x": "a.example.com"}
    log = "\n".join([nft("151.101.1.69"), nft("140.82.112.5")])
    assert parse_egress_hosts(log, dns) == ["registry.npmjs.org", "140.82.112.5"]


def test_one_name_for_two_ips_is_recorded_once() -> None:
    log = "\n".join(["reply cdn.example.com is 93.184.216.34", "reply cdn.example.com is 93.184.216.35",
                     nft("93.184.216.34"), nft("93.184.216.35")])
    assert parse_egress_hosts(log) == ["cdn.example.com"]


def test_a_dns_only_log_records_the_names_looked_up() -> None:
    log = "\n".join(["query[A] api.example.com from 127.0.0.1", "query[AAAA] api.example.com from 127.0.0.1",
                     "query[A] localhost from 127.0.0.1", "query[A] printer.local from 127.0.0.1",
                     "query[A] telemetry.example.org from 127.0.0.1"])
    assert parse_egress_hosts(log) == ["api.example.com", "telemetry.example.org"]


def test_lookups_without_a_connection_are_not_hosts_when_connections_were_logged() -> None:
    log = "\n".join(["query[A] unused.example.com from 127.0.0.1", nft("10.0.0.9")])
    assert parse_egress_hosts(log) == []


def test_sni_lines_name_hosts() -> None:
    log = "tls sni=Telemetry.Example.ORG dst=93.184.216.34\nsni: localhost\n"
    assert parse_egress_hosts(log) == ["telemetry.example.org"]


def test_ss_peer_columns() -> None:
    log = "\n".join([
        "State  Recv-Q Send-Q Local Address:Port  Peer Address:Port Process",
        'ESTAB  0      0      10.0.2.15:51234     93.184.216.34:443 users:(("node",pid=7,fd=21))',
        "ESTAB  0      0      127.0.0.1:40000     127.0.0.1:8080",
        "ESTAB  0      0      [2001:db8::2]:5000  [2606:4700::6810:84e5]:443",
        "LISTEN 0      511    0.0.0.0:3000        0.0.0.0:*",
        "tcp    ESTAB  0      0     10.0.2.15:51240  140.82.112.3:443",
    ])
    assert parse_egress_hosts(log) == ["93.184.216.34", "2606:4700::6810:84e5", "140.82.112.3"]


def test_hosts_are_capped_and_fit_the_record() -> None:
    log = "\n".join(nft(f"93.184.{i // 200}.{i % 200 + 1}") for i in range(80))
    hosts = parse_egress_hosts(log)
    assert len(hosts) == MCP_EGRESS_HOSTS_MAX and hosts[0] == "93.184.0.1"
    assert parse_egress_hosts(log, limit=3) == ["93.184.0.1", "93.184.0.2", "93.184.0.3"]
    McpHandshake.model_validate({"transport": "stdio", "launch": ["srv"], "tool_count": 0, "egress_hosts": hosts})


def test_noise_and_empty_logs() -> None:
    assert parse_egress_hosts("") == []
    assert parse_egress_hosts("DST=not-an-ip DPT=443\nrandom text 1.2.3\nDST=999.1.1.1\n") == []


def test_is_public_ip() -> None:
    import ipaddress

    assert is_public_ip(ipaddress.ip_address("93.184.216.34"))
    assert not is_public_ip(ipaddress.ip_address("192.168.0.1"))


def test_nft_rules_log_new_outbound_connections_off_loopback() -> None:
    rules = nft_log_rules()
    assert rules[0] == "nft add table inet pickfit_egress"
    assert "hook output" in rules[1] and "policy accept" in rules[1]
    assert "oifname != lo" in rules[2] and "ct state new" in rules[2] and LOG_PREFIX in rules[2]
    assert nft_cleanup().startswith("nft delete table inet pickfit_egress")
    assert LOG_PREFIX.strip() in EGRESS_LOG_COMMAND
    with pytest.raises(ValueError):
        nft_log_rules(prefix="x'; reboot; '")
    with pytest.raises(ValueError):
        nft_log_rules(table="t; reboot")
