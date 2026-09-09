#!/usr/bin/env python3
"""650 — the census: tiddler counts by kind, Footnote/Reference objects,
`cites` edges, the ledger's two counts, and the title SET by kind.

    python3 script.py <document folder>

Runs from either the repo (`out/650/script.py`) or the document's own
`out/650/`. Everything it prints is read off the model + tiddlers.json on
disk; nothing is rebuilt here. The PDF is never touched — the census reads
only `model.docmodel.json` and `<folder-name>.tiddlers.json`, both named
from the FOLDER, never globbed (six PDFs sit beside a published document,
but this script never opens a PDF at all).
"""
import collections
import json
import sys
from pathlib import Path


def _repo() -> Path:
    for cand in Path(__file__).resolve().parents:
        if (cand / "src" / "docmodel" / "ledger.py").is_file():
            return cand
    return Path("/home/wkolbe/MX/PDFDRILL")


REPO = _repo()
sys.path.insert(0, str(REPO / "src"))

from docmodel import ledger as L                                  # noqa: E402
from docops.projectors.tiddlywiki import parse_title               # noqa: E402
from pdfdrill.model_io import load_model                           # noqa: E402


def census(docdir: Path) -> dict:
    docdir = docdir.expanduser().resolve()
    bibkey = docdir.name
    model_path = docdir / "model.docmodel.json"
    doc = load_model(model_path)

    tiddlers_path = docdir / f"{bibkey}.tiddlers.json"
    tiddlers = []
    if tiddlers_path.is_file():
        tiddlers = json.loads(tiddlers_path.read_text())

    by_kind = collections.Counter()
    titles_by_kind: dict[str, set] = collections.defaultdict(set)
    unparsed = []
    for t in tiddlers:
        title = t.get("title")
        p = parse_title(title)
        if p is None:
            unparsed.append(title)
            continue
        by_kind[p.kind] += 1
        titles_by_kind[p.kind].add(title)

    fn_objs = [o for o in doc.objects.values() if o.type == "Footnote"]
    ref_objs = [o for o in doc.objects.values() if o.type == "Reference"]
    cites = sum(1 for a in doc.alignments if a.kind == "cites")

    view = L.materialize(doc)
    ledger = None
    if view is not None:
        ledger = {
            "claimed_0": view["counts"]["claimed_0"],
            "claimed_multi": view["counts"]["claimed_multi"],
        }

    res = {
        "bibkey": bibkey,
        "objects_total": len(doc.objects),
        "tiddlers_total": len(tiddlers),
        "tiddlers_by_kind": dict(sorted(by_kind.items())),
        "tiddlers_unparsed": len(unparsed),
        "footnote_objects": len(fn_objs),
        "footnote_titles": sorted(titles_by_kind.get("Footnote", ())),
        "reference_objects": len(ref_objs),
        "reference_titles": sorted(titles_by_kind.get("Reference", ())),
        "cites_edges": cites,
        "ledger": ledger,
        # every title, by kind, so two runs can be diffed SET vs SET, not
        # count vs count (a count can hold while the population underneath
        # changes id).
        "titles_by_kind": {k: sorted(v) for k, v in titles_by_kind.items()},
    }
    return res


def diff_titles(a: dict, b: dict) -> dict:
    """{kind: {"gained": [...], "lost": [...]}} for every kind where the SET
    of titles moved between two census() results, even if the count did not."""
    out = {}
    ka = a.get("titles_by_kind", {})
    kb = b.get("titles_by_kind", {})
    for kind in sorted(set(ka) | set(kb)):
        sa, sb = set(ka.get(kind, ())), set(kb.get(kind, ()))
        if sa != sb:
            out[kind] = {
                "gained": sorted(sb - sa),
                "lost": sorted(sa - sb),
            }
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    docdir = Path(sys.argv[1])
    out = census(docdir)
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
