import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parents[2] / "scripts"))
import ru_direct_refresh as rd
from unittest.mock import MagicMock

def test_parse_zone_ipv4_only():
    text = "5.8.0.0/19\n# comment\n2a00:1::/32\ngarbage\n31.13.0.0/16\n"
    assert rd.parse_zone(text) == ["5.8.0.0/19", "31.13.0.0/16"]

def test_apply_ipset_atomic_swap():
    calls = []
    runner = lambda args, **kw: calls.append(args) or MagicMock(returncode=0)
    rd.apply_ipset(["1.2.3.0/24"], ipset="ru_direct", runner=runner)
    verbs = [a[1] for a in calls if a[0] == "ipset"]
    assert "swap" in verbs and "destroy" in verbs            # tmp set swapped in, then removed
    assert any(a[0] == "ipset" and a[1] == "restore" for a in calls)

def test_main_keeps_set_on_empty_fetch(capsys):
    rd.main.__globals__  # smoke
    rd.main(url="x")  # _default_fetch will fail on 'x' -> keeps set, prints to stderr
    assert "keeping existing set" in capsys.readouterr().err
