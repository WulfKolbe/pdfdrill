"""
Regression: running `latex` twice (once via cmd_model's auto-overlay for an arXiv
born-digital base, once explicitly) doubled every gold equation — EQ0001–14 plus
byte-identical EQ0015–28 — because the keyless-base CREATE path had no idempotency
guard (scaffold stays 0 since the only equations present are the ones IT created).
The `added_by="latex"` guard makes a second run a no-op; --force still re-creates.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C
from pdfdrill.sidecar import Sidecar


_TEX = r"""
\documentclass{article}
\begin{document}
Some prose before.
\begin{equation}\label{eq:one} E = mc^2 \end{equation}
More prose.
\begin{equation}\label{eq:two} a^2 + b^2 = c^2 \end{equation}
\end{document}
"""


def _keyless_model_with_no_equations(pdf: Path):
    """Build a minimal model (a couple of Paragraphs, ZERO Equations) and mark it
    built — the keyless born-digital base the LaTeX gold overlays onto."""
    from docmodel.core import Document, DocObject
    doc = Document()
    doc.meta["bibkey"] = "paper"
    doc.add(DocObject(type="Paragraph", props={"text": "Some prose", "flow_index": 1}))
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    model_path = C._model_path(sc)
    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f)
    sc.add_fact(C.MODEL_BUILT)
    sc.set_evidence("bibkey", "paper")
    sc.save()
    return model_path


def _eq_count(model_path: Path) -> int:
    data = json.loads(model_path.read_text())
    return sum(1 for o in data["objects"] if o["type"] == "Equation")


def test_latex_create_is_idempotent_no_duplicate_equations():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4")
        tex = Path(d) / "paper.tex"; tex.write_text(_TEX)
        model_path = _keyless_model_with_no_equations(pdf)

        C.cmd_latex(pdf, tex=str(tex))
        first = _eq_count(model_path)
        assert first == 2, f"expected 2 created equations, got {first}"

        C.cmd_latex(pdf, tex=str(tex))            # run AGAIN — must not duplicate
        second = _eq_count(model_path)
        assert second == 2, f"re-run duplicated equations: {second} (expected 2)"


def test_latex_force_recreates_not_duplicates():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4")
        tex = Path(d) / "paper.tex"; tex.write_text(_TEX)
        model_path = _keyless_model_with_no_equations(pdf)
        C.cmd_latex(pdf, tex=str(tex))
        C.cmd_latex(pdf, tex=str(tex), force=True)   # force drops then re-creates
        assert _eq_count(model_path) == 2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
