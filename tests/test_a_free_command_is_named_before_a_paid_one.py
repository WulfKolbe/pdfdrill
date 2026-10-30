"""The free offline reader was never named, so 16 documents were told to pay.

The owner drilled the 15 YACCLAB papers plus one more with a fresh clone on
2026-10-28 and reported two symptoms: no LaTeX in the markdown, and wrong
geometry. Measured, the clone was fine — `pdfdrill drill` on a born-digital
non-arXiv paper takes `_write_born_digital_lines`, whose reading declares
`pdfminer-chars`, is framed in PDF POINTS and is untyped (2016icpr: 274 lines,
all `text`). The same command on a machine with every extra and the patched
pdfminer produces exactly the same file, so nothing about the install was
broken.

What IS broken is what pdfdrill then says. `pdfminer-chars` is excluded from
`commands._TYPED_GEOMETRY_SOURCES` (its regions are points), so
`lines:typed-geometry` is unsatisfied and `inspect`'s prerequisite is missing.
Three commands can satisfy that condition:

    mathpix     done_when: lines:typed-geometry     PAID
    gemmaocr    done_when: lines:typed-geometry     metered
    glyphlines  done_when: file:{stem}.lines.json   FREE, offline

`glyphlines` really does satisfy it — measured on 2018jrtip, it writes
`pdfminer-docmodel` in a 2067x2923 PIXEL frame with 1172 TYPED lines (11 math,
128 list_item, 12 code, 7 section_header, 2 title) where the chars route gave
1240 untyped ones. But `planner.equivalent_commands` groups satisfiers by STRING
EQUALITY of `done_when`, so the free command never joined the class and the
refusal named only the two that cost money.

Why `glyphlines`' own `done_when` is NOT simply changed to the condition:
sampled over 40 of the library's `pdfminer-docmodel` readings, 35 carry a
typed-family line in their first three pages and 5 do not, so the stronger
condition would report `glyphlines` as "not done" on about an eighth of
documents after it had run perfectly well. A command declares what it ALSO
satisfies instead.
"""
from __future__ import annotations

from pdfdrill import planner


def _manifest():
    return planner.load_manifest()


def test_glyphlines_declares_that_it_satisfies_typed_geometry():
    """The free reader's own entry has to say so; nothing can infer it."""
    man = _manifest()
    by_name = {c["name"]: c for c in man["commands"]}
    g = by_name["glyphlines"]
    assert g.get("also_satisfies") == "lines:typed-geometry", (
        "glyphlines writes pdfminer-docmodel, which IS typed geometry")
    assert g.get("done_when") == "file:{stem}.lines.json", (
        "its own done_when stays the weaker one — 5 of 40 sampled readings "
        "carry no typed-family line in their first three pages")
    assert not g.get("network"), "glyphlines is free and offline"


def test_the_free_reader_joins_the_paid_ones_equivalence_class():
    alts = planner.equivalent_commands(_manifest())
    assert "glyphlines" in alts["mathpix"], (
        "a paid prerequisite must know the free command that satisfies it")
    assert "glyphlines" in alts["gemmaocr"]
    assert alts["glyphlines"] >= {"mathpix", "gemmaocr", "glyphlines"}


def test_every_free_satisfier_of_a_paid_condition_is_reachable():
    """The general rule, not just this one pair: if a non-network command
    satisfies the same condition as a paid one, the paid command's alternatives
    must include it. Otherwise pdfdrill charges for what it can do for free."""
    man = _manifest()
    paid = planner.network_commands(man)
    alts = planner.equivalent_commands(man)
    cmds = {c["name"]: c for c in man["commands"]}

    def conditions(c):
        """The conditions a command meets. An ABSENT condition is not a
        condition — comparing on a missing one made every command with no
        `done_when` look equivalent to every other (the first version of this
        test said 130 commands satisfied `bibfetch`)."""
        return {x for x in (c.get("done_when"), c.get("also_satisfies")) if x}

    for p in sorted(paid):
        want = conditions(cmds[p])
        if not want:
            continue
        free = {n for n, c in cmds.items()
                if n != p and not c.get("network") and conditions(c) & want}
        missing = free - alts.get(p, set())
        assert not missing, (
            f"{p} is paid and {sorted(missing)} satisfy {sorted(want)} "
            f"for free, but the planner does not name them")


def test_the_refusal_names_the_free_command_first(tmp_path):
    """What the operator reads. The free option must be in the sentence, and
    marked free — the message that cost this batch named only `mathpix (paid)`
    and `gemmaocr`."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    out = planner.describe("inspect", pdf)
    assert "mathpix" in out
    assert "glyphlines" in out, (
        "a free offline command satisfies this prerequisite and was not named")
    assert "free" in out.lower(), "and it has to be marked as free"
