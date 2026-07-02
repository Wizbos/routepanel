# src/routepanel/awg.py
"""Parse and normalize WireGuard / AmneziaWG tunnel configs pasted by the user.
An imported conf becomes an *exit interface*: Table is forced off (routepanel's
routing_manager owns the fwmark rules and per-exit routing tables) and DNS is
stripped (an exit tunnel must never rewrite the host resolver)."""
from dataclasses import dataclass

class ConfError(ValueError):
    pass

# AmneziaWG 1.5/2.0 obfuscation keys ([Interface] section). Unknown keys are
# preserved verbatim -- new AWG versions add keys and we must not eat them.
AWG_INTERFACE_KEYS = {
    "Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4",
    "H1", "H2", "H3", "H4",
    "I1", "I2", "I3", "I4", "I5", "J1", "J2", "J3", "Itime",
}
_REQUIRED_INTERFACE = {"PrivateKey", "Address"}
_REQUIRED_PEER = {"PublicKey", "Endpoint"}

@dataclass
class TunnelConf:
    interface: dict
    peer: dict

    @property
    def is_awg(self) -> bool:
        return bool(AWG_INTERFACE_KEYS & self.interface.keys())

def parse_tunnel_conf(text: str) -> TunnelConf:
    sections: dict[str, dict] = {}
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip().lower()
            # A repeated section (any case: [Interface] then [interface]) must
            # not silently merge -- setdefault would let a second [interface]
            # block quietly overwrite keys from the first. Treat it as malformed.
            if name in sections:
                raise ConfError(f"duplicate [{name}] section")
            current = sections.setdefault(name, {})
            continue
        if "=" not in line or current is None:
            raise ConfError(f"unparseable line outside a section: {raw.strip()!r}")
        k, v = line.split("=", 1)
        current[k.strip()] = v.strip()
    iface, peer = sections.get("interface"), sections.get("peer")
    if not iface or not peer:
        raise ConfError("config must contain [Interface] and [Peer] sections")
    # Keys with an empty value (e.g. "PrivateKey =") are as useless as a missing
    # key -- don't let them slip past the required-key check.
    if missing := _REQUIRED_INTERFACE - {k for k, v in iface.items() if v}:
        raise ConfError(f"[Interface] missing: {', '.join(sorted(missing))}")
    if missing := _REQUIRED_PEER - {k for k, v in peer.items() if v}:
        raise ConfError(f"[Peer] missing: {', '.join(sorted(missing))}")
    return TunnelConf(interface=iface, peer=peer)

def render_exit_conf(tc: TunnelConf) -> str:
    # Strip case-insensitively -- a pasted conf with lowercase "dns"/"table" must
    # be stripped just as reliably as canonical "DNS"/"Table", or the exit iface
    # could rewrite the host resolver or fight routepanel's own routing tables.
    iface = {k: v for k, v in tc.interface.items() if k.lower() not in ("dns", "table")}
    iface["Table"] = "off"
    peer = dict(tc.peer)
    peer.setdefault("AllowedIPs", "0.0.0.0/0")
    lines = ["[Interface]"]
    lines += [f"{k} = {v}" for k, v in iface.items()]
    lines += ["", "[Peer]"]
    lines += [f"{k} = {v}" for k, v in peer.items()]
    return "\n".join(lines) + "\n"
