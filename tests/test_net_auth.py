"""
net.apply_credentials — HTTP Basic auth for an auth-walled host (the
sensorcloud.ddns.net stress pool: the WHOLE host sits behind Basic realm
"Ideen Sammler", so every download 401s). Credentials come, in order, from:
  * a matching `.netrc` machine entry (the standard, host-keyed mechanism), or
  * env PDFDRILL_HTTP_USER / PDFDRILL_HTTP_PASSWORD, applied only to the host in
    PDFDRILL_HTTP_AUTH_HOST when that is set (else to any host).
No creds → the Request is untouched (unchanged behavior). An already-present
Authorization header is never overwritten.
"""
import base64
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import net


def _auth_of(req):
    return req.get_header("Authorization")


def _expected(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def test_no_credentials_no_header(monkeypatch):
    for k in ("PDFDRILL_HTTP_USER", "PDFDRILL_HTTP_PASSWORD",
              "PDFDRILL_HTTP_AUTH_HOST"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(net, "_netrc_auth", lambda host: None)
    req = urllib.request.Request("https://sensorcloud.ddns.net/pdffiles/x.pdf")
    out = net.apply_credentials(req, host="sensorcloud.ddns.net")
    assert _auth_of(out) is None


def test_env_credentials_unscoped(monkeypatch):
    monkeypatch.setenv("PDFDRILL_HTTP_USER", "ideen")
    monkeypatch.setenv("PDFDRILL_HTTP_PASSWORD", "s3cret")
    monkeypatch.delenv("PDFDRILL_HTTP_AUTH_HOST", raising=False)
    monkeypatch.setattr(net, "_netrc_auth", lambda host: None)
    req = urllib.request.Request("https://sensorcloud.ddns.net/pdffiles/x.pdf")
    out = net.apply_credentials(req, host="sensorcloud.ddns.net")
    assert _auth_of(out) == _expected("ideen", "s3cret")


def test_env_credentials_host_scoped(monkeypatch):
    monkeypatch.setenv("PDFDRILL_HTTP_USER", "ideen")
    monkeypatch.setenv("PDFDRILL_HTTP_PASSWORD", "s3cret")
    monkeypatch.setenv("PDFDRILL_HTTP_AUTH_HOST", "sensorcloud.ddns.net")
    monkeypatch.setattr(net, "_netrc_auth", lambda host: None)
    # matching host → header
    good = net.apply_credentials(
        urllib.request.Request("https://sensorcloud.ddns.net/pdffiles/x.pdf"),
        host="sensorcloud.ddns.net")
    assert _auth_of(good) == _expected("ideen", "s3cret")
    # different host → NO header (creds are scoped)
    other = net.apply_credentials(
        urllib.request.Request("https://arxiv.org/pdf/2401.00001.pdf"),
        host="arxiv.org")
    assert _auth_of(other) is None


def test_netrc_credentials(monkeypatch):
    for k in ("PDFDRILL_HTTP_USER", "PDFDRILL_HTTP_PASSWORD",
              "PDFDRILL_HTTP_AUTH_HOST"):
        monkeypatch.delenv(k, raising=False)
    with tempfile.TemporaryDirectory() as d:
        nrc = Path(d) / ".netrc"
        nrc.write_text("machine sensorcloud.ddns.net login ideen password s3cret\n")
        nrc.chmod(0o600)
        monkeypatch.setenv("NETRC", str(nrc))
        req = urllib.request.Request("https://sensorcloud.ddns.net/pdffiles/x.pdf")
        out = net.apply_credentials(req, host="sensorcloud.ddns.net")
        assert _auth_of(out) == _expected("ideen", "s3cret")
        # a host absent from .netrc gets nothing
        other = net.apply_credentials(
            urllib.request.Request("https://example.com/x.pdf"),
            host="example.com")
        assert _auth_of(other) is None


def test_existing_authorization_not_overwritten(monkeypatch):
    monkeypatch.setenv("PDFDRILL_HTTP_USER", "ideen")
    monkeypatch.setenv("PDFDRILL_HTTP_PASSWORD", "s3cret")
    monkeypatch.delenv("PDFDRILL_HTTP_AUTH_HOST", raising=False)
    monkeypatch.setattr(net, "_netrc_auth", lambda host: None)
    req = urllib.request.Request("https://sensorcloud.ddns.net/x.pdf",
                                 headers={"Authorization": "Bearer keepme"})
    out = net.apply_credentials(req, host="sensorcloud.ddns.net")
    assert _auth_of(out) == "Bearer keepme"


if __name__ == "__main__":
    import types
    class MP:
        def __init__(self): self._env = {}
        def setenv(self, k, v): import os; os.environ[k] = v
        def delenv(self, k, raising=True): import os; os.environ.pop(k, None)
        def setattr(self, obj, name, val): setattr(obj, name, val)
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t(MP()); print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
