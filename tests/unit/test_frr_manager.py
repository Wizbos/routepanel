# tests/unit/test_frr_manager.py
from unittest.mock import patch, MagicMock
from routepanel.syncd import frr_manager

SHOW_ROUTE_OUTPUT = """\
Codes: K - kernel route, C - connected, S - static, R - RIP,
S>* 1.2.3.4/32 [1/0] via Null0, 00:01:00
S>* 5.6.7.8/32 [1/0] via Null0, 00:01:00
C>* 10.8.1.0/24 is directly connected, awg1
"""

def test_get_static_routes_parses():
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(returncode=0, stdout=SHOW_ROUTE_OUTPUT)
        result = frr_manager.get_static_routes()
    assert result == {"1.2.3.4/32", "5.6.7.8/32"}

def test_sync_routes_adds_and_removes():
    current = {"1.2.3.4/32", "9.9.9.9/32"}
    desired = {"1.2.3.4/32", "5.6.7.8/32"}
    with patch.object(frr_manager, "get_static_routes", return_value=current), \
         patch.object(frr_manager, "add_route") as mock_add, \
         patch.object(frr_manager, "remove_route") as mock_del:
        added, removed = frr_manager.sync_routes(desired)
    mock_add.assert_called_once_with("5.6.7.8/32", "Null0")
    mock_del.assert_called_once_with("9.9.9.9/32", "Null0")
    assert added == {"5.6.7.8/32"}
    assert removed == {"9.9.9.9/32"}


# --- prefix sanitization: a bad/maskless prefix must not poison the batch ---

def test_sync_routes_batch_normalizes_bare_ip():
    # A bare IP must reach vtysh as /32, never maskless (which vtysh rejects).
    with patch.object(frr_manager, "get_static_routes", return_value=set()), \
         patch.object(frr_manager, "_vtysh") as mock_vtysh:
        added, removed = frr_manager.sync_routes_batch({"172.67.72.55"}, "1.1.1.1")
    assert added == {"172.67.72.55/32"}
    sent = " ".join(c for call in mock_vtysh.call_args_list for c in call.args)
    assert "ip route 172.67.72.55/32 1.1.1.1" in sent
    assert "ip route 172.67.72.55 1.1.1.1" not in sent

def test_sync_routes_batch_skips_garbage_without_raising():
    with patch.object(frr_manager, "get_static_routes", return_value=set()), \
         patch.object(frr_manager, "_vtysh") as mock_vtysh:
        added, removed = frr_manager.sync_routes_batch({"garbage", "5.6.7.8/32"}, "1.1.1.1")
    assert added == {"5.6.7.8/32"}
    sent = " ".join(c for call in mock_vtysh.call_args_list for c in call.args)
    assert "garbage" not in sent

def test_sync_routes_normalizes_bare_ip():
    with patch.object(frr_manager, "get_static_routes", return_value=set()), \
         patch.object(frr_manager, "add_route") as mock_add, \
         patch.object(frr_manager, "remove_route"):
        added, _ = frr_manager.sync_routes({"172.67.72.55"}, "1.1.1.1")
    assert added == {"172.67.72.55/32"}
    mock_add.assert_called_once_with("172.67.72.55/32", "1.1.1.1")
