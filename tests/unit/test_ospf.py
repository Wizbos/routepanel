from routepanel.syncd.ospf import build_ospf_desired, uncovered_hosts


def test_static_cidrs_always_included_and_normalized():
    out = build_ospf_desired(ipset_members=set(), static_cidrs=["104.21.95.93/32", "10.0.0.0/24"], cap=64)
    assert out == {"104.21.95.93/32", "10.0.0.0/24"}


def test_host_members_become_slash32_and_are_capped():
    members = {f"192.0.2.{i}" for i in range(100)}  # 100 bare host IPs
    out = build_ospf_desired(ipset_members=members, static_cidrs=[], cap=64)
    assert len(out) == 64
    assert all(p.endswith("/32") for p in out)


def test_union_of_static_and_live_hosts():
    members = {"188.114.97.1", "104.21.95.93", "10.0.0.0/24"}  # mix: hosts + a cidr already in set
    out = build_ospf_desired(ipset_members=members, static_cidrs=["10.0.0.0/24"], cap=64)
    assert "10.0.0.0/24" in out
    assert "188.114.97.1/32" in out
    assert "104.21.95.93/32" in out


def test_hosts_covered_by_static_cidrs_do_not_consume_cap():
    # 2026-10-18: YouTube had 438 live /32s, mostly inside its static Google CIDRs;
    # they ate all 64 slots and the GGC cache 81.27.242.142 was never advertised.
    members = {f"142.250.{i // 256}.{i % 256}" for i in range(100)} | {"81.27.242.142"}
    out = build_ospf_desired(ipset_members=members, static_cidrs=["142.250.0.0/15"], cap=64)
    assert out == {"142.250.0.0/15", "81.27.242.142/32"}


def test_cap_picks_hosts_in_numeric_not_string_order():
    # String sort puts "81.x" after "142.x"/"213.x" -> 8x.x hosts were always cut first.
    members = {"213.221.56.12", "81.27.242.142", "142.251.1.1"}
    out = build_ospf_desired(ipset_members=members, static_cidrs=[], cap=2)
    assert out == {"81.27.242.142/32", "142.251.1.1/32"}


def test_uncovered_hosts_excludes_cidrs_and_covered_ips():
    members = {"10.0.0.0/24", "10.0.0.5", "8.8.8.8", "1.1.1.1"}
    assert uncovered_hosts(members, ["10.0.0.0/24", "bogus"]) == ["1.1.1.1", "8.8.8.8"]
