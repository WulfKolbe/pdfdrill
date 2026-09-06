"""publishcheck compares the FIVE published files (gate.PUBLISHED_FILES), not
just report.pdf (task 9). `compare_document` is the pure, network-free half —
it takes two directories already on disk and reports per-file status, so it
is exercised directly rather than through `main()`, which clones a site over
the network and is not run in tests.
"""
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
_spec = importlib.util.spec_from_file_location("publishcheck", TOOLS / "publishcheck.py")
pc = importlib.util.module_from_spec(_spec)
sys.modules["publishcheck"] = pc
_spec.loader.exec_module(pc)


def _write(d, name, content=b"%PDF-1.4\n"):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(content)


def test_only_locally_present_files_are_compared(tmp_path):
    local, remote = tmp_path / "local", tmp_path / "remote"
    _write(local, "residuals.pdf", b"A")
    # nothing else present locally — the other four files are not this
    # document's build and must not be reported on at all.
    results = pc.compare_document(local, remote)
    assert [r[0] for r in results] == ["residuals.pdf"]


def test_matching_file_is_same(tmp_path):
    local, remote = tmp_path / "local", tmp_path / "remote"
    _write(local, "residuals.pdf", b"A")
    _write(remote, "residuals.pdf", b"A")
    assert pc.compare_document(local, remote) == [("residuals.pdf", "same", "")]


def test_differing_bytes_is_stale(tmp_path):
    local, remote = tmp_path / "local", tmp_path / "remote"
    _write(local, "residuals.pdf", b"A")
    _write(remote, "residuals.pdf", b"B")
    fname, status, detail = pc.compare_document(local, remote)[0]
    assert fname == "residuals.pdf" and status == "stale" and detail


def test_missing_on_site_is_not_published(tmp_path):
    local, remote = tmp_path / "local", tmp_path / "remote"
    remote.mkdir()
    _write(local, "residuals.pdf", b"A")
    assert pc.compare_document(local, remote) == [("residuals.pdf", "not_published", "")]


def test_all_five_present_and_matching(tmp_path):
    local, remote = tmp_path / "local", tmp_path / "remote"
    for f in pc.gate.PUBLISHED_FILES:
        _write(local, f, b"same-bytes")
        _write(remote, f, b"same-bytes")
    results = pc.compare_document(local, remote)
    assert len(results) == len(pc.gate.PUBLISHED_FILES)
    assert all(status == "same" for _, status, _ in results)


def test_a_published_derivative_is_what_the_site_must_match(tmp_path):
    """634 — <doc>/published/<f> (the /ebook copy) wins over the original."""
    local, remote = tmp_path / "L", tmp_path / "R"
    (local / "published").mkdir(parents=True)
    remote.mkdir()
    (local / "residuals.pdf").write_bytes(b"original")
    (local / "published" / "residuals.pdf").write_bytes(b"derivative")
    (remote / "residuals.pdf").write_bytes(b"derivative")
    assert pc.compare_document(local, remote) == [("residuals.pdf", "same", "")]
    (remote / "residuals.pdf").write_bytes(b"original")
    assert pc.compare_document(local, remote)[0][1] == "stale"
