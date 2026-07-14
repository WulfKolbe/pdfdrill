"""
merge_latex (src/pdfdrill/merge_latex.py): the three-source merge where LaTeX is
the CONTENT truth and MathPix is the LAYOUT truth. MathPix Paragraphs (flow
order) define the paragraph boundaries + per-paragraph `region`; the gold LaTeX
prose is re-partitioned across those boundaries by word-alignment and each
paragraph's `text` is REPLACED by its aligned LaTeX span (LaTeX always wins).
The MathPix OCR text is preserved under `text_source` for audit.

This fixes the source-build's coarse paragraphs (a 3000-char LaTeX block that
MathPix visually splits into 3-4) WITHOUT losing MathPix's geometry.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill import merge_latex as ml


def _para(pid, text, region, flow):
    return DocObject(type="Paragraph", id=pid, props={
        "text": text, "region": region, "flow_index": flow})


def test_merges_onto_pdfminer_garble_dropping_watermark():
    """The gold-LaTeX-prose merge on a BORN-DIGITAL (pdfminer) skeleton: a
    two-column paper's paragraph carries the arXiv margin watermark ("0") + column
    interleaving. The merge replaces it with clean gold LaTeX — the watermark and
    the garble are DROPPED (they came from the char layer, the gold does not)."""
    doc = Document(); doc.meta["bibkey"] = "T"; doc.meta["source"] = "pdfminer-chars"
    # a pdfminer paragraph: leading watermark glyph "0" + interleaved right-column
    # words spliced into the left-column prose (the exact failure the user saw)
    doc.add(_para("p1",
                  "0 This paper introduces a novel approach and diffusion-based "
                  "generation, there is for topic modeling", None, 1))
    gold = ("This paper introduces a novel approach for topic modeling utilizing "
            "latent codebooks from Vector-Quantized Variational Auto-Encoder.")
    n = ml.merge_latex_prose(doc, gold)
    assert n == 1
    txt = doc.objects["p1"].props["text"]
    assert txt == gold                                   # clean gold, in reading order
    assert not txt.split()[0] == "0"                     # watermark dropped
    assert "diffusion-based" not in txt                  # interleaved garble dropped
    assert doc.objects["p1"].props["text_source"].startswith("0 This")  # original saved
    assert doc.objects["p1"].props["merged_from"] == "latex"


def test_gold_prose_repartitioned_at_mathpix_boundaries():
    """MathPix says 3 short (OCR-garbled) paragraphs; the gold LaTeX is one blob.
    After merge there are still 3 paragraphs, each carrying its aligned CLEAN gold
    span + its own MathPix region — the coarse LaTeX block is re-split by MathPix
    geometry and the OCR errors are corrected."""
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(_para("p1", "The quiok brown fox", {"top_left_x": 1}, 1))
    doc.add(_para("p2", "jumps over the Iazy", {"top_left_x": 2}, 2))
    doc.add(_para("p3", "dog and runs awoy", {"top_left_x": 3}, 3))
    gold = "The quick brown fox jumps over the lazy dog and runs away."
    n = ml.merge_latex_prose(doc, gold)
    assert n == 3
    assert doc.objects["p1"].props["text"].strip() == "The quick brown fox"
    assert doc.objects["p2"].props["text"].strip() == "jumps over the lazy"
    assert doc.objects["p3"].props["text"].strip() == "dog and runs away."
    # regions preserved (MathPix layout truth), OCR kept for audit
    assert doc.objects["p2"].props["region"] == {"top_left_x": 2}
    assert doc.objects["p1"].props["text_source"] == "The quiok brown fox"


def test_latex_wins_over_ocr_errors():
    """Where the OCR garbled a word, the aligned gold word replaces it."""
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(_para("p1", "The quiok brown f0x", {"top_left_x": 1}, 1))
    gold = "The quick brown fox"
    ml.merge_latex_prose(doc, gold)
    assert doc.objects["p1"].props["text"].strip() == "The quick brown fox"
    assert doc.objects["p1"].props["text_source"] == "The quiok brown f0x"


def test_unmatched_paragraph_keeps_mathpix_text():
    """A MathPix paragraph with no counterpart in the LaTeX prose (e.g. a figure
    caption OCR'd as a paragraph) is NOT blanked — LaTeX wins only where it has
    text; the region and original text stay."""
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(_para("p1", "We prove the theorem below", {"top_left_x": 1}, 1))
    doc.add(_para("cap", "Figure 7: an unrelated caption xyzzy", {"top_left_x": 9}, 2))
    doc.add(_para("p2", "which follows directly", {"top_left_x": 2}, 3))
    gold = "We prove the theorem below which follows directly."
    ml.merge_latex_prose(doc, gold)
    # the caption paragraph has no gold span → unchanged, no text_source stamped
    assert doc.objects["cap"].props["text"] == "Figure 7: an unrelated caption xyzzy"
    assert "text_source" not in doc.objects["cap"].props
    assert doc.objects["p1"].props["text"].strip().startswith("We prove the theorem")


def test_idempotent_second_run_no_change():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(_para("p1", "alpha bet4", {"top_left_x": 1}, 1))     # 1 garble, clean anchor
    doc.add(_para("p2", "gamma delt4", {"top_left_x": 2}, 2))
    gold = "alpha beta gamma delta"
    assert ml.merge_latex_prose(doc, gold) == 2
    # second run: text already == gold span → no change (idempotent)
    assert ml.merge_latex_prose(doc, gold) == 0


def test_latex_prose_from_body_strips_structure_and_markup():
    """The gold-prose extractor drops display math / floats / sectioning and
    unwraps text markup, keeping inline math as \\(..\\) (MathPix convention)."""
    body = (
        "\\section{Intro}\n"
        "We \\emph{prove} that \\(x>0\\) using \\cite{smith2020}.\n"
        "\\begin{equation} a=b \\end{equation}\n"
        "The \\textbf{result} follows.\\label{eq:r}\n"
        "\\begin{figure} \\includegraphics{f.png} \\end{figure}\n"
    )
    prose = ml.latex_prose_from_body(body)
    assert "prove" in prose and "result follows" in prose
    assert "\\emph" not in prose and "\\textbf" not in prose
    assert "\\section" not in prose and "Intro" not in prose      # heading dropped
    assert "a=b" not in prose                                     # display math dropped
    assert "\\cite" not in prose and "\\label" not in prose
    assert "\\(x>0\\)" in prose                                   # inline math kept


def _pdfminer_model(pdf, source="pdfminer-chars"):
    """A minimal built model with the given meta source + a garbled Paragraph."""
    import json
    from pdfdrill import commands as C
    from pdfdrill.sidecar import Sidecar
    d = Document(); d.meta["bibkey"] = "paper"; d.meta["source"] = source
    d.add(_para("p1", "0 The quiok brown fox jumps", None, 1))
    sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
    mp = C._model_path(sc)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(d.to_dict(), f)
    sc.add_fact(C.MODEL_BUILT); sc.save()
    return mp


def test_cmd_merge_accepts_pdfminer_model(tmp_path):
    """The gate is relaxed: a born-digital pdfminer model IS a valid merge
    skeleton (its prose is garbled). A local .tex supplies the gold prose."""
    from pdfdrill import commands as C
    pdf = tmp_path / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4")
    tex = tmp_path / "paper.tex"
    tex.write_text("\\documentclass{article}\\begin{document}\n"
                   "The quick brown fox jumps over the lazy dog.\n"
                   "\\end{document}\n")
    _pdfminer_model(pdf)
    out = C.cmd_merge(pdf, tex=str(tex))
    assert "born-digital (pdfminer)" in out and "got gold text" in out
    from pdfdrill.model_io import load_model
    doc = load_model(C._model_path(C.Sidecar(pdf)))
    p = next(iter(doc.objects_of_type("Paragraph")))
    assert p.props["text"].startswith("The quick brown fox")   # gold, watermark gone
    assert p.props.get("text_source", "").startswith("0 The quiok")


def test_cmd_merge_refuses_source_built_model(tmp_path):
    """A model built FROM LaTeX already has gold prose — refuse (nothing to fix)."""
    from pdfdrill import commands as C
    pdf = tmp_path / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4")
    tex = tmp_path / "paper.tex"; tex.write_text("x")
    _pdfminer_model(pdf, source="latex")
    out = C.cmd_merge(pdf, tex=str(tex))
    assert "already the gold text" in out


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
