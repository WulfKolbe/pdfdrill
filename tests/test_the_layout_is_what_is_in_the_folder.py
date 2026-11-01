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

`blob_dir_for` gates self-containment on `parent.name == p.stem`, so the SAME
TWO FILES are read two ways:

    0707.4470/      + 0707.4470.pdf + 0707.4470.drill.json  -> self-contained
    anything-else/  + 0707.4470.pdf + 0707.4470.drill.json  -> LEGACY

That contradicts the function's own docstring, which says a self-contained
sidecar "ALWAYS wins" and that "only a genuine pre-self-contained doc (a legacy
`.drill/` or `.drill.json` AND no self-contained sidecar) falls back to legacy".
In the second folder there IS a self-contained sidecar and there is NO legacy
artifact, so by the documented rule it must not fall back. It does.

WHY THIS IS NOT A ONE-LINE FIX, and why the test below is a strict xfail rather
than a change. The name gate is load-bearing: without it, a directory holding
several PDFs would resolve each one's blob_dir to the shared directory, and
`model.docmodel.json`, `residuals.pdf` and `evidence-*.pdf` carry the same name
for every document — the collision `doclock.ensure_doc_folder` exists to
prevent, which defect 854 measured as 2,667 nested folders. The narrow rule
that would fix this case without reopening that one is "honour an EXISTING
self-contained sidecar when no legacy artifact is present, whatever the folder
is called", because that sidecar's existence is evidence some earlier run
already treated this folder as the document's own. That is a decision about
where artefacts land, so it belongs to the owner, not to this test.

The strict marker is deliberate: when the rule changes, this test FAILS instead
of passing silently, so whoever changes it has to come back and read this.
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


@pytest.mark.xfail(strict=True, reason=(
    "T-0122: blob_dir_for gates self-containment on parent.name == stem, so a "
    "self-contained sidecar is ignored when the folder is named something "
    "else — contradicting its own docstring. The narrow fix is a decision "
    "about where artefacts land (see this module's docstring), so it is the "
    "owner's, not this test's."))
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

    Whatever is decided, these two folders hold byte-identical contents, so any
    difference in the answer comes from the name alone. Today the answers
    differ; this test records that they do, and names both.
    """
    a = _folder(tmp_path, STEM)
    b = _folder(tmp_path, "anything-else")
    assert sorted(p.name for p in a.iterdir()) == sorted(p.name for p in b.iterdir())
    blob_a, _ = blob_dir_for(a / f"{STEM}.pdf")
    blob_b, _ = blob_dir_for(b / f"{STEM}.pdf")
    assert blob_a.name == STEM
    assert blob_b.name == f"{STEM}.pdf.drill"          # today's answer


def test_a_legacy_artifact_and_no_self_contained_sidecar_is_legacy(tmp_path):
    """The case the fallback is FOR, so a fix cannot quietly remove it."""
    d = tmp_path / STEM
    d.mkdir()
    (d / f"{STEM}.pdf").write_bytes(_PDF)
    (d / f"{STEM}.pdf.drill.json").write_text("{}", encoding="utf-8")
    blob, js = blob_dir_for(d / f"{STEM}.pdf")
    assert blob.name == f"{STEM}.pdf.drill"
    assert js.name == f"{STEM}.pdf.drill.json"
