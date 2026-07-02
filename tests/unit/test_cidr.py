# tests/unit/test_cidr.py
import pytest
from routepanel.cidr import normalize_cidr, normalize_cidrs


def test_bare_ipv4_becomes_32():
    assert normalize_cidr("172.67.72.55") == "172.67.72.55/32"

def test_network_preserved():
    assert normalize_cidr("8.6.112.0/24") == "8.6.112.0/24"

def test_host_bits_masked_strict_false():
    assert normalize_cidr("10.0.0.5/24") == "10.0.0.0/24"

def test_bare_ipv6_becomes_128():
    assert normalize_cidr("2606:4700::1") == "2606:4700::1/128"

def test_whitespace_tolerated():
    assert normalize_cidr("  1.2.3.4 ") == "1.2.3.4/32"

def test_garbage_raises():
    with pytest.raises(ValueError):
        normalize_cidr("not-an-ip")

def test_bad_prefixlen_raises():
    with pytest.raises(ValueError):
        normalize_cidr("1.2.3.4/33")

def test_list_normalizes_dedupes_and_orders():
    assert normalize_cidrs(["8.6.112.0/24", "172.67.72.55", "8.6.112.0/24"]) == \
        ["8.6.112.0/24", "172.67.72.55/32"]

def test_list_raises_naming_offending_entry():
    with pytest.raises(ValueError) as e:
        normalize_cidrs(["1.1.1.1", "bad"])
    assert "bad" in str(e.value)
