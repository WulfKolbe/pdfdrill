"""
`pdfdrill tables` on a born-digital TWO-COLUMN paper: pdfplumber mis-reads the two
columns of body PROSE as a 3-column table (long sentence-fragment cells). Meanwhile
the model carries the paper's REAL tables as gold LaTeX (from the arXiv source
overlay). So: drop the prose-as-table garbage, and render the model's gold tables.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


def test_prose_table_detected_and_data_table_kept():
    # a pdfplumber "table" that is really two-column prose (long sentence cells)
    prose = {"cells": [
        {"text": "also proposes a flexible generation of the output by VAE,"},
        {"text": "Topic models with Embedding. PCAE proposes to cluster words"},
        {"text": "terms of NPMI deviating from the results observed in the paper"},
        {"text": "size that this outcome can be attributed to the vocabulary"}]}
    assert C._prose_table(prose) is True
    # a genuine data table: short numeric/label cells
    data = {"cells": [
        {"text": "Model"}, {"text": "Acc"}, {"text": "F1"},
        {"text": "Ours"}, {"text": "0.91"}, {"text": "0.88"},
        {"text": "Seer"}, {"text": "0.85"}, {"text": "0.83"}]}
    assert C._prose_table(data) is False


def test_gold_table_dicts_from_latex():
    from docmodel.core import Document, DocObject
    doc = Document()
    doc.add(DocObject(type="Table", props={
        "flow_index": 1, "caption": "Statistics of datasets", "number": 1,
        "latex_code": r"\begin{tabular}{lrr}\toprule Dataset & Docs & Words \\"
                      r"\midrule 20NG & 18k & 2000 \\ NYT & 12k & 5000 \\ \bottomrule"
                      r"\end{tabular}"}))
    golds = C._gold_table_dicts(doc)
    assert len(golds) == 1
    t = golds[0]
    assert t["strategy"] == "latex-gold" and t["caption"] == "Statistics of datasets"
    # rows/cells reconstructed from the tabular (\\ = row, & = column)
    texts = {c["text"] for c in t["cells"]}
    assert {"Dataset", "Docs", "Words", "20NG", "18k", "NYT", "5000"} <= texts
    assert t["n_cols"] == 3
    # the booktabs rules are NOT rows
    assert "toprule" not in " ".join(texts) and "midrule" not in " ".join(texts)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
