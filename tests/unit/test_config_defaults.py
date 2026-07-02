from routepanel.config import Config

def test_oss_defaults():
    c = Config()
    assert c.bind_host == "127.0.0.1"
    assert c.client_interfaces == ["awg0"]
    assert c.default_exit_id == ""
    assert c.password_file == "/etc/routepanel/panel.passwd"
    assert c.exit_conf_dir == "/etc/routepanel/exits"
    assert c.awg_conf_path == "/etc/amnezia/amneziawg/awg0.conf"
    assert c.awg_interface == "awg0"
    assert not hasattr(c, "agh_targets")
    assert not hasattr(c, "dnsmasq_forward_target")

def test_ru_direct_defaults_off():
    c = Config()
    assert c.ru_direct is False
    assert c.ru_direct_url.startswith("https://")
