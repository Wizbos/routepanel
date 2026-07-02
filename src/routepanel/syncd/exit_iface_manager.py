# src/routepanel/syncd/exit_iface_manager.py
"""Reconcile awg-quick interfaces for imported ('awg') exits. Idempotent, called
every sync cycle: bring up rpx* interfaces whose exit row exists, tear down and
ARCHIVE (never delete) confs whose exit row is gone."""
import logging, os, shutil, subprocess, time

log = logging.getLogger("routesyncd")

def _quick() -> str | None:
    return shutil.which("awg-quick") or shutil.which("wg-quick")

def _iface_present(name: str) -> bool:
    return subprocess.run(["ip", "link", "show", name],
                          capture_output=True, text=True).returncode == 0

def reconcile_interfaces(exits: list[dict], conf_dir: str, grace_sec: int = 600) -> None:
    quick = _quick()
    if quick is None:
        log.error("awg-quick/wg-quick not found; cannot manage exit interfaces")
        return
    want = {e["interface"]: e for e in exits if e.get("type") == "awg"}

    for iface in want:
        conf = os.path.join(conf_dir, f"{iface}.conf")
        if not os.path.exists(conf):
            log.error("exit %s: conf %s missing", iface, conf)
            continue
        if not _iface_present(iface):
            r = subprocess.run([os.path.basename(quick), "up", conf], capture_output=True, text=True)
            if r.returncode != 0:
                log.error("%s up %s failed: %s", quick, conf, r.stderr.strip())

    if os.path.isdir(conf_dir):
        for fn in os.listdir(conf_dir):
            if not (fn.startswith("rpx") and fn.endswith(".conf")):
                continue
            iface = fn[:-5]
            if iface in want:
                continue
            conf = os.path.join(conf_dir, fn)
            # A conf newer than the grace window may belong to an import that landed
            # after this cycle's exits snapshot; don't archive it yet.
            if time.time() - os.path.getmtime(conf) < grace_sec:
                continue
            subprocess.run([os.path.basename(quick), "down", conf], capture_output=True, text=True)
            ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            os.replace(conf, f"{conf}.revoked-{ts}")   # archive -- never unlink
            log.info("exit iface %s torn down; conf archived", iface)
