# tests/unit/test_dnsmasq_manager.py
import json, os
from unittest.mock import patch
from routepanel.syncd import dnsmasq_manager as dm

def test_render_maps_domains_to_rule_set():
    rules = [{"id": 5, "domains": json.dumps(["youtube.com", "ytimg.com"])}]
    frag = dm.render_fragment(rules)
    # exit-independent: domains -> rule_<id>, not an exit set
    assert "ipset=/youtube.com/ytimg.com/rule_5" in frag

def test_render_skips_empty_domains():
    frag = dm.render_fragment([{"id": 9, "domains": "[]"}])
    assert "rule_9" not in frag

def test_write_fragment_detects_change(tmp_path):
    p = str(tmp_path / "frag.conf")
    assert dm.write_fragment(p, "a\n") is True     # new file
    assert dm.write_fragment(p, "a\n") is False    # unchanged
    assert dm.write_fragment(p, "b\n") is True      # changed


# --- render_fragment: generator-side sanitization (2026-07-09 incident) ---

def test_render_fragment_drops_invalid_domain_keeps_rest():
    # A malformed domain (embedded '/') must never reach the ipset=/.../ line --
    # it would inject an extra field and corrupt the fragment for the whole rule.
    rules = [{"id": 5, "domains": json.dumps(["youtube.com", "evil.com/rule_1", "ytimg.com"])}]
    frag = dm.render_fragment(rules)
    assert "ipset=/youtube.com/ytimg.com/rule_5" in frag
    assert "evil.com" not in frag

def test_render_fragment_all_domains_invalid_skips_rule_entirely():
    rules = [{"id": 7, "domains": json.dumps(["bad one.com", ""])}]
    frag = dm.render_fragment(rules)
    assert "rule_7" not in frag

def test_render_fragment_output_lines_always_parse_as_ipset_directive():
    # Every non-comment line must match dnsmasq's ipset=/dom[/dom...]/set shape:
    # no stray '/' fields, no whitespace, no unescaped '#'.
    rules = [
        {"id": 1, "domains": json.dumps(["youtube.com", "evil.com/x", "has space.com"])},
        {"id": 2, "domains": json.dumps(["netflix.com"])},
    ]
    frag = dm.render_fragment(rules)
    for line in frag.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        assert line.startswith("ipset=/")
        body = line[len("ipset="):]
        parts = body.split("/")
        assert parts[0] == ""                  # leading '/' -> first split segment empty
        set_name = parts[-1]
        domains = parts[1:-1]
        assert set_name.startswith("rule_")
        for d in domains:
            assert " " not in d and "#" not in d and d != ""


# --- sync_fragment: validate-before-apply + last-known-good rollback ---

def test_sync_fragment_unchanged_skips_validate_and_reload(tmp_path):
    p = str(tmp_path / "frag.conf")
    rules = [{"id": 5, "domains": json.dumps(["youtube.com"])}]
    dm.write_fragment(p, dm.render_fragment(rules))
    with patch.object(dm, "check_config") as mock_check, \
         patch.object(dm, "reload_dnsmasq") as mock_reload:
        result = dm.sync_fragment(p, "dnsmasq", rules)
    assert result is False
    mock_check.assert_not_called()
    mock_reload.assert_not_called()

def test_sync_fragment_applies_when_config_valid(tmp_path):
    p = str(tmp_path / "frag.conf")
    rules = [{"id": 5, "domains": json.dumps(["youtube.com"])}]
    with patch.object(dm, "check_config", return_value=True) as mock_check, \
         patch.object(dm, "reload_dnsmasq") as mock_reload:
        result = dm.sync_fragment(p, "dnsmasq", rules)
    assert result is True
    mock_check.assert_called_once()
    mock_reload.assert_called_once_with("dnsmasq")
    with open(p) as f:
        assert "ipset=/youtube.com/rule_5" in f.read()

def test_sync_fragment_rejects_and_restores_last_known_good(tmp_path):
    p = str(tmp_path / "frag.conf")
    good_rules = [{"id": 5, "domains": json.dumps(["youtube.com"])}]
    good_content = dm.render_fragment(good_rules)
    dm.write_fragment(p, good_content)   # simulate a previously-applied, working fragment

    bad_rules = [{"id": 5, "domains": json.dumps(["youtube.com", "netflix.com"])}]
    with patch.object(dm, "check_config", return_value=False) as mock_check, \
         patch.object(dm, "reload_dnsmasq") as mock_reload:
        result = dm.sync_fragment(p, "dnsmasq", bad_rules)
    assert result is False
    mock_check.assert_called_once()
    mock_reload.assert_not_called()          # never reload on a failed validation
    with open(p) as f:
        assert f.read() == good_content      # last-known-good restored, not the bad content

def test_sync_fragment_rejects_with_no_prior_good_removes_fragment(tmp_path):
    p = str(tmp_path / "frag.conf")   # never existed before -- no LKG to fall back to
    rules = [{"id": 5, "domains": json.dumps(["youtube.com"])}]
    with patch.object(dm, "check_config", return_value=False), \
         patch.object(dm, "reload_dnsmasq") as mock_reload:
        result = dm.sync_fragment(p, "dnsmasq", rules)
    assert result is False
    mock_reload.assert_not_called()
    assert not os.path.exists(p)             # never leave a known-bad fragment in place

def test_check_config_uses_dnsmasq_test_flag():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert dm.check_config() is True
        mock_run.assert_called_once_with(["dnsmasq", "--test"], capture_output=True)

def test_check_config_false_on_nonzero_exit():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert dm.check_config() is False
