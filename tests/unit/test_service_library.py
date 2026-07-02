import ipaddress, json, pathlib

LIB = pathlib.Path(__file__).parents[2] / "service_library.json"
ALLOWED_REFRESH = {"goog-json", "cidr-lines", "ripestat-as"}

def _packs():
    return json.loads(LIB.read_text())

def test_pack_shape():
    packs = _packs()
    ids = [p["id"] for p in packs]
    assert len(ids) == len(set(ids)), "duplicate pack ids"
    for p in packs:
        assert p["name"] and p["domains"], p["id"]
        for d in p["domains"]:
            assert " " not in d and "." in d and not d.startswith("http"), (p["id"], d)
        for c in p.get("cidrs", []):
            ipaddress.ip_network(c)          # raises on garbage
        if "refresh" in p:
            assert p["refresh"]["format"] in ALLOWED_REFRESH
            assert p["refresh"]["url"].startswith("https://")

def test_broad_coverage():
    ids = {p["id"] for p in _packs()}
    required = {"youtube", "google", "telegram", "instagram", "facebook", "whatsapp",
                "discord", "twitter", "tiktok", "twitch", "netflix", "spotify",
                "signal", "viber", "linkedin", "patreon", "medium", "proton",
                "openai", "anthropic", "gemini"}
    assert required <= ids, f"missing packs: {required - ids}"

def test_meta_packs_carry_cidrs():
    packs = {p["id"]: p for p in _packs()}
    for pid in ("instagram", "facebook", "whatsapp"):
        assert "157.240.0.0/16" in packs[pid]["cidrs"], pid   # Meta AS32934 backbone

def test_telegram_cidrs_present():
    packs = {p["id"]: p for p in _packs()}
    assert "91.108.4.0/22" in packs["telegram"]["cidrs"]
