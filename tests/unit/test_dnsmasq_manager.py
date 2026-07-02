# tests/unit/test_dnsmasq_manager.py
import json
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
