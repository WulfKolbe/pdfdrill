"""651 evidence, penev_A. Real CLI (cmd_tiddlers), no mocks.

1. Copy the CURRENT penev_A.tiddlers.json as "old".
2. Hand-modify three fields in the copy: a translation on one Paragraph
   (with a text_source marker, exactly how `pdfdrill translate`'s tiddler
   pass leaves one), a wiki-added `note` field on one Formula, a hand-edited
   `latex` on one Equation (the model must win this one back).
3. `pdfdrill tiddlers penev_A.pdf` (fresh, no --update) -- overwrites the
   live file with an ordinary, unmodified projection.
4. `pdfdrill tiddlers penev_A.pdf --update <old-copy>` -- merge.
5. Report: fields restored (expect 2: the translation text + the note),
   the latex the model won back, unmatched titles (expect 0), integrity.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/wkolbe/MX/PDFDRILL/src")

DOC = Path("/home/wkolbe/pdfdrill-library/penev_A")
PDF = DOC / "penev_A.pdf"
LIVE = DOC / "penev_A.tiddlers.json"
OLD_COPY = DOC / "out" / "651" / "old_hand_edited.tiddlers.json"

PARA_TITLE = "penev_A_PARA_0006"
FO_TITLE = "penev_A_FO0001"
EQ_TITLE = "penev_A_EQ0001"


def main():
    from pdfdrill.commands import cmd_tiddlers
    from docops.projectors.tiddlywiki import tiddler_integrity

    live_before = json.loads(LIVE.read_text(encoding="utf-8"))
    print(f"BEFORE: {len(live_before)} tiddlers in the live file (this run's baseline).")

    # step 1+2: copy, then hand-edit 3 fields.
    old = json.loads(json.dumps(live_before))
    para = next(t for t in old if t["title"] == PARA_TITLE)
    fo = next(t for t in old if t["title"] == FO_TITLE)
    eq = next(t for t in old if t["title"] == EQ_TITLE)

    original_para_text = para["text"]
    para["text_source"] = original_para_text
    para["text"] = ("[EN] So far, however, the most practical and systematic "
                    "method has been PCA... (hand translation, 651 evidence)")

    original_fo_latex = fo.get("latex")
    fo["note_review"] = "checked against the printed page by hand, 651 evidence"

    original_eq_latex = eq.get("latex")
    eq["latex"] = "R(x, y) = HAND-EDITED-SHOULD-NOT-SURVIVE"

    OLD_COPY.parent.mkdir(parents=True, exist_ok=True)
    OLD_COPY.write_text(json.dumps(old), encoding="utf-8")
    print(f"Wrote hand-edited copy: {OLD_COPY}")
    print(f"  {PARA_TITLE}.text  -> translated (+text_source marker)")
    print(f"  {FO_TITLE}.note_review -> new wiki note")
    print(f"  {EQ_TITLE}.latex  -> hand-edited (must NOT survive)")

    # step 3: fresh rebuild, no --update.
    out_fresh = cmd_tiddlers(PDF, bibkey="penev_A")
    print("\n--- fresh rebuild ---")
    print(out_fresh)
    fresh = json.loads(LIVE.read_text(encoding="utf-8"))
    fresh_titles = {t["title"] for t in fresh}
    old_titles = {t["title"] for t in old}
    unmatched_expected = sorted(old_titles - fresh_titles)
    print(f"\nTitle sets: fresh={len(fresh_titles)} old={len(old_titles)} "
          f"unmatched(expected, direct diff)={len(unmatched_expected)}")

    # step 4: --update with the hand-edited copy.
    out_update = cmd_tiddlers(PDF, bibkey="penev_A", update=str(OLD_COPY))
    print("\n--- --update ---")
    print(out_update)

    merged = json.loads(LIVE.read_text(encoding="utf-8"))
    m_para = next(t for t in merged if t["title"] == PARA_TITLE)
    m_fo = next(t for t in merged if t["title"] == FO_TITLE)
    m_eq = next(t for t in merged if t["title"] == EQ_TITLE)

    update_record = json.loads(
        (DOC / "penev_A.update.json").read_text(encoding="utf-8"))
    unmatched_record = json.loads(
        (DOC / "penev_A.update-unmatched.json").read_text(encoding="utf-8"))

    integ = tiddler_integrity(merged)

    print("\n=== RESULT ===")
    print("PARA text restored:", m_para["text"] == para["text"], "->", m_para["text"][:80])
    print("PARA text_source restored:", m_para.get("text_source") == original_para_text)
    print("FO note_review restored:", m_fo.get("note_review"))
    print("EQ latex is the MODEL's (won back), not the hand edit:",
          m_eq.get("latex") == original_eq_latex, "->", m_eq.get("latex"))
    print("fields restored, by title:", {k: list(v) for k, v in update_record["restored"].items()})
    print("unmatched titles (record):", unmatched_record)
    print("integrity dangling:", integ["dangling"])
    print("integrity orphan_synthetic:", integ["orphan_synthetic"])
    print("integrity orphan_ref:", integ["orphan_ref"])

    result = {
        "para_text_restored": m_para["text"] == para["text"],
        "para_text_source_restored": m_para.get("text_source") == original_para_text,
        "fo_note_restored": m_fo.get("note_review"),
        "eq_latex_model_won": m_eq.get("latex") == original_eq_latex,
        "eq_latex_final": m_eq.get("latex"),
        "restored_titles": list(update_record["restored"].keys()),
        "restored_fields_by_title": {k: list(v) for k, v in update_record["restored"].items()},
        "unmatched": unmatched_record,
        "dangling": integ["dangling"],
        "orphan_synthetic": integ["orphan_synthetic"],
        "orphan_ref": integ["orphan_ref"],
        "tiddlers_count": len(merged),
    }
    (DOC / "out" / "651" / "result.json").write_text(
        json.dumps(result, indent=1), encoding="utf-8")

    # restore the live file to its pre-experiment state so this evidence run
    # leaves no lasting change to the document's own tiddlers.json.
    LIVE.write_text(json.dumps(live_before, indent=1), encoding="utf-8")
    print(f"\nLive file restored to its pre-experiment state ({len(live_before)} tiddlers).")


if __name__ == "__main__":
    main()
