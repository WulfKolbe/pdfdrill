r"""T-0122 — `blob_dir_for` decides the layout by the folder's NAME.

Reproduced from a real refusal (2026-11-01 19:53, T-0116 phase 2): a document
folder was copied into a working directory under a different name, and
`pdfdrill inkreport` then refused

    [  ] model      no model.docmodel.json — run `pdfdrill model` first
    [  ] geometry   the model carries no page geometry
    REFUSED: model, geometry. Nothing was spent and nothing was written.

with a complete 472-object model, bibkey `0707.4470`, sitting two directory
entries away. Re-run from a clean copy of that folder in one invocation, the
refusal comes back byte for byte, so it is the layout rule and not a transient.

THE PREFLIGHT IS NOT AT FAULT, and neither is any consumer. `cmd_inkreport`
resolves `doc = blob_dir_for(pdf)[0]` — commented "layout-aware, never
hardcoded" — and the check correctly reports that the blob_dir it was given
holds no model. What is wrong is which blob_dir it was given.

ONE DERIVATION, NOT TWO. The task was first described as "the sidecar path is
derived two different ways", which would mean the writer and the check disagree.
Measured, by wrapping `inkreport.preflight` and `model_io.save_model` in the
clean reproduction: the path tested and the path written are THE SAME path, and
the apparent contradiction in the original log is print ORDER. `cmd_inkreport`
accumulates its PREFLIGHT lines in a list it returns, so they appear last,
while `[main] wrote …` goes live to stderr. The check ran at t=1.011s against a
blob_dir that did not exist; the model was written into it at t=1.298s and
again at t=2.587s. So:

    folder                  doc_dir the check got      model?  verdict
    0707.4470-baseline/     0707.4470.pdf.drill/       False   REFUSED
    0707.4470/              the folder itself          True    [ok] model

Byte-identical contents in both; only the folder's name differs. That is the
controlled comparison, and it is why the name gate is the cause rather than a
coincidence of that one run.

TWO MORE DEFECTS VISIBLE IN THE SAME RUN, recorded here because they were
measured, not fixed and not this module's subject: the model is built TWICE in
one command (two `save_model` calls, t=1.298s and t=2.587s), and the command
prints "REFUSED: model, geometry. Nothing was spent and nothing was written."
while writing a 77,641-byte residuals.pdf — a refusal message that is wrong
about both the refusal and the writing.

`blob_dir_for` gates self-containment on `parent.name == p.stem`, so the SAME
TWO FILES are read two ways:

    0707.4470/      + 0707.4470.pdf + 0707.4470.drill.json  -> self-contained
    anything-else/  + 0707.4470.pdf + 0707.4470.drill.json  -> LEGACY

That contradicts the function's own docstring, which says a self-contained
sidecar "ALWAYS wins" and that "only a genuine pre-self-contained doc (a legacy
`.drill/` or `.drill.json` AND no self-contained sidecar) falls back to legacy".
In the second folder there IS a self-contained sidecar and there is NO legacy
artifact, so by the documented rule it must not fall back. It does.

FIXED, on the owner's decision of 2026-11-02: honour an existing
self-contained sidecar when no legacy artifact is present, whatever the folder
is called. The paragraph below is kept because it is why the fix is shaped that
way and not as "drop the name gate".

WHY IT IS NOT SIMPLY DROPPING THE NAME GATE. The name gate is load-bearing: without it, a directory holding
several PDFs would resolve each one's blob_dir to the shared directory, and
`model.docmodel.json`, `residuals.pdf` and `evidence-*.pdf` carry the same name
for every document — the collision `doclock.ensure_doc_folder` exists to
prevent, which defect 854 measured as 2,667 nested folders. The narrow rule
that would fix this case without reopening that one is "honour an EXISTING
self-contained sidecar when no legacy artifact is present, whatever the folder
is called", because that sidecar's existence is evidence some earlier run
already treated this folder as the document's own. That is a decision about
where artefacts land, so it belongs to the owner, not to this test.

The name test therefore stays first and stays load-bearing; the new branch
fires only where a sidecar is ALREADY present and no legacy artifact is, so it
cannot promote a folder nothing has drilled. `test_a_shared_directory_is_not_
promoted_by_a_stray_sidecar` holds that line.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill.sidecar import blob_dir_for                   # noqa: E402

STEM = "0707.4470"
#: A one-page PDF is not needed: `blob_dir_for` is a pure path decision and
#: never opens the file. Bytes enough to be a plausible PDF, nothing more.
_PDF = b"%PDF-1.4\n%%EOF\n"


def _folder(tmp_path: Path, name: str) -> Path:
    """`<tmp>/<name>/` holding `<STEM>.pdf` and a SELF-CONTAINED sidecar."""
    d = tmp_path / name
    d.mkdir()
    (d / f"{STEM}.pdf").write_bytes(_PDF)
    (d / f"{STEM}.drill.json").write_text("{}", encoding="utf-8")
    return d


def test_a_folder_named_after_the_document_is_self_contained(tmp_path):
    """The case that works today, so the comparison below is about one thing."""
    d = _folder(tmp_path, STEM)
    blob, js = blob_dir_for(d / f"{STEM}.pdf")
    assert blob == d
    assert js.name == f"{STEM}.drill.json"


def test_a_self_contained_sidecar_wins_whatever_the_folder_is_called(tmp_path):
    """The documented rule, applied to a folder with a different name.

    Same two files as the test above. The docstring's "ALWAYS wins" says the
    answer must be the same; the name gate makes it legacy.
    """
    d = _folder(tmp_path, "anything-else")
    blob, js = blob_dir_for(d / f"{STEM}.pdf")
    assert blob == d, f"blob_dir is {blob.name}, not the folder itself"
    assert js.name == f"{STEM}.drill.json", js.name


def test_the_two_folders_differ_only_in_their_name(tmp_path):
    """Pins what the defect IS, and passes either way.

    These two folders hold byte-identical contents, so any difference in the
    answer could only come from the name. Before the fix they differed:
    `0707.4470/` resolved to itself and `anything-else/` to
    `0707.4470.pdf.drill`. Now each resolves to itself.
    """
    a = _folder(tmp_path, STEM)
    b = _folder(tmp_path, "anything-else")
    assert sorted(p.name for p in a.iterdir()) == sorted(p.name for p in b.iterdir())
    blob_a, _ = blob_dir_for(a / f"{STEM}.pdf")
    blob_b, _ = blob_dir_for(b / f"{STEM}.pdf")
    # Since the fix the ANSWER is the same in kind — each folder is its own
    # document's blob_dir — even though the two folders are named differently.
    assert blob_a == a
    assert blob_b == b


def test_a_legacy_artifact_and_no_self_contained_sidecar_is_legacy(tmp_path):
    """The case the fallback is FOR, so a fix cannot quietly remove it."""
    d = tmp_path / STEM
    d.mkdir()
    (d / f"{STEM}.pdf").write_bytes(_PDF)
    (d / f"{STEM}.pdf.drill.json").write_text("{}", encoding="utf-8")
    blob, js = blob_dir_for(d / f"{STEM}.pdf")
    assert blob.name == f"{STEM}.pdf.drill"
    assert js.name == f"{STEM}.pdf.drill.json"


# ── the shape of the run that found this ─────────────────────────────────────

def _copied_doc_folder(tmp_path: Path, name: str) -> Path:
    """A self-contained document's CONTENTS, copied into a folder called `name`.

    This is what the 19:53 run did: everything a built document carries —
    the PDF, its self-contained sidecar, its reading and a complete model at
    the top level — in a directory that is not named after the stem.
    """
    d = tmp_path / name
    d.mkdir()
    (d / f"{STEM}.pdf").write_bytes(_PDF)
    (d / f"{STEM}.drill.json").write_text("{}", encoding="utf-8")
    (d / f"{STEM}.lines.json").write_text('{"pages": []}', encoding="utf-8")
    (d / "model.docmodel.json").write_text(
        '{"meta": {"bibkey": "%s"}, "objects": {}}' % STEM, encoding="utf-8")
    return d


def test_the_model_the_folder_holds_is_where_the_name_says_to_look(tmp_path):
    """The folder named after the stem: the check's path IS the model's path."""
    d = _copied_doc_folder(tmp_path, STEM)
    blob, _ = blob_dir_for((d / f"{STEM}.pdf").resolve())
    assert (blob / "model.docmodel.json").is_file()


def test_a_copied_doc_folder_does_not_hide_its_own_model(tmp_path):
    """The refusal, as a path question rather than a 290-crop chain run.

    `cmd_inkreport` tests `blob_dir_for(pdf)[0] / "model.docmodel.json"`. With
    the folder named anything else that path is `<stem>.pdf.drill/…`, which no
    copy ever creates — while the model the copy brought sits at the top level.
    """
    d = _copied_doc_folder(tmp_path, "0707.4470-baseline")
    assert (d / "model.docmodel.json").is_file(), "the model the copy brought"
    blob, _ = blob_dir_for((d / f"{STEM}.pdf").resolve())
    tested = blob / "model.docmodel.json"
    assert tested.is_file(), (
        f"the preflight tests {tested.relative_to(d)}, which does not exist, "
        f"while a complete model sits in {d.name}/model.docmodel.json")


# ── the line the fix must not cross ──────────────────────────────────────────

def test_a_legacy_doc_in_a_mis_named_folder_stays_legacy(tmp_path):
    """A self-contained sidecar does NOT win over a real legacy artifact.

    The docstring's own exception: "only a genuine pre-self-contained doc (a
    legacy `.drill/` or `.drill.json` AND no self-contained sidecar) falls back
    to legacy" — read the other way, a legacy artifact present in a folder that
    is not the document's own keeps the legacy answer, because that is where
    its blobs already are. Moving the answer would orphan them.
    """
    d = _copied_doc_folder(tmp_path, "some-other-name")
    (d / f"{STEM}.pdf.drill").mkdir()                      # a real legacy blob dir
    blob, js = blob_dir_for((d / f"{STEM}.pdf").resolve())
    assert blob.name == f"{STEM}.pdf.drill"
    assert js.name == f"{STEM}.pdf.drill.json"


def test_a_shared_directory_is_not_promoted_by_a_stray_sidecar(tmp_path):
    """Two documents in one directory: neither may claim the directory.

    This is the collision `doclock.ensure_doc_folder` exists to prevent (854:
    2,667 nested folders), and the reason the name test stays first. A sidecar
    for ONE of them must not make that shared directory its blob_dir, or
    `model.docmodel.json` and `residuals.pdf` — named the same for every
    document — would be written over each other.

    The fix does not open this, because `ensure_doc_folder` moves a document
    out of a shared directory before any writer runs. What this test pins is
    the weaker, local property: the answer for `other.pdf`, which has no
    sidecar of its own, is still its own legacy blob_dir and never the
    directory that `STEM`'s sidecar sits in.
    """
    d = _copied_doc_folder(tmp_path, "downloads")
    (d / "other.pdf").write_bytes(_PDF)
    blob, js = blob_dir_for((d / "other.pdf").resolve())
    assert blob.name == "other.pdf.drill", blob.name
    assert blob != d
