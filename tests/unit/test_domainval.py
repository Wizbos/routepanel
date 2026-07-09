# tests/unit/test_domainval.py
import pytest
from routepanel.domainval import is_valid_domain, validate_domains, filter_valid_domains


# --- is_valid_domain: what dnsmasq's ipset=/.../ fragment line can safely hold ---

@pytest.mark.parametrize("domain", [
    "youtube.com",
    "googlevideo.com",
    "sub.domain.example.co.uk",
    "xn--80ak6aa92e.com",   # punycode IDN
    "a-b.example.com",
])
def test_valid_domains_accepted(domain):
    assert is_valid_domain(domain) is True

@pytest.mark.parametrize("domain", [
    "",                      # empty -- produces a bare '/' in the fragment line
    "evil.com/rule_1",       # embedded '/' -- extra field, could retarget the ipset
    "evil.com/../../etc",    # embedded '/'
    "has space.com",         # internal whitespace
    " leading.com",          # leading whitespace
    "trailing.com ",         # trailing whitespace
    "tab\tchar.com",         # control/whitespace char
    "new\nline.com",         # literal newline -- would inject an extra config line
    "comment#hack.com",      # '#' starts a dnsmasq comment mid-line
    "café.com",              # non-ASCII
    "no-dot",                # not a routable internet domain (no TLD)
    "-leadinghyphen.com",    # invalid label
    "trailinghyphen-.com",   # invalid label
    "a" * 260 + ".com",      # over the DNS length limit
    None,                    # wrong type
    123,                     # wrong type
])
def test_invalid_domains_rejected(domain):
    assert is_valid_domain(domain) is False


# --- validate_domains: panel-API contract (raise ValueError naming the bad entry) ---

def test_validate_domains_passes_through_valid_list():
    domains = ["youtube.com", "googlevideo.com"]
    assert validate_domains(domains) == domains

def test_validate_domains_raises_on_space():
    with pytest.raises(ValueError, match="has space.com"):
        validate_domains(["youtube.com", "has space.com"])

def test_validate_domains_raises_on_slash():
    with pytest.raises(ValueError):
        validate_domains(["evil.com/rule_1"])

def test_validate_domains_raises_on_empty_entry():
    with pytest.raises(ValueError):
        validate_domains(["youtube.com", ""])

def test_validate_domains_empty_list_ok():
    # A rule can legitimately have no domains (static-CIDR-only OSPF rule).
    assert validate_domains([]) == []


# --- filter_valid_domains: generator-side defense in depth (drop, don't raise) ---

def test_filter_valid_domains_drops_garbage_keeps_good():
    out = filter_valid_domains(["youtube.com", "bad space.com", "", "googlevideo.com"])
    assert out == ["youtube.com", "googlevideo.com"]

def test_filter_valid_domains_calls_on_invalid_for_each_drop():
    dropped = []
    filter_valid_domains(["ok.com", "bad/one.com", ""], on_invalid=dropped.append)
    assert dropped == ["bad/one.com", ""]

def test_filter_valid_domains_no_callback_ok():
    # on_invalid is optional -- must not raise when omitted.
    out = filter_valid_domains(["ok.com", "bad one.com"])
    assert out == ["ok.com"]
