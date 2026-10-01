r"""
840 — the abstract search asks the ARTEFACT, not the FACT.

`ABSTRACT_ABSENT` is a scope-qualified negative, not a verdict: the scope it
was decided at is recorded in `evidence.abstract_search_scope`, the ladder is
`first2pages < first3pages < first5pages < markdown`, and `_can_supersede`
re-runs the search when a wider scope becomes available. Only an ABSENT
decided at `markdown` means "this document has no abstract".

The gate that chose the scope asked `sc.has(MD_BUILT)`. The fact and the file
disagree constantly. Measured over the documents marked ABSTRACT_ABSENT at the
narrow scope in one day's work:

    128 narrow-scope ABSENT
     72 of them had `<bibkey>.md` on disk with MD_BUILT UNSET
     16 of those 72 have a real abstract in that markdown

So the search read two pages while the full text sat beside the PDF, and the
negative it recorded was then reported as "genuinely has no abstract — no
further action needed". The planner already judged by the file
(`done_when: file:{bibkey}.md`), which is why `steps abstract` called md
satisfied on the very documents this gate called md-less.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import commands as C                            # noqa: E402
from pdfdrill.commands import _can_supersede, _SCOPE_ORDER    # noqa: E402

MD = """# Paper

## Abstract

We show that the thing is true, by doing the other thing.

## 1 Introduction
"""


def test_the_scope_ladder_is_ordered_and_markdown_is_widest():
    assert _SCOPE_ORDER["first2pages"] < _SCOPE_ORDER["markdown"]
    assert max(_SCOPE_ORDER, key=_SCOPE_ORDER.get) == "markdown"


def test_a_narrow_absent_is_superseded_by_a_wider_search():
    """THE REASON ABSENT IS NOT A VERDICT."""
    assert _can_supersede("first2pages", "markdown") is True
    assert _can_supersede(None, "first2pages") is True
    # ...and a decision already taken at the widest scope is final
    assert _can_supersede("markdown", "first2pages") is False
    assert _can_supersede("markdown", "markdown") is False


def test_the_gate_reads_the_markdown_file_not_the_fact(monkeypatch, tmp_path):
    """With `<bibkey>.md` on disk and MD_BUILT unset, the search must still run
    at `markdown` scope. This is the 16 lost abstracts."""
    seen = {}
    monkeypatch.setattr(C, "_read_md", lambda pdf, sc: MD)
    monkeypatch.setattr(C, "_extract_abstract_from_markdown",
                        lambda blob: seen.setdefault("blob", blob) or "the abstract")

    class _SC:
        facts = set()
        _data = {"facts": []}

        def has(self, f):
            return False                      # MD_BUILT deliberately UNSET

        def get_evidence(self, k, d=None):
            return None

        def set_evidence(self, k, v):
            seen[k] = v

        def add_fact(self, f):
            seen.setdefault("facts", []).append(f)

        def log_transition(self, *a, **kw):
            pass

        def save(self):
            pass

    monkeypatch.setattr(C, "Sidecar", lambda *a, **kw: _SC())
    monkeypatch.setattr(C, "_store_sources", lambda pdf: None)
    monkeypatch.setattr(C, "_format_abstract", lambda sc: "formatted")
    monkeypatch.setattr(C, "_arxiv_id_for", lambda pdf, sc=None: None)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")

    C.cmd_abstract.__wrapped__(pdf) if hasattr(C.cmd_abstract, "__wrapped__") \
        else C.cmd_abstract(pdf)

    assert seen.get("abstract_search_scope") == "markdown", (
        "the markdown was on disk; the search must not fall back to two pages")
    assert seen.get("abstract_method") == "markdown-heading"
    assert "ABSTRACT_KNOWN" in (seen.get("facts") or [])


def test_no_markdown_still_falls_back_to_the_narrow_scope(monkeypatch, tmp_path):
    """The fallback must survive: a document with no markdown is still searched
    on its first two pages rather than not at all."""
    monkeypatch.setattr(C, "_read_md", lambda pdf, sc: None)
    assert C._read_md(tmp_path / "x.pdf", None) is None
