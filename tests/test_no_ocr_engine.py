"""pdfdrill runs no OCR engine, and the ways it could come back.

tesseract was removed from the distribution (`docs/LANES.md`). The removal is
not one deletion but a shape: no module may invoke an OCR binary, no install
step may pull one in, `doctor` may not ask for one, and every feature that used
to get its word boxes from one must get them from the document instead. Each of
those is one assertion here, because a re-added `subprocess.run(["tesseract",
...])` compiles, passes every other test, and silently re-introduces a lane
nobody chose.

The file this replaced asserted that the OCR renderer went through the single
rasterizer and asked for grayscale. There is no OCR renderer left to hold to
that, so the grayscale claim is kept here for the renderers that remain.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Engines, not words: `tesseract` in a docstring is history and allowed; the
# binary NAME in an argv list is the thing that must not reappear.
ENGINE_BINARIES = ("tesseract", "ocrmypdf", "easyocr", "paddleocr", "gocr",
                   "cuneiform", "kraken", "calamari-predict")


def _py_sources() -> list[Path]:
    return [p for p in (ROOT / "src").rglob("*.py")]


def test_no_module_invokes_or_probes_an_ocr_binary():
    """Two shapes and no others: the head of an argv list handed to subprocess,
    and a `which()` probe for the binary.

    Deliberately NOT a plain substring search. `_KEYLESS_TEXTONLY_SOURCES`
    contains the string "tesseract" because a lines.json written years ago says
    that in its `source` field, and reading an old artifact is not running an
    engine. The two shapes below are.
    """
    offenders: list[str] = []
    for path in _py_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        for engine in ENGINE_BINARIES:
            e = re.escape(engine)
            argv = r"""(?:run|Popen|call|check_output|check_call)\(\s*\[\s*["']%s["']""" % e
            probe = r"""which\(\s*["']%s["']""" % e
            for pattern, what in ((argv, "argv"), (probe, "which")):
                if re.search(pattern, text):
                    offenders.append(f"{path.relative_to(ROOT)}: {engine} ({what})")
    assert not offenders, (
        "an OCR engine is being invoked again: " + "; ".join(offenders))


def test_bootstrap_installs_no_ocr_engine():
    text = (ROOT / "bootstrap.sh").read_text(encoding="utf-8")
    pkgs = re.findall(r"PKGS\+=\(([^)]*)\)", text)
    for group in pkgs:
        for engine in ENGINE_BINARIES:
            assert engine not in group, f"bootstrap.sh installs {engine}: {group}"


def test_doctor_does_not_ask_for_an_ocr_engine():
    from pdfdrill.commands import cmd_doctor
    out = cmd_doctor()
    assert "tesseract" not in out.lower(), out
    # and it says so positively, so a reader is not left wondering
    assert "no OCR engine" in out, out


def test_the_retired_verb_names_the_lane(tmp_path, monkeypatch):
    """`pdfdrill ocr <pdf>` still answers: three CLI sessions and three chat
    sessions know the name, and `Unknown command` is a worse answer than the
    contract."""
    from pdfdrill import cli
    from pdfdrill.commands import cmd_ocr
    assert "ocr" in cli.HANDLERS            # the verb is kept on purpose

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    out = cmd_ocr(pdf)
    assert "RETIRED" in out
    assert "gemmaocr" in out and "--geometry-only" in out
    assert "install" not in out.lower(), "a retired lane must not advise an install"


def test_the_retired_verb_writes_nothing(tmp_path):
    from pdfdrill.commands import cmd_ocr
    pdf = tmp_path / "y.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    before = sorted(p.name for p in tmp_path.iterdir())
    cmd_ocr(pdf)
    after = sorted(p.name for p in tmp_path.iterdir())
    # a sidecar may appear (route records its probe); a lines.json may not
    assert not any(n.endswith(".lines.json") for n in after), after
    assert "y.pdf" in before and "y.pdf" in after


def test_no_words_note_names_a_lane_and_never_an_install(tmp_path):
    from pdfdrill import word_boxes
    note = word_boxes.no_words_note(tmp_path / "scan.pdf")
    assert "gemmaocr" in note and "--geometry-only" in note
    assert "route" in note
    for forbidden in ("apt", "install", "tesseract"):
        assert forbidden not in note.lower(), note


def test_a_pdf_with_no_text_layer_yields_no_word_boxes(tmp_path, monkeypatch):
    from pdfdrill import word_boxes
    monkeypatch.setattr(word_boxes, "text_layer_tsv", lambda *a, **k: "")
    words, dims, src = word_boxes.words_for(tmp_path / "scan.pdf")
    assert words == [] and dims == {} and src == word_boxes.NONE


def test_renderers_that_feed_a_reader_still_ask_for_grayscale(monkeypatch, tmp_path):
    """The measurement that justified grayscale outlived the engine: scored
    against the born-digital text layer on pages 8-15 of the Infineon handbook,
    pnggray was 91.14% against png16m's 91.29% — no fidelity cost — for 2.5x
    less render and read time. The reader that renders pages today is the gemma
    lane, so it is the one held to it."""
    from pdfdrill import gemma_reader, pdf_reading
    seen: list[bool] = []

    def fake(pdf, out_dir, *, pages=None, dpi=400, fmt="png", gray=False,
             **kw):
        seen.append(gray)
        return []

    monkeypatch.setattr(pdf_reading, "rasterize", fake)
    src = (ROOT / "src/pdfdrill/gemma_reader.py").read_text(encoding="utf-8")
    call = src[src.index("sheets = pdf_reading.rasterize("):][:220]
    assert "gray=True" in call, call
