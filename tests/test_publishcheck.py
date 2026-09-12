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
    # 677 — the status SAYS which candidate matched. A check that does not
    # know which file it matched cannot tell a publish from a coincidence.
    assert pc.compare_document(local, remote) == [
        ("residuals.pdf", "same", "original")]


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


def test_either_candidate_may_match_and_the_status_names_which(tmp_path):
    """677 — 634's `published/` /ebook derivative used to WIN over the
    original unconditionally. 655's size budget made the originals fit, the
    publish went back to copying them, and the derivatives rotted on disk —
    so preferring them meant comparing the site against a file nothing had
    published in weeks, and reporting twelve current documents as STALE.
    Neither is preferred now: both are hashed and the answer says which."""
    local, remote = tmp_path / "L", tmp_path / "R"
    (local / "published").mkdir(parents=True)
    remote.mkdir()
    (local / "residuals.pdf").write_bytes(b"original")
    (local / "published" / "residuals.pdf").write_bytes(b"derivative")

    (remote / "residuals.pdf").write_bytes(b"derivative")
    assert pc.compare_document(local, remote)[0] == (
        "residuals.pdf", "same", "published/ derivative")

    (remote / "residuals.pdf").write_bytes(b"original")
    assert pc.compare_document(local, remote)[0] == (
        "residuals.pdf", "same", "original")

    (remote / "residuals.pdf").write_bytes(b"neither")
    assert pc.compare_document(local, remote)[0][1] == "stale"


def test_a_derivative_that_differs_from_its_original_is_reported(tmp_path):
    """The leftover is a finding in its own right, separate from the publish
    verdict: it is what made this tool measure the wrong file."""
    local, remote = tmp_path / "L", tmp_path / "R"
    (local / "published").mkdir(parents=True)
    remote.mkdir()
    (local / "residuals.pdf").write_bytes(b"original")
    (local / "published" / "residuals.pdf").write_bytes(b"derivative")
    (remote / "residuals.pdf").write_bytes(b"original")
    rows = pc.compare_document(local, remote)
    assert [r[1] for r in rows] == ["same", "stale_derivative"]


def test_a_derivative_identical_to_its_original_is_not_a_leftover(tmp_path):
    """The control: only a DIFFERING derivative is reported."""
    local, remote = tmp_path / "L", tmp_path / "R"
    (local / "published").mkdir(parents=True)
    remote.mkdir()
    for p in (local / "residuals.pdf", local / "published" / "residuals.pdf",
              remote / "residuals.pdf"):
        p.write_bytes(b"same bytes")
    assert [r[1] for r in pc.compare_document(local, remote)] == ["same"]


def test_a_book_resolves_by_its_tiddlers_file_not_by_its_folder_name(tmp_path):
    """677 — the defect that had never checked eight of twenty documents.

    462 renamed nine bibkeys without renaming their folders, so the site
    slug `voloshin-hypergraph` names a folder called `Introduction to Graph
    and Hypergraph Theory (Vitaly I. Voloshin) (Z-Library)`. Resolving
    `<library>/<slug>` found nothing, reported "NO LOCAL BUILD", and printed
    a verdict anyway. `<bibkey>.tiddlers.json` is beside every document and
    its stem IS the slug.
    """
    lib = tmp_path / "library"
    book = lib / "Introduction to Graph and Hypergraph Theory (V. I.) (Z-Lib)"
    book.mkdir(parents=True)
    (book / "voloshin-hypergraph.tiddlers.json").write_text("[]")
    arxiv = lib / "0902.0431"
    arxiv.mkdir()

    found, unresolved = pc.resolve_folders(
        lib, ["voloshin-hypergraph", "0902.0431"])
    assert found["voloshin-hypergraph"] == book, "the book did not resolve"
    assert found["0902.0431"] == arxiv, "a folder named for its slug regressed"
    assert unresolved == []


def test_a_slug_that_resolves_to_nothing_is_named(tmp_path):
    """It must not be indistinguishable from a document with no build."""
    lib = tmp_path / "library"
    lib.mkdir()
    found, unresolved = pc.resolve_folders(lib, ["ghost-document"])
    assert found == {}
    assert unresolved == ["ghost-document"]
