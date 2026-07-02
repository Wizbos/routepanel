# src/routepanel/config.py
from dataclasses import dataclass, field
import os, yaml

@dataclass
class Config:
    bind_host: str = "10.255.99.30"
    port: int = 8080
    db_path: str = "/etc/routepanel/db.sqlite"
    ipsets_save_path: str = "/etc/routepanel/ipsets.save"
    poll_interval: int = 300
    health_interval: int = 30
    health_latency_threshold_ms: float = 200.0
    health_down_threshold: int = 3
    health_up_threshold: int = 3          # consecutive successes before DOWN->UP (anti-flap)
    failback_min_dwell_sec: int = 300     # stay on fallback this long before returning to recovered primary
    default_exit_id: str = "doprax"       # catch-all exit; failover-aware via its fallback chain
    client_interfaces: list = field(default_factory=lambda: ["awg0","docker0","amn0","wg-vermont"])
    frr_next_hop: str = "Null0"
    wan_interface: str = "eth0"   # direct-exit (OSPF-distributed) traffic is MASQUERADEd out this iface
    dns_intercept: bool = True
    dnsmasq_conf_path: str = "/etc/routepanel/dnsmasq-routepanel.conf"
    dnsmasq_service: str = "dnsmasq"
    ospf_debounce_sec: int = 60
    max_ospf_ips_per_rule: int = 64
    resolved_ip_ttl_days: int = 7
    ipset_timeout_sec: int = 86400   # per-member ipset timeout (auto-expiry)
    resolver_address: str = "127.0.0.1"   # daemon resolves via the VPS dnsmasq (same answers clients get)
    resolver_port: int = 5353
    dnsmasq_forward_target: str = "10.255.99.30:5353"   # what site AGHs forward routed domains to
    agh_targets: list = field(default_factory=list)     # [{name,url,user,password}]; empty = no AGH push
    auth_token: str = ""

_config: Config | None = None

def get_config() -> Config:
    global _config
    if _config is None:
        path = os.environ.get("ROUTEPANEL_CONFIG", "/etc/routepanel/config.yaml")
        _config = _load(path)
    return _config

def reset_config() -> None:
    global _config
    _config = None

def _load(path: str) -> Config:
    if not os.path.exists(path):
        return Config()
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    valid = {f for f in Config.__dataclass_fields__}
    return Config(**{k: v for k, v in data.items() if k in valid})
