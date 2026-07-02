import pytest
from routepanel import awg

AWG_SAMPLE = """
[Interface]
PrivateKey = aBcD+priv=
Address = 10.66.0.2/32
DNS = 1.1.1.1
Jc = 4
Jmin = 40
Jmax = 70
S1 = 116
S2 = 61
H1 = 1239304154
H2 = 918327131
H3 = 1069286926
H4 = 1902871833

[Peer]
PublicKey = eFgH+pub=
PresharedKey = iJkL+psk=
Endpoint = 203.0.113.10:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""

WG_SAMPLE = """
[Interface]
PrivateKey = aBcD+priv=
Address = 10.66.0.2/32

[Peer]
PublicKey = eFgH+pub=
Endpoint = vpn.example.com:51820
AllowedIPs = 0.0.0.0/0
"""

def test_parse_awg():
    tc = awg.parse_tunnel_conf(AWG_SAMPLE)
    assert tc.interface["PrivateKey"] == "aBcD+priv="
    assert tc.peer["Endpoint"] == "203.0.113.10:51820"
    assert tc.is_awg

def test_parse_plain_wg():
    tc = awg.parse_tunnel_conf(WG_SAMPLE)
    assert not tc.is_awg

@pytest.mark.parametrize("missing", ["PrivateKey", "Address"])
def test_missing_interface_field(missing):
    broken = "\n".join(l for l in AWG_SAMPLE.splitlines() if not l.startswith(missing))
    with pytest.raises(awg.ConfError):
        awg.parse_tunnel_conf(broken)

@pytest.mark.parametrize("missing", ["PublicKey", "Endpoint"])
def test_missing_peer_field(missing):
    broken = "\n".join(l for l in AWG_SAMPLE.splitlines() if not l.startswith(missing))
    with pytest.raises(awg.ConfError):
        awg.parse_tunnel_conf(broken)

def test_garbage_rejected():
    with pytest.raises(awg.ConfError):
        awg.parse_tunnel_conf("hello world")

def test_render_exit_conf_normalization():
    out = awg.render_exit_conf(awg.parse_tunnel_conf(AWG_SAMPLE))
    assert "Table = off" in out
    assert "DNS" not in out                      # exit iface must not rewrite host DNS
    assert "Jc = 4" in out                       # AWG params preserved
    assert "AllowedIPs = 0.0.0.0/0" in out
    assert awg.parse_tunnel_conf(out).is_awg     # round-trips

def test_duplicate_section_case_variant_rejected():
    # [Interface] and [interface] must not silently merge -- a duplicated
    # section (any case) is almost certainly a malformed/malicious paste.
    conf = """
[Interface]
PrivateKey = aBcD+priv=
Address = 10.66.0.2/32

[interface]
PrivateKey = OTHER+priv=

[Peer]
PublicKey = eFgH+pub=
Endpoint = vpn.example.com:51820
"""
    with pytest.raises(awg.ConfError):
        awg.parse_tunnel_conf(conf)

def test_empty_value_treated_as_missing():
    conf = """
[Interface]
PrivateKey =
Address = 10.66.0.2/32

[Peer]
PublicKey = eFgH+pub=
Endpoint = vpn.example.com:51820
"""
    with pytest.raises(awg.ConfError):
        awg.parse_tunnel_conf(conf)

def test_render_strips_dns_table_case_insensitively():
    conf = """
[Interface]
PrivateKey = aBcD+priv=
Address = 10.66.0.2/32
dns = 1.1.1.1
table = 1234

[Peer]
PublicKey = eFgH+pub=
Endpoint = vpn.example.com:51820
"""
    out = awg.render_exit_conf(awg.parse_tunnel_conf(conf))
    assert "1.1.1.1" not in out                  # lowercase dns must still be stripped
    assert "1234" not in out                      # lowercase table must still be overridden
    assert "Table = off" in out
