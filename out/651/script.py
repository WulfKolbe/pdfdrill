"""651 evidence, penev_A. Real CLI (cmd_tiddlers), no mocks.

FIX ROUND 1 (task-651-review.md) added three more scenarios (B, C, D) to
the original run (A), because the review's finding 2 is exactly right: A's
"0 unmatched" cannot fail, because A never changes the model between the
OLD build and the FRESH one -- it is the case that PROVES NOTHING about
content having moved, and reporting it as confirmation of that (the
original wording) was the defect. B, C, D exercise the three fix-round-1
findings directly, live, on this document.

A. Copy the CURRENT penev_A.tiddlers.json as "old". Hand-modify three
   fields in the copy: a translation on one Paragraph (with a text_source
   marker matching the CURRENT fresh text -- an UNCHANGED base, so this
   scenario tests only "the translation still applies", never "the model
   changed under it"), a wiki-added `note` field on one Formula, a
   hand-edited `latex` on one Equation (the model must win this one back).
   Rebuild fresh, then --update. Expect: 2 restorations (translation +
   note), latex won back, 0 unmatched -- and explicitly NOT evidence that
   a moved base is handled; see B.
B. NEW (finding 2, live). Same translated Paragraph, but this time OLD's
   `text_source` is deliberately WRONG -- a stale baseline that does NOT
   match the model's current untranslated rendering, simulating an OCR fix
   between the two builds. Expect: `refused_stale_base` fires, the fresh
   (corrected) text wins, NOT the translation.
C. NEW (finding 1, live). penev_A's own 52 References are all STUBS (no
   `bibfetch` was ever run on this corpus, confirmed below) so there is no
   naturally-resolved Reference to rebuild the MODEL into, and
   `cmd_tiddlers` always regenerates its own "fresh" side straight from the
   model -- it cannot be handed a fake fresh array. Reproduced instead by
   calling `merge_updated_tiddlers` directly (the exact function
   `cmd_tiddlers` calls internally): OLD is this document's own, REAL,
   unmodified stub tiddler; FRESH is a hand-built RESOLVED counterpart in
   the projector's own real shape (no `stub`/`ref_source` keys, filled
   `text`/`year`/`authors`). Expect: the resolved text and fields survive;
   `stub`/`ref_source` are NOT reattached.
D. NEW (finding 3, live). `--update` with a path that does not exist.
   Expect: the fresh tiddlers.json is still written and non-empty (not
   discarded), and the return message says so.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/wkolbe/MX/PDFDRILL/src")

DOC = Path("/home/wkolbe/pdfdrill-library/penev_A")
PDF = DOC / "penev_A.pdf"
LIVE = DOC / "penev_A.tiddlers.json"
OLD_COPY = DOC / "out" / "651" / "old_hand_edited.tiddlers.json"
OLD_COPY_STALE = DOC / "out" / "651" / "old_stale_base.tiddlers.json"
OLD_COPY_STUB = DOC / "out" / "651" / "old_still_stub_reference.tiddlers.json"

PARA_TITLE = "penev_A_PARA_0006"
FO_TITLE = "penev_A_FO0001"
EQ_TITLE = "penev_A_EQ0001"
REF_TITLE = "penev_A_REF_Atick1995"      # a real, live stub citekey on this doc


def main():
    from pdfdrill.commands import cmd_tiddlers
    from docops.projectors.tiddlywiki import tiddler_integrity

    live_before = json.loads(LIVE.read_text(encoding="utf-8"))
    print(f"BEFORE: {len(live_before)} tiddlers in the live file (this run's baseline).")

    refs = [t for t in live_before if t.get("tags", "").startswith("reference")]
    resolved_already = [t for t in refs if not t.get("stub")]
    print(f"References on this corpus: {len(refs)} total, "
          f"{len(resolved_already)} already resolved (confirms C's premise: "
          f"{'none resolved, fake one below' if not resolved_already else 'unexpected, see result.json'}).")

    # ---- A: copy, then hand-edit 3 fields (UNCHANGED base). ----
    old = json.loads(json.dumps(live_before))
    para = next(t for t in old if t["title"] == PARA_TITLE)
    fo = next(t for t in old if t["title"] == FO_TITLE)
    eq = next(t for t in old if t["title"] == EQ_TITLE)

    original_para_text = para["text"]
    para["text_source"] = original_para_text        # UNCHANGED base, on purpose
    para["text"] = ("[EN] So far, however, the most practical and systematic "
                    "method has been PCA... (hand translation, 651 evidence)")

    original_fo_latex = fo.get("latex")
    fo["note_review"] = "checked against the printed page by hand, 651 evidence"

    original_eq_latex = eq.get("latex")
    eq["latex"] = "R(x, y) = HAND-EDITED-SHOULD-NOT-SURVIVE"

    OLD_COPY.parent.mkdir(parents=True, exist_ok=True)
    OLD_COPY.write_text(json.dumps(old), encoding="utf-8")
    print(f"\nWrote A's hand-edited copy: {OLD_COPY}")
    print(f"  {PARA_TITLE}.text  -> translated (+text_source == the CURRENT fresh text)")
    print(f"  {FO_TITLE}.note_review -> new wiki note")
    print(f"  {EQ_TITLE}.latex  -> hand-edited (must NOT survive)")

    # ---- B: same translation, but text_source is a STALE baseline. ----
    old_stale = json.loads(json.dumps(old))
    stale_para = next(t for t in old_stale if t["title"] == PARA_TITLE)
    stale_para["text_source"] = ("[STALE PRE-OCR-FIX BASELINE] et al. 1995. "
                                 "So far, however, PCA has bene the most practical "
                                 "and systemtaic method... (deliberately wrong, "
                                 "651 evidence -- does NOT match the real fresh text)")
    OLD_COPY_STALE.write_text(json.dumps(old_stale), encoding="utf-8")
    print(f"\nWrote B's copy (stale text_source baseline): {OLD_COPY_STALE}")

    # ---- C: penev_A has NO resolved Reference to rebuild the model into, so
    # this cannot go through `cmd_tiddlers` (which always regenerates its
    # OWN "fresh" side straight from the model, ignoring any hand-edit to
    # the live file) -- confirmed above (0 of 52 resolved) and unsurprising
    # (`bibfetch` is a paid Perplexity call, never run on this corpus, and
    # this task must not run a paid command to manufacture evidence).
    # Reproduced instead at the exact function `cmd_tiddlers` itself calls,
    # `tiddlywiki.merge_updated_tiddlers`, with the OLD side 100% REAL
    # corpus data (this document's own, unmodified stub tiddler) and the
    # FRESH side a hand-built RESOLVED counterpart in the projector's own
    # real shape (no `stub`/`ref_source` keys; filled text/year/authors/
    # entry_type -- see tiddlywiki.py's Reference loop, `if is_stub: ...
    # else: ...`) -- simulating exactly what THIS document's OWN model
    # would project after `bibliography`/`bibfetch` resolved this citekey.
    ref_stub_real = next(t for t in live_before if t["title"] == REF_TITLE)
    assert ref_stub_real.get("stub") == "true", "premise: this REF is a stub"
    ref_resolved_fake = json.loads(json.dumps(ref_stub_real))
    ref_resolved_fake.pop("stub", None)
    ref_resolved_fake.pop("ref_source", None)
    ref_resolved_fake["text"] = ("{{||CIT}} Atick, J. J. (1995). Could information "
                                 "theory provide an ecological theory of sensory "
                                 "processing? Network 3.")
    ref_resolved_fake["year"] = "1995"
    ref_resolved_fake["authors"] = "Atick, J. J."
    ref_resolved_fake["entry_type"] = "article"
    ref_resolved_fake["tags"] = ref_resolved_fake["tags"].replace(
        "reference stub", "reference bibentry bibtex")

    OLD_COPY_STUB.write_text(json.dumps([ref_stub_real]), encoding="utf-8")
    (DOC / "out" / "651" / "fresh_resolved_fake.tiddlers.json").write_text(
        json.dumps([ref_resolved_fake]), encoding="utf-8")
    print(f"\nWrote C's OLD (the REAL, unmodified stub): {OLD_COPY_STUB}")
    print(f"  Wrote C's simulated FRESH (hand-built resolved counterpart, "
          f"real shape): {DOC / 'out' / '651' / 'fresh_resolved_fake.tiddlers.json'}")

    # ---- run: fresh rebuild would erase C's fake resolution, so write it AFTER. ----
    out_fresh = cmd_tiddlers(PDF, bibkey="penev_A")
    print("\n--- fresh rebuild (A/B baseline) ---")
    print(out_fresh)
    fresh = json.loads(LIVE.read_text(encoding="utf-8"))
    fresh_titles = {t["title"] for t in fresh}
    old_titles = {t["title"] for t in old}
    unmatched_expected = sorted(old_titles - fresh_titles)
    print(f"\nTitle sets: fresh={len(fresh_titles)} old={len(old_titles)} "
          f"unmatched(expected, direct diff)={len(unmatched_expected)} "
          f"-- NOTE: this equality is guaranteed by construction (the model "
          f"did not change), not evidence about a moved-content case; see B.")

    # ---- A: --update with the hand-edited copy (unchanged base). ----
    out_update_a = cmd_tiddlers(PDF, bibkey="penev_A", update=str(OLD_COPY))
    print("\n--- A: --update (unchanged base) ---")
    print(out_update_a)

    merged_a = json.loads(LIVE.read_text(encoding="utf-8"))
    m_para = next(t for t in merged_a if t["title"] == PARA_TITLE)
    m_fo = next(t for t in merged_a if t["title"] == FO_TITLE)
    m_eq = next(t for t in merged_a if t["title"] == EQ_TITLE)
    # snapshot A's own update records into out/651/ (rule 19/20 -- evidence
    # lives beside the document, not only transiently at the document root)
    # BEFORE the end-of-run cleanup removes the root copies.
    import shutil as _shutil
    _shutil.copy(DOC / "penev_A.update.json", DOC / "out" / "651" / "update.json")
    _shutil.copy(DOC / "penev_A.update-unmatched.json",
                DOC / "out" / "651" / "update-unmatched.json")
    update_record_a = json.loads((DOC / "penev_A.update.json").read_text(encoding="utf-8"))
    unmatched_record_a = json.loads(
        (DOC / "penev_A.update-unmatched.json").read_text(encoding="utf-8"))
    integ_a = tiddler_integrity(merged_a)

    print("A RESULT: PARA text restored:", m_para["text"] == para["text"])
    print("A RESULT: FO note_review restored:", m_fo.get("note_review"))
    print("A RESULT: EQ latex model-won:", m_eq.get("latex") == original_eq_latex)
    print("A RESULT: unmatched:", unmatched_record_a)
    print("A RESULT: refused_stale_base:", update_record_a["refused_stale_base"])
    print("A RESULT: integrity dangling:", integ_a["dangling"])

    # restore the live file to A's baseline (post fresh-rebuild) before B/C/D,
    # so each scenario starts from the SAME, known state.
    LIVE.write_text(json.dumps(fresh, indent=1), encoding="utf-8")

    # ---- B: --update with the STALE-baseline copy. ----
    out_update_b = cmd_tiddlers(PDF, bibkey="penev_A", update=str(OLD_COPY_STALE))
    print("\n--- B: --update (STALE text_source baseline) ---")
    print(out_update_b)
    merged_b = json.loads(LIVE.read_text(encoding="utf-8"))
    m_para_b = next(t for t in merged_b if t["title"] == PARA_TITLE)
    update_record_b = json.loads((DOC / "penev_A.update.json").read_text(encoding="utf-8"))
    print("B RESULT: PARA text is the FRESH value (guard fired), not the translation:",
         m_para_b["text"] != stale_para["text"])
    print("B RESULT: refused_stale_base:", update_record_b["refused_stale_base"])

    LIVE.write_text(json.dumps(fresh, indent=1), encoding="utf-8")

    # ---- C: called DIRECTLY at the merge-function level (see the comment
    # above -- cmd_tiddlers cannot be fed a fake "fresh", it always
    # regenerates its own from the real model, which has no resolved
    # References to regenerate from).
    from docops.projectors.tiddlywiki import merge_updated_tiddlers as _merge_c
    fresh_for_c = [json.loads(json.dumps(ref_resolved_fake))]   # own copy, mutated in place
    old_for_c = [json.loads(json.dumps(ref_stub_real))]
    m_c = _merge_c(fresh_for_c, old_for_c)
    m_ref = fresh_for_c[0]
    print("\n--- C: merge_updated_tiddlers(fresh=[RESOLVED], old=[REAL STUB]) ---")
    print("C RESULT: REF text is still the RESOLVED text (not reverted):",
         m_ref["text"] == ref_resolved_fake["text"])
    print("C RESULT: REF has no stub/ref_source reattached:",
         "stub" not in m_ref and "ref_source" not in m_ref)
    print("C RESULT: restored for this title:", m_c["restored"].get(REF_TITLE, {}))
    print("C RESULT: merged tiddler:", m_ref)

    # ---- D: bad --update path; the fresh file must still stand. ----
    before_d = LIVE.read_text(encoding="utf-8")
    out_update_d = cmd_tiddlers(PDF, bibkey="penev_A",
                                update=str(DOC / "out" / "651" / "does-not-exist.json"))
    print("\n--- D: --update (missing path) ---")
    print(out_update_d)
    after_d = LIVE.read_text(encoding="utf-8")
    print("D RESULT: fresh file still present and non-empty:", LIVE.is_file() and len(after_d) > 0)
    print("D RESULT: 'still written' in the message:", "still written" in out_update_d)
    # content equality, ignoring `created`/`modified` (cmd_tiddlers stamps a
    # fresh wall-clock timestamp on EVERY call, so byte-for-byte equality
    # across two separate invocations would spuriously fail on timing alone).
    def _sig(tiddlers):
        return sorted((t.get("title"), {k: v for k, v in t.items()
                                        if k not in ("created", "modified")}.items())
                      for t in tiddlers)
    print("D RESULT: fresh file's CONTENT unchanged by the failed --update "
         "(still the plain projection, timestamps aside):",
         _sig(json.loads(after_d)) == _sig(fresh))

    result = {
        "A_unchanged_base": {
            "para_text_restored": m_para["text"] == para["text"],
            "para_text_source_restored": m_para.get("text_source") == original_para_text,
            "fo_note_restored": m_fo.get("note_review"),
            "eq_latex_model_won": m_eq.get("latex") == original_eq_latex,
            "restored_titles": list(update_record_a["restored"].keys()),
            "restored_fields_by_title": {k: list(v) for k, v in update_record_a["restored"].items()},
            "unmatched": unmatched_record_a,
            "refused_stale_base": update_record_a["refused_stale_base"],
            "dangling": integ_a["dangling"],
        },
        "B_stale_base_conflict": {
            "para_text_is_fresh_not_translation": m_para_b["text"] != stale_para["text"],
            "para_text_final": m_para_b["text"][:120],
            "refused_stale_base": update_record_b["refused_stale_base"],
        },
        "C_resolved_reference_not_reverted": {
            "note": "OLD is REAL corpus data (this doc's own unmodified stub "
                    "tiddler for penev_A_REF_Atick1995); FRESH is a hand-built "
                    "resolved counterpart in the real projector shape -- "
                    "cmd_tiddlers cannot be fed a fake fresh side, so this "
                    "calls merge_updated_tiddlers directly (the same function "
                    "cmd_tiddlers calls internally).",
            "ref_text_matches_resolved": m_ref["text"] == ref_resolved_fake["text"],
            "no_stub_reattached": "stub" not in m_ref and "ref_source" not in m_ref,
            "restored_for_this_title": m_c["restored"].get(REF_TITLE, {}),
        },
        "D_bad_update_path_still_writes_fresh": {
            "fresh_file_present": LIVE.is_file(),
            "message_says_still_written": "still written" in out_update_d,
            "fresh_file_unchanged": _sig(json.loads(after_d)) == _sig(fresh),
        },
    }
    (DOC / "out" / "651" / "result.json").write_text(
        json.dumps(result, indent=1), encoding="utf-8")

    # restore the live file (and the REF stub state) to its ORIGINAL pre-experiment
    # bytes so this evidence run leaves no lasting change to the document.
    LIVE.write_text(json.dumps(live_before, indent=1), encoding="utf-8")
    for p in (DOC / "penev_A.update.json", DOC / "penev_A.update-unmatched.json"):
        if p.exists():
            p.unlink()
    print(f"\nLive file restored to its pre-experiment state ({len(live_before)} tiddlers).")


if __name__ == "__main__":
    main()
