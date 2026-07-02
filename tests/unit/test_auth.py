import time
from routepanel.panel import auth

def test_password_roundtrip():
    stored = auth.hash_password("s3cret")
    assert stored.startswith("pbkdf2_sha256$600000$")
    assert auth.verify_password("s3cret", stored)
    assert not auth.verify_password("wrong", stored)

def test_session_roundtrip():
    stored = auth.hash_password("s3cret")
    tok = auth.make_session(stored)
    assert auth.check_session(tok, stored)
    assert not auth.check_session(tok + "x", stored)            # tampered
    assert not auth.check_session(tok, auth.hash_password("s3cret"))  # new salt = password change -> invalid

def test_expired_session():
    stored = auth.hash_password("s3cret")
    tok = auth.make_session(stored, ttl_sec=-1)
    assert not auth.check_session(tok, stored)

def test_read_password_file_missing(tmp_path):
    assert auth.read_password_file(str(tmp_path / "nope")) is None
