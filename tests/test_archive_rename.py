"""`relocate` phase 2 — the host prefix migration (807, defects 805/806)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import archive_rename as AR          # noqa: E402


# ── the shape rule is arithmetic, and it is the FIRST authority ──────────────

@pytest.mark.parametrize("ident,kind", [
    ("2510.04618", "arxiv"),      # five digits — viXra never issued one
    ("1501.00001", "arxiv"),
    ("math_0309136", "arxiv"),    # old-style — viXra has no such scheme
    ("hep-th_9901001", "arxiv"),
    ("1702.0234", "vixra"),       # four digits after arXiv left them behind
    ("1501.0001", "vixra"),
    ("2505.0100v1", "vixra"),
    ("1412.8390", None),          # four digits before 1501 — genuinely both
    ("0705.4638", None),
    ("not-an-id", None),
])
def test_shape_kind(ident, kind):
    assert AR.shape_kind(ident) == kind


def test_already_prefixed_is_not_a_candidate():
    assert AR.looks_like_archive_id("2510.04618")
    assert not AR.looks_like_archive_id("arxiv.2510.04618")
    assert not AR.looks_like_archive_id("vixra.1702.0234v1")
    assert not AR.looks_like_archive_id("1-s2.0-S2590118425000565-main")


# ── the precedence: shape OVER a sidecar that names the other archive ────────

def _doc(root: Path, stem: str, bibtex_url: str | None = None) -> Path:
    d = root / stem
    (d / "latex").mkdir(parents=True)
    (d / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n")
    (d / f"{stem}.inspect.html").write_text("x")
    (d / "latex" / f"{stem}.tex").write_text("x")
    (d / "model.docmodel.json").write_text("{}")
    sc = {"pdf": f"{stem}.pdf",
          "evidence": {"bibkey": stem, "inspect_path": f"{stem}.inspect.html",
                       "source_arxiv_id": stem},
          "bibtex": {"arxiv_id": stem, "eprint": stem}}
    if bibtex_url:
        sc["bibtex"]["url"] = bibtex_url
    (d / f"{stem}.drill.json").write_text(json.dumps(sc))
    return d


def test_shape_beats_a_sidecar_claiming_the_other_archive(tmp_path):
    """The measured 806 residue: nine viXra folders in this library carry a
    sidecar bibtex saying arxiv.org. Believing it would write the defect into
    the filesystem, where nothing questions a folder name again."""
    d = _doc(tmp_path, "2505.0100v1", bibtex_url="https://arxiv.org/abs/2505.0100v1")
    plan = AR.plan_rename(d, {})
    assert isinstance(plan, AR.Rename)
    assert plan.kind == "vixra" and plan.via == "shape"
    assert plan.new_stem == "vixra.2505.0100v1"
    assert plan.bibtex_disagrees is True          # and it is REPORTED, not hidden


def test_registry_url_decides_an_ambiguous_id(tmp_path):
    d = _doc(tmp_path, "1107.2723")
    reg = {"https://arxiv.org/abs/1107.2723":
           {"filename": "1107.2723/1107.2723.pdf"}}
    plan = AR.plan_rename(d, reg)
    assert (plan.kind, plan.via) == ("arxiv", "registry")


def test_sidecar_decides_only_when_nothing_else_can(tmp_path):
    d = _doc(tmp_path, "1107.2723", bibtex_url="https://vixra.org/abs/1107.2723")
    plan = AR.plan_rename(d, {})
    assert (plan.kind, plan.via) == ("vixra", "sidecar")


def test_ambiguous_with_no_evidence_is_skipped_never_guessed(tmp_path):
    d = tmp_path / "1412.8390"
    d.mkdir()
    (d / "1412.8390.pdf").write_bytes(b"%PDF")
    plan = AR.plan_rename(d, {})
    assert isinstance(plan, AR.Skip)
    assert "1501" in plan.reason


def test_a_corrupt_sidecar_does_not_break_the_rename(tmp_path):
    """Three sidecars in this library are truncated JSON. A doc still has a
    shape; a rename is not the place to die on a bad file."""
    d = _doc(tmp_path, "2510.04618")
    (d / "2510.04618.drill.json").write_text('{"pdf": "x"} EXTRA GARBAGE')
    plan = AR.plan_rename(d, {})
    assert plan.kind == "arxiv"
    AR.apply_rename(plan)
    assert (tmp_path / "arxiv.2510.04618").is_dir()


# ── what the rename touches, and what it must NOT ────────────────────────────

def test_renames_the_folder_and_every_file_carrying_the_stem(tmp_path):
    d = _doc(tmp_path, "2510.04618")
    AR.apply_rename(AR.plan_rename(d, {}))
    new = tmp_path / "arxiv.2510.04618"
    assert new.is_dir() and not d.exists()
    assert (new / "arxiv.2510.04618.pdf").exists()
    assert (new / "arxiv.2510.04618.drill.json").exists()
    assert (new / "latex" / "arxiv.2510.04618.tex").exists()   # at any depth
    assert (new / "model.docmodel.json").exists()              # untouched


def test_the_sidecar_keeps_the_ID_and_gains_the_new_PATHS(tmp_path):
    """The stem changes; the arXiv id does NOT. A blind string replace would
    write `arxiv.2510.04618` into `source_arxiv_id` and take the document off
    every free e-print route."""
    d = _doc(tmp_path, "2510.04618")
    AR.apply_rename(AR.plan_rename(d, {}))
    sc = json.loads((tmp_path / "arxiv.2510.04618" /
                     "arxiv.2510.04618.drill.json").read_text())
    assert sc["pdf"] == "arxiv.2510.04618.pdf"
    assert sc["evidence"]["inspect_path"] == "arxiv.2510.04618.inspect.html"
    assert sc["evidence"]["bibkey"] == "arxiv.2510.04618"
    assert sc["evidence"]["source_arxiv_id"] == "2510.04618"   # the ID stands
    assert sc["bibtex"]["arxiv_id"] == "2510.04618"
    assert sc["bibtex"]["eprint"] == "2510.04618"


def test_a_collision_moves_nothing_at_all(tmp_path):
    d = _doc(tmp_path, "2510.04618")
    (tmp_path / "arxiv.2510.04618").mkdir()
    plan = AR.plan_rename(d, {})
    assert not plan.ok and plan.collisions
    assert AR.apply_rename(plan) == 0
    assert (d / "2510.04618.pdf").exists()        # untouched


def test_the_download_registry_is_repointed(tmp_path):
    """Left stale, the next `add <url>` finds no file at the recorded path and
    pays for the download again."""
    d = _doc(tmp_path, "2510.04618")
    reg = {"https://arxiv.org/abs/2510.04618":
           {"filename": "2510.04618/2510.04618.pdf", "bytes": 1},
           "https://example.org/other.pdf": {"filename": "other/other.pdf"}}
    plan = AR.plan_rename(d, reg)
    AR.apply_rename(plan)
    assert AR.rewrite_registry(reg, [plan]) == 1
    assert (reg["https://arxiv.org/abs/2510.04618"]["filename"]
            == "arxiv.2510.04618/arxiv.2510.04618.pdf")
    assert reg["https://example.org/other.pdf"]["filename"] == "other/other.pdf"


def test_idempotent(tmp_path):
    d = _doc(tmp_path, "2510.04618")
    AR.apply_rename(AR.plan_rename(d, {}))
    assert AR.find_folders(tmp_path) == []
    assert AR.plan_rename(tmp_path / "arxiv.2510.04618", {}) is None


def test_the_renamed_folder_still_yields_its_arxiv_id(tmp_path):
    """The whole point of the free lanes: `archive_ident` must invert the name,
    or the rename quietly moves papers off the e-print route and onto OCR."""
    from pdfdrill import sources as S
    d = _doc(tmp_path, "2510.04618")
    AR.apply_rename(AR.plan_rename(d, {}))
    assert S.archive_ident("arxiv.2510.04618") == ("arxiv", "2510.04618")


# ── the command ──────────────────────────────────────────────────────────────

def test_cmd_relocate_dry_run_moves_nothing(tmp_path):
    from pdfdrill.commands import cmd_relocate
    _doc(tmp_path, "2510.04618")
    bare = tmp_path / "1412.8390"          # no sidecar: nothing proves the archive
    bare.mkdir()
    (bare / "1412.8390.pdf").write_bytes(b"%PDF")
    out = cmd_relocate([], library=str(tmp_path))
    assert "HOST PREFIX" in out and "arxiv.2510.04618" in out
    assert "SKIPPED" in out and "1412.8390" in out
    assert (tmp_path / "2510.04618").is_dir()          # dry run

    out = cmd_relocate([], library=str(tmp_path), apply=True)
    assert (tmp_path / "arxiv.2510.04618").is_dir()
    assert (tmp_path / "1412.8390").is_dir()           # skipped, not guessed


def test_cmd_relocate_no_prefix_opts_out(tmp_path):
    from pdfdrill.commands import cmd_relocate
    _doc(tmp_path, "2510.04618")
    out = cmd_relocate([], library=str(tmp_path), apply=True, no_prefix=True)
    assert "HOST PREFIX" not in out
    assert (tmp_path / "2510.04618").is_dir()
