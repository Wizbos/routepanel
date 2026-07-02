# tests/unit/test_ipset_manager.py
import pytest
from unittest.mock import patch, MagicMock
from routepanel.syncd import ipset_manager

def make_ipset_list_output(members: list[str]) -> str:
    lines = ["Name: rule_5", "Type: hash:net", "Members:"] + members
    return "\n".join(lines) + "\n"

def test_get_members_parses_output():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=make_ipset_list_output(["1.2.3.4", "5.6.7.8"])
        )
        result = ipset_manager.get_members("doprax")
    assert result == {"1.2.3.4", "5.6.7.8"}

def test_get_members_returns_empty_on_missing_ipset():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = ipset_manager.get_members("doprax")
    assert result == set()

def test_sync_ips_adds_and_removes():
    current = {"1.1.1.1", "2.2.2.2"}
    desired = {"2.2.2.2", "3.3.3.3"}
    calls = []
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=make_ipset_list_output(["1.1.1.1","2.2.2.2"]))
        with patch.object(ipset_manager, "add_ip") as mock_add, \
             patch.object(ipset_manager, "remove_ip") as mock_del, \
             patch.object(ipset_manager, "ensure_ipset"):
            added, removed = ipset_manager.sync_ips("doprax", desired)
    assert added == {"3.3.3.3"}
    assert removed == {"1.1.1.1"}
