# tests/unit/test_routing_manager.py
import subprocess
from unittest.mock import patch, MagicMock
from routepanel.syncd import routing_manager as rm

def _cp(rc=0, stdout=""):
    return MagicMock(returncode=rc, stdout=stdout)

def test_rebuild_chain_per_rule_marks_effective_exit():
    rules = [{"id": 5}, {"id": 8}]
    effective = {5: 0, 8: 100}        # rule 5 -> direct (clear), rule 8 -> VPN exit (100)
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
    # rule 8 -> VPN exit, rule 5 -> direct; both after the system rules
    assert ["-m", "set", "--match-set", "rule_8", "dst", "-j", "MARK", "--set-mark", "100"] in appended
    assert ["-m", "set", "--match-set", "rule_5", "dst", "-j", "MARK", "--and-mark", "0x0"] in appended
    assert appended.index(["-m","set","--match-set","rule_8","dst","-j","MARK","--set-mark","100"]) > 1

def test_apply_routing_tables_tolerates_missing_device():
    # At boot, an exit's rpx iface may not be up yet. `ip route replace ... dev
    # <iface>` fails in that case -- it must be logged and skipped, not raise
    # and abort the whole reconcile (which would also skip every later exit).
    exits = [
        {"id": "missing", "fwmark": 101, "routing_table": "101", "interface": "rpx101"},
        {"id": "present", "fwmark": 102, "routing_table": "102", "interface": "rpx102"},
    ]
    calls = []
    def fake_run(args, **kw):
        calls.append(args)
        if args[:3] == ["ip", "route", "replace"] and "rpx101" in args:
            if kw.get("check"):
                raise subprocess.CalledProcessError(1, args, stderr='Cannot find device "rpx101"\n')
            return MagicMock(returncode=1, stdout="", stderr='Cannot find device "rpx101"\n')
        return _cp(0)
    with patch("subprocess.run", side_effect=fake_run):
        rm.apply_routing_tables(exits)   # must not raise
    replace_calls = [c for c in calls if c[:3] == ["ip", "route", "replace"]]
    assert len(replace_calls) == 2   # both attempted; failure of the first didn't abort the loop

def test_rebuild_chain_skips_missing_system_ipset():
    # A deployment-added system ipset (SYSTEM_IPSETS is empty in the OSS build but
    # a deployment may populate it) may not exist yet -- e.g. routesyncd starts
    # before whatever provisions it, or a set was dropped. `-A ... --match-set
    # <missing> dst` fails; that single missing set must be skipped (logged), not
    # raise and abort the rest of the chain rebuild.
    rules = [{"id": 5}]
    effective = {5: 100}
    appended = []
    def fake_run(args, **kw):
        if args[:4] == ["iptables", "-t", "mangle", "-A"] and args[4] == rm.CHAIN:
            if "missing_set" in args:
                if kw.get("check"):
                    raise subprocess.CalledProcessError(1, args, stderr="ipset missing_set not found\n")
                return _cp(1)
            appended.append(args[5:])
            return _cp(0)
        if args[:2] == ["ipset", "list"]:
            # missing_set doesn't exist; present_set does
            return _cp(1) if "missing_set" in args else _cp(0)
        return _cp(0)
    with patch.object(rm, "SYSTEM_IPSETS", [("present_set", "clear"), ("missing_set", 100)]), \
         patch("subprocess.run", side_effect=fake_run), \
         patch("routepanel.config.get_config", return_value=MagicMock(client_interfaces=["awg0"])):
        rm.rebuild_chain(rules, effective, default_fwmark=100)   # must not raise
    # rule 5's match still got appended -- the missing system set didn't abort the rebuild
    assert ["-m", "set", "--match-set", "rule_5", "dst", "-j", "MARK", "--set-mark", "100"] in appended
    # the present system set still got its rule
    assert any("present_set" in a for a in appended)
    assert not any("missing_set" in a for a in appended)
