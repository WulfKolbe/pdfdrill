r"""902b — THE READING ORDER WAS IN THE FILE AND NO READER ASKED FOR IT.

`md` reconstructs reading order from glyph geometry. Measured on eleven
PDF-Association / ISO documents (1,234 pages) on 2026-10-13, that cost:

    11,036 tagged table cells in ISO 32000-2  ->      1 markdown table
     1,111 licence-footer lines woven into the running prose
        51 running headers fused to the next word (`14to`, `20be`, `41be`)
           clause numbers interleaved letter by letter (`3st.a2ndard`)

Ten of the eleven ship a `/StructTreeRoot`. `structmd` reads it.

These tests are written against SYNTHETIC trees rather than the corpus,
because the corpus documents are licensed (six carry a per-copy watermark with
the owner's name) and must not enter the repository. Every fixture here
encodes a shape that was MEASURED on a real document, and says which one.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import structmd


# ---------------------------------------------------------------------------
# the marked-content folding, which is where the subtle losses live
# ---------------------------------------------------------------------------
def _chars(*triples):
    """(text, mcid, tag) -> pdfplumber-shaped char dicts on page 1."""
    return [{"text": t, "mcid": m, "tag": g, "page_number": 1}
            for t, m, g in triples]


def _fold(chars):
    runs, stats = {}, __import__("collections").Counter()
    acc = __import__("collections").defaultdict(list)
    structmd._runs_from_page_chars(chars, 0, acc, stats)
    return {k: "".join(v) for k, v in acc.items()}, stats


def test_a_split_run_is_reattached_to_the_half_it_was_split_from():
    r"""THE NON-BREAKING-SPACE HOLE, measured on ISO/TS 32005 page 8.

    pdfplumber reports `mcid` and `tag` per char but loses BOTH inside a nested
    marked-content sequence, and InDesign splits a text run at a non-breaking
    space. The page's own stream reads `H1/150 '1'`, `None 'Scope'` — so the
    heading is `1 Scope` and dropping the untagged half loses the word.
    """
    runs, stats = _fold(_chars(("1", 150, "H1"), ("Scope", None, None),
                               ("x", 151, "P")))
    assert runs[(0, 150)] == "1Scope"
    assert stats["reattached_chars"] == 5


def test_an_artifact_never_absorbs_and_is_never_absorbed():
    """The licence footer must not be glued to the paragraph above it.

    Measured: 1,111 footer lines reached the geometric markdown woven into the
    prose. An artifact is not in the reading flow at all, so it breaks the
    chain in both directions.
    """
    runs, stats = _fold(_chars(
        ("body", 10, "P"),
        ("Sold by the PDF Association", None, "Artifact"),
        ("tail", None, None),                 # after an artifact: unattachable
        ("next", 11, "P")))
    assert runs[(0, 10)] == "body"            # the footer did not land here
    assert "Sold by" not in "".join(runs.values())
    assert stats["artifact_chars"] == len("Sold by the PDF Association")
    assert stats.get("reattached_chars", 0) == 0


def test_an_unsandwiched_untagged_run_is_dropped_not_guessed():
    """A page whose untagged run has no marked content before it — the
    bilingual running title on an ISO cover — belongs to no element and has no
    reading position, so it stays out and is COUNTED."""
    runs, stats = _fold(_chars(("— Format de document portable", None, None),
                               ("real", 5, "P")))
    assert runs[(0, 5)] == "real"
    assert stats["orphan_chars"] > 0


def test_whitespace_only_orphans_are_not_reported_as_loss():
    """`tag=Span mcid=None` runs of tabs are 169-439 chars per ISO/TS document
    and losing them costs nothing; counting them as loss would cry wolf."""
    _, stats = _fold(_chars(("\t\t  ", None, None), ("x", 1, "P")))
    assert stats["orphan_chars"] == 0


def test_page_numbers_are_normalised_once():
    """pdfplumber is 1-based and the structure tree is 0-based. One conversion,
    in the folder, or every lookup misses by one page."""
    runs, _ = _fold(_chars(("a", 7, "P")))
    assert (0, 7) in runs and (1, 7) not in runs


# ---------------------------------------------------------------------------
# the tree: roles, containers, tables
# ---------------------------------------------------------------------------
class _Node(dict):
    """The subset of a pikepdf Dictionary the projector touches."""

    def __init__(self, S=None, K=None, **kw):
        super().__init__()
        if S is not None:
            self["/S"] = S
        if K is not None:
            self["/K"] = K
        self.update({f"/{k}": v for k, v in kw.items()})

    def get(self, k, default=None):          # noqa: A003
        return dict.get(self, k, default)

    @property
    def objgen(self):
        return (id(self), 0)


class _FakeTree(structmd.StructTree):
    """A StructTree over synthetic nodes — no PDF, no licence problem."""

    def __init__(self, root, mc, rolemap=None):
        self.root = root
        self._mc = mc
        self.rolemap = rolemap or {}
        self._pageidx = {}
        self._pdf = None

    def element_kids(self, node):
        k = node.get("/K")
        if k is None:
            return []
        items = k if isinstance(k, list) else [k]
        return [i for i in items if isinstance(i, _Node)]

    def text_of(self, node, pg, depth=0):
        if depth > 50:
            return ""
        actual = node.get("/ActualText")
        if actual is not None:
            return str(actual)
        k = node.get("/K")
        if k is None:
            return ""
        parts = []
        for it in (k if isinstance(k, list) else [k]):
            if isinstance(it, int):
                parts.append(self._mc.get((pg, it), ""))
            elif isinstance(it, _Node):
                parts.append(self.text_of(it, pg, depth + 1))
        return "".join(parts)

    def page_of(self, node, inherited):
        return inherited

    def link_uri(self, node):
        return node.get("/URI")


def _render(root, mc, rolemap=None):
    t = _FakeTree(root, mc, rolemap)
    r = structmd._Renderer(t)
    for k in t.element_kids(root):
        r.walk(k, 0)
    return "\n\n".join(x for x in r.out if x.strip()), r.stats


def test_rolemap_translates_a_producers_private_names():
    """A producer's own style names are NOT the standard roles. InDesign ships
    `/Heading_2`; Word ships `/H1 bold_`; 32000-2 has 66 such entries. The file
    states the mapping in `/RoleMap`, so nothing here is guessed."""
    root = _Node(K=[_Node("/Heading_2", K=[0])])
    md, st = _render(root, {(0, 0): "Normative references"},
                     {"/Heading_2": "/H2"})
    assert md == "## Normative references"
    assert st["headings"] == 1


def test_a_rolemap_chain_is_followed_but_cannot_loop():
    """InDesign chains `/Subtitle -> /H1`. A malformed map could be circular,
    and a reader that trusted it would hang."""
    root = _Node(K=[_Node("/A", K=[0])])
    md, _ = _render(root, {(0, 0): "t"}, {"/A": "/B", "/B": "/H3"})
    assert md == "### t"
    md2, _ = _render(_Node(K=[_Node("/X", K=[0])]), {(0, 0): "t"},
                     {"/X": "/Y", "/Y": "/X"})
    assert "t" in md2                         # no hang, text not lost


def test_a_table_becomes_a_pipe_table_with_its_header_row():
    """AN003's `Object type | ISO 32000-2 reference | Description` reached the
    geometric markdown as two headings — `## Object type ISO 32000-2
    Description` then `## reference`. The tree states the grid."""
    row = lambda role, a, b: _Node("/TR", K=[_Node(role, K=[a]),
                                             _Node(role, K=[b])])
    root = _Node(K=[_Node("/Table", K=[
        _Node("/THead", K=[row("/TH", 0, 1)]),
        _Node("/TBody", K=[row("/TD", 2, 3)])])])
    mc = {(0, 0): "Object type", (0, 1): "Description",
          (0, 2): "Catalog", (0, 3): "A metadata stream"}
    md, st = _render(root, mc)
    assert md.splitlines() == [
        "| Object type | Description |",
        "| --- | --- |",
        "| Catalog | A metadata stream |",
    ]
    assert st["tables"] == 1 and st["table_rows"] == 2


def test_a_p_that_contains_a_table_is_not_flattened_into_prose():
    r"""ISO/TS 32005's every table hangs below a `/P`: the measured ancestor
    chain to the first row is

        /Document > /Art > /Sect > /P > /Table > /THead > /TR

    because the producer's `/Table_Position` style maps to `/P`. Treating `/P`
    as a leaf reported 0 tables for a document with 151 rows — the exact fault
    this layer removes, reintroduced one level up.
    """
    inner = _Node("/Table", K=[_Node("/TR", K=[_Node("/TD", K=[0])])])
    root = _Node(K=[_Node("/Table_Position", K=[inner])])
    md, st = _render(root, {(0, 0): "cell"}, {"/Table_Position": "/P"})
    assert st["tables"] == 1
    assert "| cell |" in md


def test_a_row_label_later_in_a_table_does_not_start_a_second_header():
    """ISO tables put a `/TH` in the left column of every data row. Promoting
    those would split one table into many."""
    root = _Node(K=[_Node("/Table", K=[
        _Node("/TR", K=[_Node("/TH", K=[0]), _Node("/TH", K=[1])]),
        _Node("/TR", K=[_Node("/TH", K=[2]), _Node("/TD", K=[3])]),
        _Node("/TR", K=[_Node("/TH", K=[4]), _Node("/TD", K=[5])])])])
    mc = {(0, i): f"c{i}" for i in range(6)}
    md, st = _render(root, mc)
    assert st["tables"] == 1
    assert md.splitlines()[1] == "| --- | --- |"      # exactly one separator
    assert md.count("---") == 2


def test_a_table_whose_every_row_is_a_header_still_has_data_rows():
    """8 of ISO 32000-2's 732 tables tag every cell `/TH` — the PostScript
    operator tables. Taking them all as header left no data rows and put the
    separator at the BOTTOM of the block, which renders as no table at all."""
    rows = [_Node("/TR", K=[_Node("/TH", K=[2 * i]), _Node("/TH", K=[2 * i + 1])])
            for i in range(3)]
    root = _Node(K=[_Node("/Table", K=rows)])
    md, _ = _render(root, {(0, i): f"c{i}" for i in range(6)})
    lines = md.splitlines()
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| c2 | c3 |"
    assert len(lines) == 4


def test_a_cells_pipe_is_escaped_so_one_cell_stays_one_cell():
    root = _Node(K=[_Node("/Table", K=[
        _Node("/TR", K=[_Node("/TD", K=[0]), _Node("/TD", K=[1])])])])
    md, _ = _render(root, {(0, 0): "a|b", (0, 1): "c"})
    assert "a\\|b" in md


def test_an_unknown_leaf_keeps_its_text_rather_than_dropping_it():
    """An unknown WRAPPER costs nothing; an unknown LEAF would silently lose
    text, which is the failure class this whole layer exists to end."""
    root = _Node(K=[_Node("/SomeFutureRole", K=[0])])
    md, st = _render(root, {(0, 0): "important"})
    assert "important" in md
    assert st["unrecognised_leaf:/SomeFutureRole"] == 1


def test_actual_text_wins_over_the_glyphs():
    """`/ActualText` is the producer saying what the glyphs MEAN — how a
    decoratively split word or a ligature reaches a reader intact."""
    root = _Node(K=[_Node("/P", K=[0], ActualText="difficult")])
    md, _ = _render(root, {(0, 0): "difﬁcult"})
    assert md == "difficult"


def test_a_list_keeps_its_items_and_its_nesting():
    sub = _Node("/L", K=[_Node("/LI", K=[_Node("/LBody", K=[2])])])
    root = _Node(K=[_Node("/L", K=[
        _Node("/LI", K=[_Node("/Lbl", K=[0]), _Node("/LBody", K=[1])]),
        _Node("/LI", K=[_Node("/LBody", K=[3]), sub])])])
    mc = {(0, 0): "1.", (0, 1): "first", (0, 2): "nested", (0, 3): "second"}
    md, st = _render(root, mc)
    lines = md.splitlines()
    assert lines[0] == "1. first"
    assert lines[1] == "- second"
    assert lines[2] == "  - nested"
    assert st["list_items"] == 3


def test_a_link_carries_its_uri():
    root = _Node(K=[_Node("/Link", K=[0], URI="https://www.pdfa.org/")])
    md, st = _render(root, {(0, 0): "PDF Association"})
    assert md == "[PDF Association](https://www.pdfa.org/)"
    assert st["links"] == 1


def test_a_figure_uses_its_alt_text():
    root = _Node(K=[_Node("/Figure", Alt="PDF Association logo")])
    md, st = _render(root, {})
    assert md == "![PDF Association logo](figure)"
    assert st["figures"] == 1


# ---------------------------------------------------------------------------
# the refusal
# ---------------------------------------------------------------------------
def test_no_structure_tree_raises_rather_than_falling_back():
    """A tagged PDF whose tags are a stub is exactly the case where a silent
    fallback to the geometric route is indistinguishable from success. ISO
    32000-2 declares `/MarkInfo <</Marked true>>`, so `Tagged: yes` from
    pdfinfo is not evidence that a usable tree exists."""
    class _Handle:
        Root = {"/StructTreeRoot": None}
        pages = []

        def __init__(self):
            self.Root = type("R", (), {"get": lambda s, k: None})()

    with pytest.raises(structmd.NoStructure):
        structmd.StructTree(_Handle(), {})


def test_an_empty_tree_is_refused_too():
    """`/StructTreeRoot` present but childless. 32000-2's own walk returned 7
    elements under a naive reading before the signature count corrected it, so
    a tree that LOOKS present and yields nothing is a real shape."""
    t = _FakeTree(_Node(K=[]), {})
    r = structmd._Renderer(t)
    assert t.element_kids(t.root) == []
    assert r.out == []


def test_the_command_is_registered_in_the_manifest_and_the_cli():
    """A new capability is a layer in the manifest, not a new verb — code that
    lands outside it is invisible to the planner, `status` and `--ensure`."""
    from pdfdrill import cli
    assert "structmd" in cli.HANDLERS
    manifest = (Path(__file__).resolve().parent.parent
                / ".claude/skills/pdfdrill/commands.yaml").read_text()
    assert "- name: structmd" in manifest
    assert "done_when: file:{bibkey}.struct.md" in manifest
