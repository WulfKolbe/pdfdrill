"""Two reported bugs:

1. A path argument starting with `~/` (the shell `$HOME` shorthand) must resolve
   like the absolute form. `pdfdrill <cmd> ~/x.pdf` used to fail with
   "Not found: ~/x.pdf" while `/home/me/x.pdf` worked, because neither
   `cli._pdf` nor `sources.resolve_input` expanded `~`.
2. `pdfdrill md` on a scanned (needs_ocr) doc returned a *discussion* about how
   to OCR even when MathPix credentials are configured. When keys are present it
   must just RUN MathPix and return the markdown — no discussion.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# --------------------------------------------------------------------------- #
# 1. tilde expansion
# --------------------------------------------------------------------------- #

def test_cli_pdf_expands_tilde():
    from pdfdrill import cli
    old = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as d:
        os.environ["HOME"] = d
        try:
            f = Path(d) / "doc.pdf"
            f.write_bytes(b"%PDF-1.4")
            assert cli._pdf(["~/doc.pdf"]) == f
            # and the absolute form still works
            assert cli._pdf([str(f)]) == f
        finally:
            if old is not None:
                os.environ["HOME"] = old


def test_resolve_input_expands_tilde():
    from pdfdrill import sources as S
    old = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as d:
        os.environ["HOME"] = d
        try:
            f = Path(d) / "paper.pdf"
            f.write_bytes(b"%PDF-1.4")
            out = S.resolve_input("~/paper.pdf")
            assert out["path"] == f and out["source"] is None
        finally:
            if old is not None:
                os.environ["HOME"] = old


# --------------------------------------------------------------------------- #
# 2. md serves the result when MathPix keys exist
# --------------------------------------------------------------------------- #

def test_mathpix_creds_available_reflects_env():
    from pdfdrill import mathpix_creds
    saved = {k: os.environ.get(k) for k in ("MATHPIX_APP_ID", "MATHPIX_APP_KEY")}
    try:
        os.environ["MATHPIX_APP_ID"] = "id"
        os.environ["MATHPIX_APP_KEY"] = "key"
        assert mathpix_creds.available() is True
        del os.environ["MATHPIX_APP_KEY"]
        assert mathpix_creds.available() is False
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_md_runs_mathpix_when_keys_present_no_discussion():
    """needs_ocr + no <stem>.md + creds present → md runs MathPix and returns the
    markdown, NOT the 'Run pdfdrill mathpix / ocr' hint."""
    from pdfdrill import commands, mathpix_creds
    from pdfdrill.sidecar import Sidecar

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "scan_front.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        sc = Sidecar(pdf)
        sc.add_fact(commands.SIZE_KNOWN)
        sc.add_fact(commands.FONTS_KNOWN)
        sc.set_evidence("needs_ocr", True)
        sc.save()

        # MathPix "produces" the .md next to the PDF.
        def fake_mathpix(p, force=False):
            (p.parent / f"{p.stem}.md").write_text("# Title\n\nReal OCR markdown body.\n")
            return "ok"

        real_avail = mathpix_creds.available
        real_mpx = commands.cmd_mathpix
        mathpix_creds.available = lambda: True
        commands.cmd_mathpix = fake_mathpix
        try:
            out = commands.cmd_md(pdf)
        finally:
            mathpix_creds.available = real_avail
            commands.cmd_mathpix = real_mpx

        assert "Real OCR markdown" in out or "MathPix OCR" in out, out
        assert "Run `pdfdrill mathpix" not in out, out
        assert "keyless tesseract" not in out, out


def test_md_keeps_hint_when_no_keys():
    """needs_ocr + no md + NO creds → still the actionable hint (unchanged)."""
    from pdfdrill import commands, mathpix_creds
    from pdfdrill.sidecar import Sidecar

    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "scan_front.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        sc.add_fact(commands.SIZE_KNOWN)
        sc.add_fact(commands.FONTS_KNOWN)
        sc.set_evidence("needs_ocr", True)
        sc.save()

        real_avail = mathpix_creds.available
        mathpix_creds.available = lambda: False
        try:
            out = commands.cmd_md(pdf)
        finally:
            mathpix_creds.available = real_avail
        assert "SCANNED PDF" in out and "pdfdrill" in out


if __name__ == "__main__":
    for fn in [test_cli_pdf_expands_tilde, test_resolve_input_expands_tilde,
               test_mathpix_creds_available_reflects_env,
               test_md_runs_mathpix_when_keys_present_no_discussion,
               test_md_keeps_hint_when_no_keys]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
