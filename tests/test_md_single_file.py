"""
Markdown is ONE canonical file per doc: `<bibkey>.md`.

Previously `md` wrote the SAME markdown twice — the internal `md.md` blob (read by
fetch/toc/abstract/render) AND a findable `<bibkey>.md` copy. Two byte-identical
files per doc. Now `<bibkey>.md` is the single source; the ~10 internal readers
read it, with a fallback to the legacy `md.md` blob so folders drilled before the
change still work.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C
from pdfdrill.sidecar import Sidecar


def _sc(tmp_path):
    pdf = tmp_path / "2603.16021v2.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    return pdf, Sidecar(pdf)


def test_write_md_writes_only_the_named_file(tmp_path):
    pdf, sc = _sc(tmp_path)
    note = C._write_md(pdf, sc, "# hello\n\nworld", source="mathpix")
    named = sc.blob_dir / "2603.16021v2.md"
    assert named.exists() and named.read_text() == "# hello\n\nworld"
    assert not (sc.blob_dir / "md.md").exists(), "no duplicate md.md"
    assert "2603.16021v2.md" in note                      # findable-path note
    layer = sc.get_layer("md") if hasattr(sc, "get_layer") else sc.layers.get("md")
    assert layer and layer["blob"] == "2603.16021v2.md"


def test_read_md_reads_the_named_file(tmp_path):
    pdf, sc = _sc(tmp_path)
    C._write_md(pdf, sc, "canonical body", source="mathpix")
    assert C._read_md(pdf, sc) == "canonical body"


def test_read_md_falls_back_to_legacy_md_md(tmp_path):
    """A folder drilled BEFORE the consolidation has only the md.md blob."""
    pdf, sc = _sc(tmp_path)
    sc.write_blob("md.md", "legacy body")               # no <bibkey>.md
    assert not (sc.blob_dir / "2603.16021v2.md").exists()
    assert C._read_md(pdf, sc) == "legacy body"


def test_read_md_prefers_named_over_legacy(tmp_path):
    pdf, sc = _sc(tmp_path)
    sc.write_blob("md.md", "stale legacy")
    C._write_md(pdf, sc, "fresh canonical", source="mathpix")
    assert C._read_md(pdf, sc) == "fresh canonical"


def test_read_md_none_when_absent(tmp_path):
    pdf, sc = _sc(tmp_path)
    assert C._read_md(pdf, sc) is None
