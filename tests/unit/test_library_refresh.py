import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parents[2] / "scripts"))
import library_refresh

def test_goog_json():
    payload = json.dumps({"prefixes": [
        {"ipv4Prefix": "8.8.8.0/24"}, {"ipv6Prefix": "2001:4860::/32"}]})
    got = library_refresh.fetch_cidrs(
        {"refresh": {"format": "goog-json", "url": "https://x"}}, fetch=lambda url: payload)
    assert got == ["8.8.8.0/24"]

def test_cidr_lines_skips_garbage_and_v6():
    payload = "91.108.4.0/22\n# comment\n2001:b28::/32\nnot-a-cidr\n149.154.160.0/20\n"
    got = library_refresh.fetch_cidrs(
        {"refresh": {"format": "cidr-lines", "url": "https://x"}}, fetch=lambda url: payload)
    assert got == ["91.108.4.0/22", "149.154.160.0/20"]

def test_ripestat_as():
    payload = json.dumps({"data": {"prefixes": [
        {"prefix": "157.240.0.0/16"}, {"prefix": "2a03:2880::/32"}]}})
    got = library_refresh.fetch_cidrs(
        {"refresh": {"format": "ripestat-as", "url": "https://x"}}, fetch=lambda url: payload)
    assert got == ["157.240.0.0/16"]
