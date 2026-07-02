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

def test_ensure_client_nat_masquerades_each_exit_and_wan():
    exits = [
        {"id": "vpn1", "interface": "rpx101", "fwmark": 101},
        {"id": "direct", "interface": "eth0", "fwmark": 0},
    ]
    added = []
    with patch("subprocess.run") as run:
        # -C (check) returns nonzero -> rule absent -> -A is issued
        run.side_effect = lambda args, **kw: added.append(args) or MagicMock(
            returncode=(0 if args[:1] == ["ipset"] else (1 if "-C" in args else 0)))
        rm.ensure_client_nat("10.8.0.0/24", exits, "eth0")
    appends = [a for a in added if a[:4] == ["iptables", "-t", "nat", "-A"]]
    outs = {a[a.index("-o") + 1] for a in appends}
    assert outs == {"rpx101", "eth0"}                 # exit iface + WAN, not the direct exit's eth0 twice
    for a in appends:
        assert a[a.index("-s") + 1] == "10.8.0.0/24"
        assert a[-1] == "MASQUERADE"

def test_ensure_client_nat_noop_without_subnet():
    with patch("subprocess.run") as run:
        rm.ensure_client_nat(None, [], "eth0")
    run.assert_not_called()

def test_system_ipsets_empty_by_default():
    from routepanel.config import Config
    assert rm.system_ipsets(Config()) == []

def test_system_ipsets_includes_ru_direct_when_enabled():
    from routepanel.config import Config
    assert rm.system_ipsets(Config(ru_direct=True)) == [("ru_direct", "clear")]

def test_ensure_dns_intercept_dnats_client_53():
    added = []
    with patch("subprocess.run") as run:
        run.side_effect = lambda args, **kw: added.append(args) or MagicMock(
            returncode=(1 if "-C" in args else 0))
        rm.ensure_dns_intercept("10.8.0.0/24", 5353, ["awg0"])
    appends = [a for a in added if "-A" in a and "PREROUTING" in a]
    assert appends, "expected a DNAT PREROUTING rule"
    a = appends[0]
    assert "10.8.0.0/24" in a and "53" in a and "awg0" in a
    assert a[-1].endswith(":5353") or "5353" in a

def test_rebuild_chain_marks_ru_direct_when_enabled():
    from routepanel.config import Config
    appended = []
    with patch("routepanel.syncd.routing_manager.get_config", return_value=Config(ru_direct=True)), \
         patch.object(rm, "ipset_exists", return_value=True), \
         patch("subprocess.run") as run:
        run.side_effect = lambda args, **kw: appended.append(args) or MagicMock(returncode=0)
        rm.rebuild_chain([], {}, default_fwmark=0)
    assert ["-m", "set", "--match-set", "ru_direct", "dst",
            "-j", "MARK", "--and-mark", "0x0"] in [a[5:] for a in appended if len(a) > 5]
