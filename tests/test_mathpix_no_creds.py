"""Without credentials, `upload_pdf` must fail BEFORE touching the file.

It logged "Uploading <path>..." and then streamed the entire PDF into a
temporary multipart body — copying the whole document to disk — before the POST
was rejected for missing credentials. On a keyless batch that is a full copy of
every book for nothing, and the log line says "Uploading" for a request that
cannot be made, which reads exactly like a paid upload in progress.

Found while watching a 2653-document rebuild print "Uploading …" per document
under an environment with no keys at all.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pdfdrill.mathpix_client as MC


def test_no_creds_raises_before_reading_the_file(tmp_path, monkeypatch):
    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 1_000_000)
    monkeypatch.setattr(MC, "_creds", lambda: ("", ""))

    opened = []
    real_open = open

    def watched_open(p, *a, **k):
        opened.append(str(p))
        return real_open(p, *a, **k)

    monkeypatch.setattr("builtins.open", watched_open)
    logged = []
    try:
        MC.upload_pdf(str(pdf), log=logged.append)
        raised = False
    except Exception:
        raised = True

    assert raised, "must refuse without credentials"
    assert not any(str(pdf) in o for o in opened), \
        f"the PDF was read before the credential check: {opened[:3]}"
    assert not any("Uploading" in m for m in logged), \
        f"claimed to be uploading with no credentials: {logged}"


def test_with_creds_it_still_proceeds(tmp_path, monkeypatch):
    """The guard must not block a configured run — it only short-circuits the
    case that could never have worked."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(MC, "_creds", lambda: ("id", "key"))
    logged = []
    try:
        MC.upload_pdf(str(pdf), log=logged.append)
    except Exception:
        pass                                  # the network call is expected to fail here
    assert any("Uploading" in m for m in logged), logged
