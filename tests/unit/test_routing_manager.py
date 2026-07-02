# tests/unit/test_routing_manager.py
from unittest.mock import patch, MagicMock
from routepanel.syncd import routing_manager as rm

def _cp(rc=0, stdout=""):
    return MagicMock(returncode=rc, stdout=stdout)

def test_rebuild_chain_per_rule_marks_effective_exit():
    rules = [{"id": 5}, {"id": 8}]
    effective = {5: 0, 8: 100}        # rule 5 -> direct (clear), rule 8 -> doprax (100)
    appended = []
    def fake_run(args, **kw):
        if args[:4] == ["iptables", "-t", "mangle", "-A"] and args[4] == rm.CHAIN:
            appended.append(args[5:])
        return _cp(0)
    with patch("subprocess.run", side_effect=fake_run), \
         patch("routepanel.config.get_config", return_value=MagicMock(client_interfaces=["awg0"])):
        rm.rebuild_chain(rules, effective, default_fwmark=100)
    # catch-all default first, marked to the default exit's effective fwmark
    assert appended[0] == ["-j", "MARK", "--set-mark", "100"]
    # rule 8 -> doprax, rule 5 -> direct; both after the system rules
    assert ["-m", "set", "--match-set", "rule_8", "dst", "-j", "MARK", "--set-mark", "100"] in appended
    assert ["-m", "set", "--match-set", "rule_5", "dst", "-j", "MARK", "--and-mark", "0x0"] in appended
    assert appended.index(["-m","set","--match-set","rule_8","dst","-j","MARK","--set-mark","100"]) > 1
