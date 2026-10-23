r"""`pdfdrill md` must not overwrite the MathPix markdown that was paid for.

MEASURED ON THE LIBRARY, 2026-10-23. 1,329 documents hold a sidecar record of a
bought MathPix `md` download (`evidence.mathpix_files`). 41 of those files are
no longer MathPix's: 28 were replaced by `MarkdownProjector`, 7 by the latex /
llm-compact routes, 6 by `translate` before 815 gave the bi-layer its own name.
bh2's 922,111-byte download is gone from every disk and every commit.

`cmd_md` HAD a guard for exactly this, and it never fired:

    layer = sc.get_layer("md") or {}
    if str(layer.get("source") or "") == "mathpix":
        return None                      # "A GENUINE MathPix markdown still wins"

The md LAYER is pdfdrill's own bookkeeping; the MathPix download stamps
`evidence.mathpix_files` and never touches it. On the casualties the layer read
`'latex'`, `'model'` or `None` — never `'mathpix'`. Of the 1,285 still-intact
downloads the layer protects 54; the remaining 1,231 were one `pdfdrill md`
away from the same loss.

`cmd_md`'s own summary already promised the right order — "Prefers a genuine
MathPix .md, then the model, then the text layer" — while the code called the
latex route first, the model second and the MathPix branch third. The fix is to
ask the record that actually knows, and to ask it FIRST.

AND THE QUESTION IS SETTLED BY CONTENT, NOT BY A RECORD. In the self-contained
layout the download's path and the projector's target are the same file
(`<library>/<stem>/<stem>.md`), so "a file exists at the recorded path" proves
nothing about who wrote it — that is how `_serve_mathpix_md` once announced
`translate`'s bi-layer as "Markdown from MathPix" (816). Our own writers sign
their output: a YAML front matter naming the generator, or the bi-layer's
`seg source` divs. MathPix signs nothing, so absence of our signature is the
only honest test.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import commands                               # noqa: E402
from pdfdrill.sidecar import Sidecar                        # noqa: E402

MATHPIX_MD = (
    "# Introduction\n\nThe field is $E = mc^2$ and the display form is\n\n"
    "$$\n\\begin{aligned}\n& a = b \\\\\n& c = d\n\\end{aligned}\n$$\n\n"
    "![](https://cdn.mathpix.com/cropped/abc-01.jpg?height=100&width=200)\n")


def _doc_with_a_bought_md(tmp_path, *, md_text=MATHPIX_MD, bytes_recorded=None):
    """A document whose sidecar records a bought MathPix md, with that md on
    disk — the shape 1,285 library documents are in.

    `<dir>/<stem>/<stem>.pdf` ON PURPOSE: that is the self-contained layout the
    library uses, and the only one where the download's path and `_write_md`'s
    blob are the same file. In the legacy layout they are two files in two
    directories, and the collision this whole test file is about cannot happen.
    """
    home = tmp_path / "doc"
    home.mkdir(parents=True, exist_ok=True)
    pdf = home / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7 stub\n%%EOF\n")
    md = home / "doc.md"
    md.write_text(md_text, encoding="utf-8")
    sc = Sidecar(pdf)
    sc.set_evidence("pages", 3)
    sc.set_evidence("mathpix_files", [
        {"format": "lines.json", "path": "doc.lines.json", "bytes": 10},
        {"format": "md", "path": "doc.md",
         "bytes": bytes_recorded if bytes_recorded is not None
         else len(md_text.encode())},
    ])
    sc.save()
    return pdf, md


# ── the helper that answers the question ────────────────────────────────────

def test_a_bought_md_is_recognised_from_the_sidecar_record(tmp_path):
    pdf, md = _doc_with_a_bought_md(tmp_path)
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) == md


def test_our_own_projection_at_that_path_is_not_mistaken_for_it(tmp_path):
    """The file the projector wrote is NOT the bought one, however the sidecar
    still describes it — this is the 816 trap, and the only way out is the
    signature our own writers leave."""
    pdf, md = _doc_with_a_bought_md(
        tmp_path,
        md_text=("---\nbibkey: doc\ngenerator: pdfdrill MarkdownProjector\n"
                 "---\n\n# Introduction\n"))
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) is None


def test_the_bilayer_translation_at_that_path_is_not_mistaken_for_it(tmp_path):
    """What bh2 actually holds: 818 translated segments and 818 hidden German
    ones. It was once announced as "Markdown from MathPix"."""
    pdf, md = _doc_with_a_bought_md(
        tmp_path,
        md_text=('<style>.seg.source{display:none}</style>\n'
                 '<button onclick="x">Toggle DE source</button>\n\n'
                 '<div class="seg trans" lang="EN-US">\n\nhello\n\n</div>\n'
                 '<div class="seg source" lang="DE">\n\nhallo\n\n</div>\n'))
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) is None


def test_no_sidecar_record_means_no_claim(tmp_path):
    """A `<stem>.md` with nothing to say it was bought is just a markdown file;
    the routes that build one must stay free to write it."""
    home = tmp_path / "doc"
    home.mkdir(parents=True, exist_ok=True)
    pdf = home / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.7 stub\n%%EOF\n")
    (home / "doc.md").write_text("# Hand-written\n", encoding="utf-8")
    sc = Sidecar(pdf)
    sc.set_evidence("pages", 1)
    sc.save()
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) is None


def test_a_recorded_md_that_is_gone_is_not_resurrected(tmp_path):
    pdf, md = _doc_with_a_bought_md(tmp_path)
    md.unlink()
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) is None


def test_the_recorded_byte_count_is_not_the_test(tmp_path):
    """`fetch_mathpix` reports "cached" when the md merely EXISTS — only
    `.lines.json` gets a content check — so a later run can re-stamp
    `mathpix_files[md].bytes` with whatever is at the path. 93 library
    documents hold a MathPix md whose size differs from the record. Size
    cannot decide this; content can."""
    pdf, md = _doc_with_a_bought_md(tmp_path, bytes_recorded=999_999)
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) == md


# ── authorship after the format change ─────────────────────────────────────

def test_our_own_front_matterless_projection_is_still_ours(tmp_path):
    """787's own trap. Matching MathPix's format meant dropping the YAML
    `generator:` header — which WAS the signature. The first acceptance run
    after that change served a projection back as "Markdown from MathPix",
    because nothing in the file said otherwise any more. `_write_md` now
    records the sha256 of what it wrote, so the file is ours if it is still
    what we put there."""
    pdf, md = _doc_with_a_bought_md(tmp_path)
    sc = Sidecar(pdf)
    ours = "# Heading\n\nno front matter at all, just like MathPix\n"
    commands._write_md(pdf, sc, ours, source="model")
    assert md.read_text(encoding="utf-8") == ours
    assert commands._md_is_ours(md, Sidecar(pdf)) is True
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) is None


def test_a_restored_purchase_is_not_claimed_by_a_stale_digest(tmp_path):
    """The other direction, which is how a correction gets honoured: once the
    bought md is put back at that path by hand, it no longer hashes to what
    pdfdrill wrote, so it is served and never overwritten — the two files
    restored from the MathPix UI on 2026-10-23 depend on exactly this."""
    pdf, md = _doc_with_a_bought_md(tmp_path)
    commands._write_md(pdf, Sidecar(pdf), "# ours\n", source="model")
    md.write_text(MATHPIX_MD, encoding="utf-8")          # the restoration
    assert commands._md_is_ours(md, Sidecar(pdf)) is False
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) == md


def test_a_digest_for_another_file_does_not_decide_this_one(tmp_path):
    """The layer's digest describes the blob the layer NAMES. A sidecar whose
    md layer points somewhere else says nothing about this path."""
    pdf, md = _doc_with_a_bought_md(tmp_path)
    sc = Sidecar(pdf)
    sc.set_layer("md", {"blob": "something-else.md", "source": "model",
                        "sha256": "0" * 64})
    sc.save()
    assert commands._bought_mathpix_md(pdf, Sidecar(pdf)) == md


# ── and the order `cmd_md` promises ─────────────────────────────────────────

def test_the_model_route_does_not_run_while_a_bought_md_is_on_disk(
        tmp_path, monkeypatch):
    """The behaviour, not the helper: `pdfdrill md` serves the download and the
    model projection is never reached, so the file cannot be replaced."""
    pdf, md = _doc_with_a_bought_md(tmp_path)
    before = md.read_bytes()
    called: list[str] = []
    monkeypatch.setattr(commands, "_md_from_model",
                        lambda *a, **k: called.append("model") or "projected")
    monkeypatch.setattr(commands, "_md_from_latex_source",
                        lambda *a, **k: called.append("latex") or "projected")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    out = commands.cmd_md(pdf)
    assert called == [], f"a projection ran over the bought md: {called!r}"
    assert "MathPix" in out, out
    assert md.read_bytes() == before, "the bought md was rewritten"


def test_the_model_route_still_runs_when_the_md_is_our_own(tmp_path, monkeypatch):
    """The other side: once the download is gone, pdfdrill must go on building
    markdown — the guard protects a bought file, it does not disable the route."""
    pdf, md = _doc_with_a_bought_md(
        tmp_path,
        md_text="---\ngenerator: pdfdrill MarkdownProjector\n---\n\n# x\n")
    called: list[str] = []
    monkeypatch.setattr(commands, "_md_from_model",
                        lambda *a, **k: called.append("model") or "projected")
    monkeypatch.setenv("PDFDRILL_NO_PREFLIGHT", "1")
    commands.cmd_md(pdf)
    assert called == ["model"], f"the model route was skipped: {called!r}"
