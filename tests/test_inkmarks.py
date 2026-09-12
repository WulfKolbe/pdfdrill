"""673 — `pdfdrill marks` and the two 2026-09-11 defects it exists to
prevent from recurring: a merged stdout/stderr capture that corrupts
every marks.json, and a key resolved by the site slug alone that finds
nothing for a book."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import inkmarks as IM                            # noqa: E402
from pdfdrill import commands as C                             # noqa: E402
from pdfdrill import refine as RF                              # noqa: E402
from pdfdrill import regionink as RI                           # noqa: E402
from pdfdrill.refine import InkUnavailable                     # noqa: E402


# --------------------------------------------------------------------- #
# candidate_keys / resolve_key — the SECOND 2026-09-11 defect
# --------------------------------------------------------------------- #

def test_candidate_keys_is_one_entry_when_folder_and_site_agree(tmp_path):
    doc = tmp_path / "0902.0431" / "0902.0431.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"")
    cands = IM.candidate_keys(doc, "0902.0431")
    assert cands == [("library folder name", "0902.0431")]


def test_candidate_keys_tries_folder_name_first_when_they_differ(tmp_path):
    """The exact shape of a Z-Library book: the folder is the messy download
    title, pdfdrill's own bibkey is the clean slug. Folder name must be
    first — inkdrill always keys by it."""
    folder = tmp_path / "Lie Groups, Physics and Geometry - R. Gilmore ("
    doc = folder / "book.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"")
    cands = IM.candidate_keys(doc, "gilmore-lie-groups")
    assert cands == [
        ("library folder name", folder.name),
        ("pdfdrill bibkey (site slug)", "gilmore-lie-groups"),
    ]


def _stamp_run(marks_root, key):
    work = marks_root / key / "work"
    work.mkdir(parents=True)
    (work / "meta.json").write_text("{}", encoding="utf-8")


def test_resolve_key_uses_the_folder_name_when_only_it_has_a_run(tmp_path):
    """673's regression for the second defect: on 2026-09-11, resolving by
    the site slug ALONE found nothing for a book because the run lives
    under the folder name. Here only the folder-name directory has a
    finished run, and resolution must still succeed by finding it —
    never by falling back to a site slug that has nothing."""
    folder = tmp_path / "library" / "Some Messy Book Title ("
    doc = folder / "book.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"")
    marks_root = tmp_path / "inkdrill-marks"
    _stamp_run(marks_root, folder.name)
    key, matched_by = IM.resolve_key(doc, "clean-bibkey", marks_root=marks_root)
    assert key == folder.name
    assert matched_by == "library folder name"


def test_resolve_key_falls_back_to_site_slug_when_only_it_has_a_run(tmp_path):
    folder = tmp_path / "library" / "Some Messy Book Title ("
    doc = folder / "book.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"")
    marks_root = tmp_path / "inkdrill-marks"
    _stamp_run(marks_root, "clean-bibkey")
    key, matched_by = IM.resolve_key(doc, "clean-bibkey", marks_root=marks_root)
    assert key == "clean-bibkey"
    assert matched_by == "pdfdrill bibkey (site slug)"


def test_resolve_key_refuses_naming_both_when_neither_has_a_run(tmp_path):
    folder = tmp_path / "library" / "Some Messy Book Title ("
    doc = folder / "book.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"")
    marks_root = tmp_path / "inkdrill-marks"
    with pytest.raises(IM.MarksRefused) as e:
        IM.resolve_key(doc, "clean-bibkey", marks_root=marks_root)
    msg = str(e.value)
    assert folder.name in msg and "clean-bibkey" in msg


def test_resolve_key_never_guesses_when_both_have_a_run(tmp_path):
    """Never-guess-silently: if BOTH the folder name and the site slug
    resolve to a finished run, that is an ambiguity, not a tiebreak."""
    folder = tmp_path / "library" / "Some Messy Book Title ("
    doc = folder / "book.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"")
    marks_root = tmp_path / "inkdrill-marks"
    _stamp_run(marks_root, folder.name)
    _stamp_run(marks_root, "clean-bibkey")
    with pytest.raises(IM.MarksRefused) as e:
        IM.resolve_key(doc, "clean-bibkey", marks_root=marks_root)
    msg = str(e.value)
    assert folder.name in msg and "clean-bibkey" in msg
    assert "--key" in msg


# --------------------------------------------------------------------- #
# run() — the FIRST 2026-09-11 defect: stdout/stderr merged
# --------------------------------------------------------------------- #

_FAKE_TOOL = '''\
import sys
print("inkdrill: measuring...", file=sys.stderr, flush=True)
print("inkdrill: still going...", file=sys.stderr, flush=True)
print('{{"bibkey": "{key}", "refused": null, "counts": ''' \
    '''{{"evidence_rows": 1, "measured": 1, "marked": 1, "reading_changed": 0}}}}')
'''


def _fake_inkdrill_root(tmp_path, key="k"):
    root = tmp_path / "fake-inkdrill"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "formulamarks.py").write_text(
        _FAKE_TOOL.format(key=key), encoding="utf-8")
    return root


def test_stderr_progress_never_corrupts_the_parsed_json(monkeypatch, tmp_path):
    """End-to-end through a REAL subprocess: a tool that writes progress to
    stderr and the one JSON document to stdout must parse cleanly. If a
    future change ever merges the two streams (`stderr=subprocess.STDOUT`
    or shell `2>&1`), inkdrill's stderr lines land ahead of the JSON on
    stdout and `json.loads` raises "Extra data" — exactly the failure the
    controller's throwaway script produced on 2026-09-11 for every one of
    21 marks files."""
    root = _fake_inkdrill_root(tmp_path, key="mykey")
    monkeypatch.setattr(IM, "inkdrill_root", lambda: root)
    doc = IM.run(tmp_path / "x.pdf", "mykey",
                marks_root=tmp_path / "mr", library=tmp_path / "lib")
    assert doc == {"bibkey": "mykey", "refused": None,
                   "counts": {"evidence_rows": 1, "measured": 1,
                              "marked": 1, "reading_changed": 0}}


def test_run_captures_stdout_and_stderr_separately(monkeypatch, tmp_path):
    """Pins the call shape directly: capture_output=True (separate
    buffers) and stderr must never be redirected onto stdout."""
    root = _fake_inkdrill_root(tmp_path, key="k")
    monkeypatch.setattr(IM, "inkdrill_root", lambda: root)
    calls = {}
    real_run = subprocess.run

    def spy(cmd, **kw):
        calls.update(kw)
        return real_run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", spy)
    IM.run(tmp_path / "x.pdf", "k", marks_root=tmp_path / "mr",
          library=tmp_path / "lib")
    assert calls.get("capture_output") is True
    assert calls.get("stderr") != subprocess.STDOUT
    assert "stdout" not in calls           # capture_output, not stdout=PIPE by hand


def test_run_refuses_on_no_stdout(monkeypatch, tmp_path):
    root = tmp_path / "fake-inkdrill"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "formulamarks.py").write_text(
        "import sys\nprint('nothing useful', file=sys.stderr)\n",
        encoding="utf-8")
    monkeypatch.setattr(IM, "inkdrill_root", lambda: root)
    with pytest.raises(IM.MarksRefused, match="no stdout"):
        IM.run(tmp_path / "x.pdf", "k", marks_root=tmp_path / "mr",
              library=tmp_path / "lib")


def test_run_refuses_on_unparseable_stdout(monkeypatch, tmp_path):
    """The exact shape of the corrupted-by-merge failure: prose landed
    where only JSON was promised."""
    root = tmp_path / "fake-inkdrill"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "formulamarks.py").write_text(
        "print('inkdrill: measuring...')\nprint('{\"bibkey\": \"k\"}')\n",
        encoding="utf-8")
    monkeypatch.setattr(IM, "inkdrill_root", lambda: root)
    with pytest.raises(IM.MarksRefused, match="not one JSON document"):
        IM.run(tmp_path / "x.pdf", "k", marks_root=tmp_path / "mr",
              library=tmp_path / "lib")


def test_run_raises_ink_unavailable_when_tool_missing(monkeypatch, tmp_path):
    root = tmp_path / "empty-checkout"
    root.mkdir()
    monkeypatch.setattr(IM, "inkdrill_root", lambda: root)
    with pytest.raises(InkUnavailable, match="formulamarks.py"):
        IM.run(tmp_path / "x.pdf", "k", marks_root=tmp_path / "mr",
              library=tmp_path / "lib")


def test_run_propagates_ink_unavailable_when_inkdrill_absent(monkeypatch, tmp_path):
    def boom():
        raise InkUnavailable("inkdrill not found (tried: ~/inkdrill)")
    monkeypatch.setattr(IM, "inkdrill_root", boom)
    with pytest.raises(InkUnavailable, match="tried"):
        IM.run(tmp_path / "x.pdf", "k", marks_root=tmp_path / "mr",
              library=tmp_path / "lib")


# --------------------------------------------------------------------- #
# refine.inkdrill_root / regionink — the two-env-var defect
# --------------------------------------------------------------------- #

def _checkout(path):
    (path / "inkdrill").mkdir(parents=True)
    (path / "inkdrill" / "__main__.py").write_text("", encoding="utf-8")
    return path


def test_inkdrill_root_env_precedence_is_one_function(monkeypatch, tmp_path):
    root = _checkout(tmp_path / "root_checkout")
    home = _checkout(tmp_path / "home_checkout")
    monkeypatch.setenv("INKDRILL_ROOT", str(root))
    monkeypatch.setenv("INKDRILL_HOME", str(home))
    assert RF.inkdrill_root() == root
    assert RF._env_inkdrill_home() == root


def test_inkdrill_home_alias_still_works_when_root_unset(monkeypatch, tmp_path):
    home = _checkout(tmp_path / "home_checkout")
    monkeypatch.delenv("INKDRILL_ROOT", raising=False)
    monkeypatch.setenv("INKDRILL_HOME", str(home))
    assert RF.inkdrill_root() == home


def test_regionink_and_refine_agree_on_env_precedence(tmp_path):
    """Black-box, across a real process: `regionink._INKDRILL_HOME` and
    `refine.inkdrill_root()` must resolve to the SAME checkout when both
    INKDRILL_ROOT and INKDRILL_HOME are set to different, real checkouts —
    two modules reading two env vars independently is exactly the defect
    673 fixes."""
    root = _checkout(tmp_path / "root_checkout")
    home = _checkout(tmp_path / "home_checkout")
    code = (
        "from pdfdrill import refine, regionink\n"
        "print(refine.inkdrill_root())\n"
        "print(regionink._INKDRILL_HOME)\n"
    )
    env = dict(os.environ, INKDRILL_ROOT=str(root), INKDRILL_HOME=str(home))
    env["PYTHONPATH"] = str(ROOT / "src")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=30, env=env)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines == [str(root), str(root)], (lines, r.stderr)


# --------------------------------------------------------------------- #
# cmd_marks — writes beside the document, surfaces reading_changed,
# never reports a refusal as success
# --------------------------------------------------------------------- #

def _fake_doc(tmp_path):
    pdf = tmp_path / "somedoc" / "somedoc.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4\n")
    return pdf


def test_cmd_marks_writes_marks_json_beside_the_document(monkeypatch, tmp_path):
    pdf = _fake_doc(tmp_path)
    payload = {"bibkey": "somedoc", "refused": None,
               "counts": {"evidence_rows": 10, "measured": 9, "marked": 4,
                          "reading_changed": 0,
                          "suppressed": {"too short": 5}}}
    monkeypatch.setattr(IM, "resolve_key",
                        lambda pdf, site_key, marks_root: ("somedoc",
                                                           "library folder name"))
    monkeypatch.setattr(IM, "run", lambda pdf, key, marks_root, library: payload)
    out = C.cmd_marks(pdf)
    assert "somedoc" in out
    assert "library folder name" in out
    assert "reading_changed: 0" in out
    written = json.loads((pdf.parent / "marks.json").read_text(encoding="utf-8"))
    assert written == payload


def test_cmd_marks_surfaces_reading_changed_prominently(monkeypatch, tmp_path):
    pdf = _fake_doc(tmp_path)
    payload = {"bibkey": "somedoc", "refused": None,
               "counts": {"evidence_rows": 10, "measured": 8, "marked": 4,
                          "reading_changed": 3}}
    monkeypatch.setattr(IM, "resolve_key",
                        lambda pdf, site_key, marks_root: ("somedoc", "x"))
    monkeypatch.setattr(IM, "run", lambda pdf, key, marks_root, library: payload)
    out = C.cmd_marks(pdf)
    assert "reading_changed: 3" in out


def test_cmd_marks_refusal_is_never_reported_as_success(monkeypatch, tmp_path):
    pdf = _fake_doc(tmp_path)
    payload = {"bibkey": "somedoc",
               "refused": "stale: somedoc.lines.json changed since the run",
               "counts": {}}
    monkeypatch.setattr(IM, "resolve_key",
                        lambda pdf, site_key, marks_root: ("somedoc", "x"))
    monkeypatch.setattr(IM, "run", lambda pdf, key, marks_root, library: payload)
    with pytest.raises(IM.MarksRefused, match="stale"):
        C.cmd_marks(pdf)
    assert not (pdf.parent / "marks.json").exists()
    refused_note = pdf.parent / "marks.json.REFUSED"
    assert refused_note.exists()
    assert "stale" in refused_note.read_text(encoding="utf-8")


def test_cmd_marks_explicit_key_bypasses_resolution_but_still_checks_a_run_exists(
        monkeypatch, tmp_path):
    pdf = _fake_doc(tmp_path)
    mroot = tmp_path / "inkdrill-marks"
    with pytest.raises(IM.MarksRefused, match="explicit-key"):
        C.cmd_marks(pdf, key="explicit-key", marks_root=mroot)


def test_cmd_marks_explicit_key_used_when_a_run_exists(monkeypatch, tmp_path):
    pdf = _fake_doc(tmp_path)
    mroot = tmp_path / "inkdrill-marks"
    _stamp_run(mroot, "explicit-key")
    payload = {"bibkey": "explicit-key", "refused": None,
               "counts": {"evidence_rows": 1, "measured": 1, "marked": 0,
                         "reading_changed": 0}}
    monkeypatch.setattr(IM, "run", lambda pdf, key, marks_root, library: payload)
    out = C.cmd_marks(pdf, key="explicit-key", marks_root=mroot)
    assert "explicit-key" in out
    assert "--key (explicit)" in out


def test_cmd_marks_is_a_locked_handler():
    """297 — one writer per document. A second concurrent `pdfdrill marks`
    on the same PDF must refuse, not interleave its write of marks.json
    with another process's."""
    import inspect
    mod_src = inspect.getsource(C)
    assert '@_writes("marks")\ndef cmd_marks' in mod_src


def test_cmd_marks_build_flag_calls_evidence_with_the_written_marks_path(
        monkeypatch, tmp_path):
    pdf = _fake_doc(tmp_path)
    payload = {"bibkey": "somedoc", "refused": None,
               "counts": {"evidence_rows": 1, "measured": 1, "marked": 1,
                         "reading_changed": 0}}
    monkeypatch.setattr(IM, "resolve_key",
                        lambda pdf, site_key, marks_root: ("somedoc", "x"))
    monkeypatch.setattr(IM, "run", lambda pdf, key, marks_root, library: payload)
    seen = {}

    def fake_evidence(pdf, all_kinds=False, pdf_out=False, marks_path=None,
                      **kw):
        seen["marks_path"] = marks_path
        seen["all_kinds"] = all_kinds
        seen["pdf_out"] = pdf_out
        return "evidence: ok"

    monkeypatch.setattr(C, "cmd_evidence", fake_evidence)
    out = C.cmd_marks(pdf, build=True)
    assert seen["marks_path"] == pdf.parent / "marks.json"
    assert seen["all_kinds"] is True and seen["pdf_out"] is True
    assert "evidence: ok" in out


def test_cmd_marks_default_does_not_touch_evidence(monkeypatch, tmp_path):
    """The default stops at the marks file — `--build` is opt-in."""
    pdf = _fake_doc(tmp_path)
    payload = {"bibkey": "somedoc", "refused": None,
               "counts": {"evidence_rows": 1, "measured": 1, "marked": 1,
                         "reading_changed": 0}}
    monkeypatch.setattr(IM, "resolve_key",
                        lambda pdf, site_key, marks_root: ("somedoc", "x"))
    monkeypatch.setattr(IM, "run", lambda pdf, key, marks_root, library: payload)

    def boom(*a, **kw):
        raise AssertionError("cmd_evidence must not run without --build")

    monkeypatch.setattr(C, "cmd_evidence", boom)
    out = C.cmd_marks(pdf)
    assert "wrote marks.json" in out
