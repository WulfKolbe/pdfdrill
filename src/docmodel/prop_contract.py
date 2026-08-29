"""
290 — the props table: every DocObject prop, who writes it, who reads it.

GENERATED, not written. `tools/propstable.py` walks the corpus for the names
and `src/**/*.py` for the writers and readers, and emits
`docs/layers/PROPS.md`. Nothing in this module is a hand-kept list of props;
the only hand-written thing is a REASON for a prop nothing reads, which is the
same shape `type_contract.IGNORED` has and exists for the same purpose.

Why a fourth contract. 250 asks whether every TYPE is named, 255 whether every
FIELD is read, 260 whether every VALUE under a read field is handled — all
three about MathPix's output. This one is about OURS, and the failure it
catches is the one that keeps recurring: a capability exists, is written down,
and is rebuilt anyway. `subtype` sat unread on 1,239,021 lines; `list_item` was
unread in 882 documents; `code` was called dropped entirely when 97.5% of it
was already recovered.

THE PAIRS, because a wrong choice between them compiles silently:

    latex / latex_original   `latex` and `latex_code` hold the macro-EXPANDED
        form; `latex_original` holds the author's, macros intact. The renderer
        compiles the expanded one, which is why it needs no author preamble to
        resolve macros (289): original+author scored 70/176 against
        expanded+generic 151/207.
    latex_pretail / trailing_punct   `trailing_punct` is punctuation printed
        AFTER the maths and set beside it, never inside (025). `latex_pretail`
        is maths that trails the value and belongs to the following prose.
        Both are held out of `latex`; putting either back changes what renders.
    latex_refined   a VERIFIED refinement in a TWIN prop, because `latex` is
        never overwritten (232). A consumer reading `latex` alone silently
        ignores every accepted repair, which is what 233 had to build.
"""
from __future__ import annotations

import json
from pathlib import Path

CORPUS = Path(__file__).with_name("corpus_props.json")
CODE = Path(__file__).with_name("props_code.json")
TABLE = Path(__file__).resolve().parents[2] / "docs" / "layers" / "PROPS.md"

#: A prop with no `props.get("x")` / `props["x"]` reader -> why not.
#:
#: Every one of these IS mentioned somewhere in the source — through a constant
#: (`REFINED_FIELD = "latex_refined"`), a `setdefault`, or membership in a tuple
#: of key names. That is weaker than a reader and it is not the same as
#: untouched, so the distinction is kept rather than flattened.
NO_READER_REASON: dict[str, str] = {
    "from_line_index": "provenance: which lines.json rows built this Paragraph. Written for traceability, consulted by hand.",
    "to_line_index": "provenance: as above, the last row.",
    "num_lines": "provenance: how many source lines the Paragraph spans.",
    "paragraph_index": "provenance: the Paragraph's ordinal, written for traceability.",
    "latex_raw": "GAP: the maths BEFORE normalisation, 112,066 objects. Kept so a normalisation defect is recoverable, and nothing has ever recovered one.",
    "page_height": "geometry: page dimensions in MathPix pixels; the crop path uses region and image_id instead.",
    "page_width": "geometry: page width in MathPix pixels; the crop path uses region and image_id instead.",
    "languages_detected": "GAP: MathPix's script detection, 65,966 pages. Nothing consults it, including the routing that decides a vision lane.",
    "list_index": "provenance: the item's ordinal, written by ListProcessor.",
    "style": "GAP: a Section's detected heading style, 22,120 objects. 259 set levels from font_size and never looked at this.",
    "ref_source": "provenance: where a Reference came from.",
    "numeric": "GAP: whether a table cell holds a number, 10,695 cells. No projector formats on it.",
    "numbered": "redundant: equation_number is non-empty exactly when this is true.",
    "detected_by": "provenance: typed vs lexical list detection (248), written to make the 248 change auditable.",
    "text_source": "the text BEFORE translation. Read by `has_translation` through a tuple of prose keys, not by name — and a rebuild reverts it (275).",
    "starred": "provenance: whether the sectioning command was starred.",
    "first_section_id": "summary: written on the Document object; consumers walk the flow instead.",
    "total_pages": "summary: a count written on the Document object; consumers walk the flow and count for themselves.",
    "total_paragraphs": "summary: a Paragraph count on the Document object; consumers count the objects instead.",
    "total_sections": "summary: a Section count on the Document object; consumers count the objects instead.",
    "of_label": "provenance: the label a Proof proves; proof_of carries the id that is actually used.",
    "content_source": "the content BEFORE translation, for objects whose body is `content`. Same tuple-membership access as text_source.",
    "anchor_text": "GAP: a Link's visible text, 254 objects. `links` reports URLs; nothing reads the anchor.",
    "context": "GAP: the prose surrounding a Link, 254 objects. Recorded when the link was found and never read back.",
    "uri": "GAP: the Link's target. The `links` command reads the annotation layer directly rather than these objects.",
    "caption_source": "the caption BEFORE translation. Tuple-membership access.",
    "latex_fragment": "GAP: a partial maths value carried for reassembly, 51 objects. No reassembly pass exists.",
    "position": "GAP: positional hint recorded with a fragment.",
    "source_object": "provenance: the object a derived value came from.",
    "page_before_repair": "provenance: a Section's page before heading_cleanup moved it. Written with setdefault, so the scan sees no reader.",
    "latex_refined": "READ THROUGH A CONSTANT: refine.REFINED_FIELD. The `--prefer-refined` projection reads it (233); a name-literal scan cannot see that.",
    "indent_norm": "GAP: normalised ListItem indentation, 21 objects.",
    "list_type": "GAP: ordered vs unordered, 21 objects. No projector distinguishes them.",
}


def corpus_props() -> dict:
    """{object type: {prop: {n, docs}}} as last walked. Committed, not scanned
    at runtime: the corpus is gigabytes and a check must not read it."""
    return json.loads(CORPUS.read_text(encoding="utf-8"))["props"]


def all_corpus_props() -> dict:
    """{prop: total occurrences} across every object type."""
    out: dict = {}
    for _t, ps in corpus_props().items():
        for k, v in ps.items():
            out[k] = out.get(k, 0) + v["n"]
    return out


def code_map() -> dict:
    """{"readers"/"writers"/"mentions": {prop: [source files]}}."""
    d = json.loads(CODE.read_text(encoding="utf-8"))
    return {k: d.get(k, {}) for k in ("readers", "writers", "mentions")}


def table_props() -> set:
    """The prop names the generated table lists."""
    if not TABLE.is_file():
        return set()
    out = set()
    # Only the "Every prop" section. The file also carries a pairs table and an
    # object-types table, both of which use the same `| \`name\` |` row shape —
    # reading all of them made every object TYPE look like a prop the corpus
    # lacked, and check 2 reported 26 false violations.
    in_props = False
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_props = line.strip() == "## Every prop"
            continue
        if in_props and line.startswith("| `"):
            out.add(line.split("`")[1])
    return out


def table_violations() -> list:
    """CHECK 1 — every prop in the corpus must be in the table, with a reader
    or an explicit reason. This is the direction with teeth, as it was for
    types: a prop the corpus contains and the table omits is one nobody has
    looked at."""
    counts = all_corpus_props()
    listed = table_props()
    code = code_map()
    bad = []
    for p in sorted(counts, key=lambda x: -counts[x]):
        if p not in listed:
            bad.append("%s: in the corpus (%d), not in the table" % (p, counts[p]))
        elif not code["readers"].get(p) and p not in NO_READER_REASON:
            bad.append("%s: no reader and no reason" % p)
    return bad


def table_not_in_corpus() -> list:
    """CHECK 2 — every prop in the table must occur in the corpus.

    250 dropped this direction for TYPES, because a literal absent from today's
    corpus is not a defect — MathPix owns the vocabulary. It is kept here
    because props are OURS: a name in the table that no model carries is a
    typo, or a writer that has been removed."""
    counts = all_corpus_props()
    return sorted(p for p in table_props() if p not in counts)
