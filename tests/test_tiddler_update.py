"""651 — `pdfdrill tiddlers --update <old.tiddlers.json>`.

650 proved titles survive a rebuild unchanged, which is what makes matching
an older tiddler array onto a fresh projection BY TITLE safe. This file
tests the merge in two layers:

  * `merge_updated_tiddlers` directly, on hand-built tiddler dicts — every
    KEEP_LIST entry, the conditional `text`/`caption` predicate, the
    dangling-transclusion refusal, and the unmatched-title accounting.
  * `cmd_tiddlers(..., update=...)` end to end, through the real model
    pipeline (`cmd_model` -> `cmd_tiddlers`), matching the brief's own
    scenario: a translated PARA, a wiki-added `note` field, a hand-edited
    `latex`, and one stale title with no match.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docops.projectors.tiddlywiki import (
    merge_updated_tiddlers, tiddler_integrity, KEEP_LIST, keep_list_report,
    _is_hand_edited,
)


# ---------------------------------------------------------------------------
# merge_updated_tiddlers — unit level
# ---------------------------------------------------------------------------

def _pair(fresh_extra=None, old_extra=None, title="DOC_PARA_0001"):
    fresh = {"title": title, "text": "fresh text", "created": "1", "modified": "1"}
    old = {"title": title, "text": "old text", "created": "1", "modified": "1"}
    fresh.update(fresh_extra or {})
    old.update(old_extra or {})
    return fresh, old


def test_translated_text_survives_via_source_marker():
    # `text_source` matches the CURRENT fresh text -- the model has not
    # moved between builds, so the translation still applies cleanly and
    # `_stale_base_conflict` must not fire.
    fresh, old = _pair(old_extra={
        "text": "Translated English prose.", "text_source": "fresh text"})
    m = merge_updated_tiddlers([fresh], [old])
    assert fresh["text"] == "Translated English prose."
    assert fresh["text_source"] == "fresh text"
    assert "text" in m["restored"]["DOC_PARA_0001"]
    assert "text_source" in m["restored"]["DOC_PARA_0001"]
    assert m["refused_stale_base"] == {}


def test_translated_text_survives_via_modified_after_created():
    """No `_source` marker, but the old tiddler was clearly opened and saved
    inside TiddlyWiki after being written — that alone is enough."""
    fresh, old = _pair(old_extra={"text": "hand-edited.", "created": "1", "modified": "2"})
    merge_updated_tiddlers([fresh], [old])
    assert fresh["text"] == "hand-edited."


def test_plain_stale_text_does_not_survive():
    """The control: an old value with NEITHER signal is ordinary staleness —
    the whole point of 650 is that the model's fresh text must win here."""
    fresh, old = _pair(old_extra={"text": "just an older OCR reading."})
    merge_updated_tiddlers([fresh], [old])
    assert fresh["text"] == "fresh text"


def test_wiki_added_note_field_survives():
    fresh, old = _pair(old_extra={"note_pronunciation": "hand note"})
    m = merge_updated_tiddlers([fresh], [old])
    assert fresh["note_pronunciation"] == "hand note"
    assert "note_pronunciation" in m["restored"]["DOC_PARA_0001"]


def test_note_prefixed_field_present_on_both_sides_still_keeps_old():
    """Not just the absent-field case: if the model ever grows a same-named
    field, the reserved-namespace convention still wins, and says so."""
    fresh, old = _pair(fresh_extra={"note_pronunciation": "model guess"},
                       old_extra={"note_pronunciation": "hand note"})
    m = merge_updated_tiddlers([fresh], [old])
    assert fresh["note_pronunciation"] == "hand note"
    assert m["restored"]["DOC_PARA_0001"]["note_pronunciation"].startswith("reserved")


def test_user_prefixed_field_survives():
    fresh, old = _pair(old_extra={"user_rating": "5"})
    merge_updated_tiddlers([fresh], [old])
    assert fresh["user_rating"] == "5"


def test_latex_the_model_produces_always_wins():
    fresh = {"title": "DOC_EQ0001", "text": "...", "latex": "E=mc^2",
            "created": "1", "modified": "1"}
    old = {"title": "DOC_EQ0001", "text": "...", "latex": "E = mc^{2} (hand edit)",
          "created": "1", "modified": "1"}
    m = merge_updated_tiddlers([fresh], [old])
    assert fresh["latex"] == "E=mc^2"
    assert "latex" not in m["restored"].get("DOC_EQ0001", {})


def test_trailing_punct_kept_even_when_fresh_is_blank():
    """The projector always emits `trailing_punct` (as "" when the model has
    nothing) — 'present in both, fresh empty' must not blank a real split."""
    fresh = {"title": "DOC_EQ0001", "text": "...", "trailing_punct": "",
            "created": "1", "modified": "1"}
    old = {"title": "DOC_EQ0001", "text": "...", "trailing_punct": ".",
          "created": "1", "modified": "1"}
    merge_updated_tiddlers([fresh], [old])
    assert fresh["trailing_punct"] == "."


def test_spoken_correction_kept():
    fresh = {"title": "DOC_FO0001", "text": "...", "spoken": "e equals em c squared",
            "created": "1", "modified": "1"}
    old = {"title": "DOC_FO0001", "text": "...", "spoken": "E equals M C squared (fixed)",
          "created": "1", "modified": "1"}
    merge_updated_tiddlers([fresh], [old])
    assert fresh["spoken"] == "E equals M C squared (fixed)"


def test_latex_refined_and_its_evidence_kept_together():
    fresh = {"title": "DOC_EQ0001", "text": "...", "created": "1", "modified": "1"}
    old = {"title": "DOC_EQ0001", "text": "...", "latex_refined": "x^2",
          "refined_basis": "eprint", "refined_verified_by": "human",
          "refined_author": "alice", "created": "1", "modified": "1"}
    m = merge_updated_tiddlers([fresh], [old])
    assert fresh["latex_refined"] == "x^2"
    assert fresh["refined_basis"] == "eprint"
    assert fresh["refined_verified_by"] == "human"
    assert fresh["refined_author"] == "alice"
    # all absent from fresh -> restored, not "kept over a live disagreement"
    assert set(m["restored"]["DOC_EQ0001"]) >= {
        "latex_refined", "refined_basis", "refined_verified_by", "refined_author"}


def test_unmatched_old_title_is_listed_not_inserted():
    fresh = [{"title": "DOC_PARA_0001", "text": "x", "created": "1", "modified": "1"}]
    old = [{"title": "DOC_PARA_0001", "text": "x", "created": "1", "modified": "1"},
          {"title": "DOC_PARA_9999", "text": "stale, no such object any more",
           "created": "1", "modified": "1"}]
    m = merge_updated_tiddlers(fresh, old)
    assert m["unmatched"] == ["DOC_PARA_9999"]
    assert m["unmatched_by_kind"] == {"Paragraph": 1}
    assert [t["title"] for t in m["merged"]] == ["DOC_PARA_0001"]   # never inserted


def test_unmatched_title_that_does_not_parse_counts_as_unparsed():
    fresh = [{"title": "DOC", "text": "root", "created": "1", "modified": "1"}]
    old = [{"title": "DOC", "text": "root", "created": "1", "modified": "1"},
          {"title": "not-a-title-at-all", "text": "x", "created": "1", "modified": "1"}]
    m = merge_updated_tiddlers(fresh, old)
    assert m["unmatched"] == ["not-a-title-at-all"]
    assert m["unmatched_by_kind"] == {"unparsed": 1}


def test_restoring_a_dangling_transclusion_is_refused_and_counted():
    """The class this task's brief warns about directly: a hand-edit that
    embeds a transclusion the CURRENT object tree no longer has a title for
    must not be silently baked back in."""
    fresh = [{"title": "DOC_PARA_0001", "text": "fresh, footnote-free.",
             "created": "1", "modified": "1"}]
    old = [{"title": "DOC_PARA_0001",
           "text": "translated {{DOC_FN0099||FN}} prose.",
           # the base is UNCHANGED (matches the current fresh text) so this
           # is purely a dangling-target case, not a stale-base one.
           "text_source": "fresh, footnote-free.", "created": "1", "modified": "1"}]
    m = merge_updated_tiddlers(fresh, old)
    assert fresh[0]["text"] == "fresh, footnote-free."       # NOT overwritten
    assert "text" in m["refused_dangling"]["DOC_PARA_0001"]
    assert "DOC_FN0099" in m["refused_dangling"]["DOC_PARA_0001"]["text"]
    assert m["refused_stale_base"] == {}
    # the harmless sibling field still restores normally
    assert fresh[0]["text_source"] == "fresh, footnote-free."


def test_a_live_transclusion_target_is_not_refused():
    fresh = [{"title": "DOC_PARA_0001", "text": "fresh prose.",
             "created": "1", "modified": "1"},
            {"title": "DOC_FN0001", "text": "a footnote", "created": "1", "modified": "1"}]
    old = [{"title": "DOC_PARA_0001",
           "text": "translated {{DOC_FN0001||FN}} prose.",
           "text_source": "fresh prose.", "created": "1", "modified": "1"},
          {"title": "DOC_FN0001", "text": "a footnote", "created": "1", "modified": "1"}]
    m = merge_updated_tiddlers(fresh, old)
    assert fresh[0]["text"] == "translated {{DOC_FN0001||FN}} prose."
    assert m["refused_dangling"] == {}
    assert m["refused_stale_base"] == {}


def test_a_restored_prose_that_drops_a_live_citation_is_counted_newly_orphaned():
    """The OTHER direction from `refused_dangling` (penev_A, out/651.txt): the
    restore is not refused (the marker is not dangling, there is simply no
    marker at all any more) but a title that was reachable before the merge
    becomes unreferenced after it, and that must be counted, not silent."""
    fn_template = {"title": "FN", "text": "tpl", "created": "1", "modified": "1"}
    fresh = [{"title": "DOC_PARA_0001",
             "text": "fresh prose citing {{DOC_FN0001||FN}}.",
             "created": "1", "modified": "1"},
            {"title": "DOC_FN0001", "text": "a footnote", "created": "1", "modified": "1"},
            dict(fn_template)]
    old = [{"title": "DOC_PARA_0001",
           "text": "a hand-typed replacement with no footnote marker at all.",
           "text_source": "fresh prose citing {{DOC_FN0001||FN}}.",
           "created": "1", "modified": "1"},
          {"title": "DOC_FN0001", "text": "a footnote", "created": "1", "modified": "1"},
          dict(fn_template)]
    m = merge_updated_tiddlers(fresh, old)
    assert fresh[0]["text"] == old[0]["text"]          # the hand-work still wins
    assert m["newly_orphaned"] == ["DOC_FN0001"]
    assert m["refused_dangling"] == {}                 # not dangling -- orphaned
    assert m["refused_stale_base"] == {}                # base unchanged


def test_no_orphaning_when_nothing_was_reachable_to_begin_with():
    fresh = [{"title": "DOC_PARA_0001", "text": "fresh, footnote-free.",
             "created": "1", "modified": "1"}]
    old = [{"title": "DOC_PARA_0001", "text": "translated, also footnote-free.",
           "text_source": "orig.", "created": "1", "modified": "1"}]
    m = merge_updated_tiddlers(fresh, old)
    assert m["newly_orphaned"] == []


def test_merge_never_breaks_tiddler_integrity():
    fn_template = {"title": "FN", "text": "<$link to={{!!current-tiddler}}/>",
                   "created": "1", "modified": "1"}
    fresh = [{"title": "DOC_PARA_0001", "text": "fresh {{DOC_FN0001||FN}} prose.",
             "created": "1", "modified": "1"},
            {"title": "DOC_FN0001", "text": "a footnote", "created": "1", "modified": "1"},
            dict(fn_template)]
    old = [{"title": "DOC_PARA_0001",
           "text": "translated {{DOC_FN0001||FN}} prose.",
           "text_source": "orig.", "created": "1", "modified": "1"},
          {"title": "DOC_FN0001", "text": "a footnote", "created": "1", "modified": "1"},
          dict(fn_template),
          {"title": "DOC_PARA_9999", "text": "stale {{GONE||FN}}",
           "created": "1", "modified": "1"}]
    m = merge_updated_tiddlers(fresh, old)
    integ = tiddler_integrity(m["merged"])
    assert integ["dangling"] == []


def test_keep_list_is_exact_and_argued():
    """Every entry carries a real, non-empty reason; the conditional ones
    (text/caption) are marked as such by keep_list_report."""
    for field, entry in KEEP_LIST.items():
        assert entry.reason and len(entry.reason) > 20, field
    lines = keep_list_report()
    assert any(l.startswith("text [conditional") for l in lines)
    assert any(l.startswith("caption [conditional") for l in lines)
    assert any(l.startswith("trailing_punct:") for l in lines)   # unconditional


def test_is_hand_edited_predicate():
    assert _is_hand_edited({"created": "1", "modified": "1", "text_source": "x"})
    assert _is_hand_edited({"created": "1", "modified": "2"})
    assert not _is_hand_edited({"created": "1", "modified": "1"})
    assert not _is_hand_edited({})


# ---------------------------------------------------------------------------
# cmd_tiddlers(..., update=...) — end to end, through the real pipeline
# ---------------------------------------------------------------------------

def test_cmd_tiddlers_update_end_to_end():
    from pdfdrill.commands import cmd_model, cmd_tiddlers
    from pdfdrill.sidecar import Sidecar

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "doc651.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        (d / "doc651.lines.json").write_text(json.dumps({"pages": [
            {"page": 1, "image_id": "i", "lines": [
                {"id": "l1", "type": "text",
                 "text": "German prose here.",
                 "text_display": "German prose here."},
                {"id": "l2", "type": "equation", "text": "E=mc^2",
                 "text_display": "E=mc^2"},
            ]}]}))
        cmd_model(pdf, bibkey="doc651")
        out1 = cmd_tiddlers(pdf)
        assert "Wrote" in out1
        sc = Sidecar(pdf)
        fresh_path = sc.blob_dir / "doc651.tiddlers.json"
        fresh = json.loads(fresh_path.read_text(encoding="utf-8"))

        para = next(t for t in fresh if t.get("tags", "").startswith("paragraph"))
        eqs = [t for t in fresh if t.get("tags", "").startswith("equation")]
        assert eqs, "expected at least one Equation tiddler"
        eq = eqs[0]

        # Build the "old" array: a hand translation + wiki note on the
        # paragraph, and a hand-edited latex on the equation.
        old = json.loads(json.dumps(fresh))     # deep copy via round trip
        old_para = next(t for t in old if t["title"] == para["title"])
        old_para["text"] = "Translated English prose here."
        old_para["text_source"] = para["text"]
        old_para["note_check"] = "verified by hand"
        old_eq = next(t for t in old if t["title"] == eq["title"])
        old_eq["latex"] = "E = mc^{2} (should NOT survive)"
        # one stale title with no match in the fresh model
        old.append({"title": "doc651_PARA_9999", "text": "long gone",
                    "created": "1", "modified": "1"})
        old_path = d / "old.tiddlers.json"
        old_path.write_text(json.dumps(old))

        out2 = cmd_tiddlers(pdf, update=str(old_path))
        assert "restored" in out2 or "field(s) restored" in out2
        assert "1 old title(s) unmatched" in out2

        merged = json.loads(fresh_path.read_text(encoding="utf-8"))
        m_para = next(t for t in merged if t["title"] == para["title"])
        m_eq = next(t for t in merged if t["title"] == eq["title"])
        assert m_para["text"] == "Translated English prose here."
        assert m_para["note_check"] == "verified by hand"
        assert m_eq["latex"] == "E=mc^2"          # the model's, unchanged
        assert all(t["title"] != "doc651_PARA_9999" for t in merged)

        update_json = json.loads(
            (sc.blob_dir / "doc651.update.json").read_text(encoding="utf-8"))
        assert update_json["unmatched"] == ["doc651_PARA_9999"]
        assert para["title"] in update_json["restored"]
        assert update_json["newly_orphaned"] == []          # no citation dropped

        unmatched_json = json.loads(
            (sc.blob_dir / "doc651.update-unmatched.json").read_text(encoding="utf-8"))
        assert unmatched_json == ["doc651_PARA_9999"]

        from docops.projectors.tiddlywiki import tiddler_integrity
        integ = tiddler_integrity(merged)
        assert integ["dangling"] == []


def test_cmd_tiddlers_update_missing_file_reports_cleanly():
    """651 review, finding 3: a bad --update path must not discard the fresh
    projection that was already computed — the file must land on disk
    exactly as a plain `tiddlers` run would, not be silently skipped."""
    from pdfdrill.commands import cmd_model, cmd_tiddlers
    from pdfdrill.sidecar import Sidecar
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "doc651b.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        (d / "doc651b.lines.json").write_text(json.dumps({"pages": [
            {"page": 1, "image_id": "i", "lines": [
                {"id": "l1", "type": "text", "text": "hi", "text_display": "hi"}]}]}))
        cmd_model(pdf, bibkey="doc651b")
        out = cmd_tiddlers(pdf, update=str(d / "does-not-exist.json"))
        assert "does not exist" in out
        assert "still written" in out
        fresh_path = Sidecar(pdf).blob_dir / "doc651b.tiddlers.json"
        assert fresh_path.is_file() and fresh_path.stat().st_size > 0
        tiddlers = json.loads(fresh_path.read_text(encoding="utf-8"))
        assert len(tiddlers) > 0


def test_cmd_tiddlers_update_bad_json_still_writes_the_fresh_file():
    """The other half of finding 3: a path that exists but fails to parse."""
    from pdfdrill.commands import cmd_model, cmd_tiddlers
    from pdfdrill.sidecar import Sidecar
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "doc651c.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        (d / "doc651c.lines.json").write_text(json.dumps({"pages": [
            {"page": 1, "image_id": "i", "lines": [
                {"id": "l1", "type": "text", "text": "hi", "text_display": "hi"}]}]}))
        cmd_model(pdf, bibkey="doc651c")
        bad = d / "not-json.json"
        bad.write_text("{not valid json")
        out = cmd_tiddlers(pdf, update=str(bad))
        assert "could not read/parse" in out
        assert "still written" in out
        fresh_path = Sidecar(pdf).blob_dir / "doc651c.tiddlers.json"
        assert fresh_path.is_file() and fresh_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# 651 review, finding 1 — the `ref_source` false positive
# ---------------------------------------------------------------------------

def _stub_reference(citekey="smith2020"):
    return {"title": f"DOC_REF_{citekey}",
           "text": f"{{{{||CIT}}}} Reference not yet resolved: `{citekey}`",
           "tags": "reference stub DOC", "kind": "reference", "citekey": citekey,
           "year": "", "authors": "", "entry_type": "misc",
           "stub": "true", "ref_source": "citation",
           "created": "1", "modified": "1"}


def _resolved_reference(citekey="smith2020"):
    return {"title": f"DOC_REF_{citekey}",
           "text": "{{||CIT}} Smith, J. (2020). A real paper title.",
           "tags": "reference bibentry bibtex DOC", "kind": "reference",
           "citekey": citekey, "year": "2020", "authors": "Smith, J.",
           "entry_type": "article", "created": "1", "modified": "1"}


def test_a_resolved_reference_is_not_reverted_by_the_old_stubs_ref_source():
    """The reviewer's own live reproduction: `ref_source` ends in `_source`
    but is NOT a translation marker — it is the projector's OWN provenance
    tag on every stub Reference. Before the fix, `_is_hand_edited` treated
    its mere presence on the OLD stub as proof of hand-work and reverted a
    freshly-resolved bibliography entry back to its unresolved placeholder."""
    fresh = [_resolved_reference()]
    old = [_stub_reference()]
    m = merge_updated_tiddlers(fresh, old)
    assert fresh[0]["text"] == "{{||CIT}} Smith, J. (2020). A real paper title."
    assert "stub" not in fresh[0]                  # not reattached either
    assert "ref_source" not in fresh[0]
    assert m["restored"] == {}
    assert m["refused_dangling"] == {} and m["refused_stale_base"] == {}


def test_a_stub_reference_that_is_still_a_stub_is_unaffected():
    """The other state named in the review: OLD and FRESH both still stubs
    (bibliography never ran) — nothing to restore, nothing corrupted."""
    fresh = [_stub_reference()]
    old = [_stub_reference()]
    m = merge_updated_tiddlers(fresh, old)
    assert fresh[0]["stub"] == "true"
    assert fresh[0]["text"].startswith("{{||CIT}} Reference not yet resolved")
    assert m["restored"] == {}


def test_ref_source_alone_no_longer_trips_is_hand_edited():
    assert not _is_hand_edited(
        {"created": "1", "modified": "1", "ref_source": "citation"})
    # the real translation markers still do
    assert _is_hand_edited({"created": "1", "modified": "1", "text_source": "x"})
    assert _is_hand_edited({"created": "1", "modified": "1", "translated_lang": "EN-US"})


# ---------------------------------------------------------------------------
# 651 review, finding 2 — content moved between builds (`refused_stale_base`)
# ---------------------------------------------------------------------------

def test_stale_base_conflict_is_refused_and_counted():
    """The hazard named in the dispatch and confirmed by the reviewer: a
    translated paragraph whose UNDERLYING prose was legitimately corrected
    (an OCR fix, a re-split) between the OLD build and the FRESH one. OLD's
    own `text_source` (the baseline it captured at build time) no longer
    matches the model's CURRENT untranslated rendering — restoring OLD's
    translation would silently discard that correction. Must be refused
    and counted, not silently applied."""
    fresh = [{"title": "DOC_PARA_0001", "text": "Corrected fresh prose (OCR fix).",
             "created": "1", "modified": "1"}]
    old = [{"title": "DOC_PARA_0001", "text": "Translated OLD prose.",
           "text_source": "Stale OLD prose (pre-fix).",
           "created": "1", "modified": "1"}]
    m = merge_updated_tiddlers(fresh, old)
    assert fresh[0]["text"] == "Corrected fresh prose (OCR fix)."   # NOT overwritten
    assert "text" in m["refused_stale_base"]["DOC_PARA_0001"]
    assert m["refused_dangling"] == {}                              # different class


def test_unchanged_base_restores_normally():
    """The control: when OLD's baseline DOES match the model's current
    rendering, the translation still applies — this is the ordinary case
    the whole feature exists for, and the new guard must not block it."""
    fresh = [{"title": "DOC_PARA_0001", "text": "Unchanged fresh prose.",
             "created": "1", "modified": "1"}]
    old = [{"title": "DOC_PARA_0001", "text": "Translated OLD prose.",
           "text_source": "Unchanged fresh prose.",
           "created": "1", "modified": "1"}]
    m = merge_updated_tiddlers(fresh, old)
    assert fresh[0]["text"] == "Translated OLD prose."
    assert m["refused_stale_base"] == {}
    assert "text" in m["restored"]["DOC_PARA_0001"]


def test_stale_base_conflict_has_no_signal_for_a_bare_wiki_edit():
    """Documents the remaining, unguardable gap (out/651.txt CONCERNS): a
    bare hand-edit with no `_source` backup carries no baseline at all, so
    `_stale_base_conflict` cannot see a moved base for it — it simply
    doesn't fire, and the hand-edit is restored on the modified>created
    signal alone, exactly as before. Not a bug; the documented limit."""
    fresh = [{"title": "DOC_PARA_0001", "text": "fresh, possibly different now.",
             "created": "1", "modified": "1"}]
    old = [{"title": "DOC_PARA_0001", "text": "hand-edited in the wiki.",
           "created": "1", "modified": "2"}]           # no text_source at all
    m = merge_updated_tiddlers(fresh, old)
    assert fresh[0]["text"] == "hand-edited in the wiki."
    assert m["refused_stale_base"] == {}
