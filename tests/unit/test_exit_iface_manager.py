import os, time
from unittest.mock import patch, MagicMock, call
from routepanel.syncd import exit_iface_manager as eim

def _exits():
    return [
        {"id": "myvpn", "type": "awg", "interface": "rpx101", "fwmark": 101},
        {"id": "direct", "type": "manual", "interface": "eth0", "fwmark": 0},
    ]

def test_brings_up_missing_awg_iface(tmp_path):
    (tmp_path / "rpx101.conf").write_text("[Interface]\n")
    with patch("subprocess.run") as run, patch("shutil.which", return_value="/usr/bin/awg-quick"):
        run.side_effect = [
            MagicMock(returncode=1),   # ip link show rpx101 -> missing
            MagicMock(returncode=0),   # awg-quick up
        ]
        eim.reconcile_interfaces(_exits(), str(tmp_path))
    assert run.call_args_list[1].args[0][:2] == ["awg-quick", "up"]

def test_skips_present_iface(tmp_path):
    (tmp_path / "rpx101.conf").write_text("[Interface]\n")
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)  # ip link show -> exists
        eim.reconcile_interfaces(_exits(), str(tmp_path))
    assert all(c.args[0][0] == "ip" for c in run.call_args_list)

def test_orphan_conf_archived_not_deleted(tmp_path):
    conf = tmp_path / "rpx102.conf"
    conf.write_text("[Interface]\n")   # no exit row for it
    old = time.time() - 4000; os.utime(str(conf), (old, old))   # older than grace
    with patch("subprocess.run") as run, patch("shutil.which", return_value="/usr/bin/awg-quick"):
        run.return_value = MagicMock(returncode=0)
        eim.reconcile_interfaces(_exits(), str(tmp_path))
    assert not (tmp_path / "rpx102.conf").exists()
    archived = list(tmp_path.glob("rpx102.conf.revoked-*"))
    assert len(archived) == 1                                 # archived, never unlinked
    downs = [c for c in run.call_args_list if c.args[0][:2] == ["awg-quick", "down"]]
    assert len(downs) == 1

def test_fresh_orphan_conf_not_archived(tmp_path):
    conf = tmp_path / "rpx102.conf"; conf.write_text("[Interface]\n")   # no exit row, just created
    with patch("subprocess.run") as run, patch("shutil.which", return_value="/usr/bin/awg-quick"):
        run.return_value = MagicMock(returncode=0)
        eim.reconcile_interfaces(_exits(), str(tmp_path), grace_sec=600)
    assert conf.exists()                                    # within grace -> preserved
    assert not list(tmp_path.glob("rpx102.conf.revoked-*"))

def test_old_orphan_conf_archived(tmp_path):
    conf = tmp_path / "rpx102.conf"; conf.write_text("[Interface]\n")
    old = time.time() - 4000; os.utime(conf, (old, old))    # older than grace
    with patch("subprocess.run") as run, patch("shutil.which", return_value="/usr/bin/awg-quick"):
        run.return_value = MagicMock(returncode=0)
        eim.reconcile_interfaces(_exits(), str(tmp_path), grace_sec=600)
    assert not conf.exists()
    assert len(list(tmp_path.glob("rpx102.conf.revoked-*"))) == 1
