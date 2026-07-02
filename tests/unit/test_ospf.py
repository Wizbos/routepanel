from routepanel.syncd.ospf import build_ospf_desired


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
