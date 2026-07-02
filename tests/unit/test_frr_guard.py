from unittest.mock import patch
from routepanel.syncd import main as syncd_main
from routepanel.config import Config

def _reset_state():
    syncd_main._last_ospf_pushed = set()
    syncd_main._last_frr_sync = 0.0

def test_maybe_push_frr_skips_when_disabled():
    _reset_state()
    cfg = Config(frr_next_hop="")
    with patch.object(syncd_main.frr_manager, "sync_routes_batch") as srb:
        syncd_main._maybe_push_frr({"1.2.3.4/32"}, cfg)
    srb.assert_not_called()

def test_maybe_push_frr_pushes_when_configured():
    _reset_state()
    cfg = Config(frr_next_hop="192.0.2.1", ospf_debounce_sec=0)
    with patch.object(syncd_main.frr_manager, "sync_routes_batch",
                      return_value=(set(), set())) as srb:
        syncd_main._maybe_push_frr({"9.9.9.9/32"}, cfg)
    srb.assert_called_once_with({"9.9.9.9/32"}, "192.0.2.1")
