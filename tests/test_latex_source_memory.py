"""The LaTeX source path is remembered, so `--tex` is passed once, not forever.

A thesis kept its sources in the author's working tree, not beside the PDF. The
first `injectlatex --tex …` worked and even recorded the directory in the model
meta — but the NEXT run, without the flag, reported "No LaTeX source found" and
did nothing, because the locator only ever looked beside the PDF or at arXiv. A
path pdfdrill has already been told, used, and written down should not have to be
supplied again; forgetting it means every later `injectlatex`/`svg` on that
document either re-types the path or silently drops the author's LaTeX and falls
back to MathPix rasters.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C


class _Sidecar:
    """Only what `_locate_latex_source` touches."""
    def __init__(self, evidence=None, blob=None):
        self.evidence = dict(evidence or {})
        self.blob_dir = blob or Path("/nonexistent")
        self.saved = {}

    def set_evidence(self, key, value):
        # named exactly as pdfdrill.sidecar.Sidecar.set_evidence — a stub with
        # an invented method name lets a production typo pass green, which is
        # how the first version of this test "passed" while recording nothing.
        self.evidence[key] = value
        self.saved[key] = value

    def get_evidence(self, key, default=None):
        return self.evidence.get(key, default)


def _pdf(tmp_path, name="doc.pdf"):
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4\n")
    return p


def test_a_sibling_source_is_still_preferred(tmp_path):
    pdf = _pdf(tmp_path)
    sib = tmp_path / "doc.tex"
    sib.write_text("\\documentclass{article}")
    got, err = C._locate_latex_source(pdf, _Sidecar(), None)
    assert err is None and got == sib


def test_an_explicit_tex_is_remembered_for_next_time(tmp_path):
    far = tmp_path / "elsewhere" / "AKolbe-BA.tex"
    far.parent.mkdir()
    far.write_text("\\documentclass{scrbook}")
    sc = _Sidecar()
    got, err = C._locate_latex_source(_pdf(tmp_path), sc, str(far))
    assert err is None and got == far
    assert sc.saved.get("latex_source_path") == str(far.resolve())


def test_the_remembered_path_is_used_when_no_flag_is_given(tmp_path):
    """The whole point: pass --tex once."""
    far = tmp_path / "elsewhere" / "AKolbe-BA.tex"
    far.parent.mkdir()
    far.write_text("\\documentclass{scrbook}")
    sc = _Sidecar({"latex_source_path": str(far)})
    got, err = C._locate_latex_source(_pdf(tmp_path), sc, None)
    assert err is None and got == far


def test_an_explicit_flag_still_overrides_the_memory(tmp_path):
    old = tmp_path / "old.tex"; old.write_text("x")
    new = tmp_path / "new.tex"; new.write_text("y")
    sc = _Sidecar({"latex_source_path": str(old)})
    got, err = C._locate_latex_source(_pdf(tmp_path), sc, str(new))
    assert got == new
    assert sc.saved.get("latex_source_path") == str(new.resolve())


def test_a_remembered_path_that_has_since_moved_does_not_masquerade(tmp_path):
    """A stale memory must not read as a working source — the error has to say
    the recorded path is gone, or the user hunts for a file pdfdrill knows about
    and is not admitting to."""
    sc = _Sidecar({"latex_source_path": str(tmp_path / "gone" / "x.tex")})
    got, err = C._locate_latex_source(_pdf(tmp_path), sc, None)
    assert got is None
    assert "gone" in err and "x.tex" in err


def test_the_memory_is_recovered_from_a_model_built_before_it_existed(tmp_path):
    """Documents already ingested carry `latex_source_dir` in their model meta
    and nothing in the sidecar. Reading it back is what makes this fix apply to
    the library as it stands rather than only to future ingests."""
    srcdir = tmp_path / "thesis"
    srcdir.mkdir()
    (srcdir / "AKolbe-BA.tex").write_text("\\documentclass{scrbook}")
    blob = tmp_path / "blob"
    blob.mkdir()
    (blob / "model.docmodel.json").write_text(json.dumps({
        "meta": {"bibkey": "k", "latex_source_dir": str(srcdir),
                 "latex_preamble": {"main": "AKolbe-BA.tex"}},
        "streams": {}, "objects": [], "alignments": []}))
    got, err = C._locate_latex_source(_pdf(tmp_path), _Sidecar(blob=blob), None)
    assert err is None and got == srcdir / "AKolbe-BA.tex"


def test_no_source_anywhere_still_reports_the_plain_message(tmp_path):
    got, err = C._locate_latex_source(_pdf(tmp_path), _Sidecar(), None)
    assert got is None
    assert "No LaTeX source found" in err


def test_both_resolvers_consult_the_memory(tmp_path):
    """`cmd_injectlatex` keeps its OWN source-resolution order (arXiv e-print
    before a local .tex), so it does not call `_locate_latex_source`. The two
    copies drifted: the memory was added to one and the command still said
    "No LaTeX source found". Both now go through the same two helpers."""
    import inspect
    body = inspect.getsource(C.cmd_injectlatex)
    assert "remembered_latex_source(" in body
    assert "remember_latex_source(" in body
    loc = inspect.getsource(C._locate_latex_source)
    assert "remembered_latex_source(" in loc
    assert "remember_latex_source(" in loc


def test_the_stub_matches_the_real_sidecar_api():
    """The first version of this test stubbed `add_evidence`, which pdfdrill's
    Sidecar does not have: the recording call raised, the `except` swallowed it,
    and the suite went green while nothing was ever written. A stub that does
    not match the real object tests only itself."""
    from pdfdrill.sidecar import Sidecar as Real
    for name in ("set_evidence", "get_evidence"):
        assert hasattr(Real, name), name
        assert hasattr(_Sidecar, name), name
    assert not hasattr(Real, "add_evidence")
