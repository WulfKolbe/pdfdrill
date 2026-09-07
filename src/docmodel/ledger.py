r"""634 — THE CLAIM LEDGER: every module records the anchors it consumed.

`pdfdrill model --ledger <pdf>` prints how many `mathpix_lines` anchors were
claimed zero times and how many more than once. THIS IS THE MEASUREMENT, NOT
THE FIX: the ledger adds no object, removes none and changes no prop.

WHY IT HAS TO BE RECORDED AND CANNOT BE DERIVED
-----------------------------------------------
`docops.conserve.anchor_claims` (646) measures the same surface from the other
end: it walks the finished Document and derives who covers which line. It can
say a line is claimed twice and it can name the two TYPES. It cannot name the
two MODULES, because the finished document does not carry that: on penev_A
1271 of 1448 objects have no `added_by` prop at all — the base build's modules
do not write one. "A Footnote and a Paragraph both claim this line" is a
symptom; "footnote_cleanup and paragraph both claim this line" is the address
of the code that has to change.

So the claim is recorded WHERE IT IS MADE — at `DocObject.add_realization`,
the ONE place every realization in the codebase is attached (54 call sites,
all of them through that method; the only other construction path is
`Document.from_dict`, which is a reload, not a claim). The recording site is
read off the calling frame, so no module had to be edited to take part and a
module added tomorrow is in the ledger the day it lands.

THE CLAIM RULE — block, inline, container
------------------------------------------
A claim is a `surface` Realization on `mathpix_lines`.

  BLOCK      no sub-anchor offset/length: the object consumed the whole line.
             THE USER'S TWO COUNTS ARE ABOUT BLOCK CLAIMS ALONE.
  INLINE     offset AND length present: the object lives INSIDE the line. A
             Formula inside a paragraph line is NESTING, not a second
             consumption; counting it would make every prose line with maths
             look mixed up. Recorded and reported separately.
  CONTAINER  the object's type is in `CONTAINER_TYPES`. `PageProcessor` gives
             every Page a surface realization spanning EVERY line of its page,
             by construction rather than by claim. 646 measured what counting
             them does: all 3178 penev_A anchors become doubly claimed and the
             measure says nothing. Recorded, reported, never counted — and the
             exclusion is printed in the output, not hidden in the code.

The rule is `docops.conserve`'s rule, deliberately: the two instruments must
be comparable anchor by anchor, and `tests/test_claim_ledger.py` pins that
they agree on the 0-claim and the >1-claim sets, not merely on the counts.

WHAT PERSISTS, AND WHY ONLY THAT
---------------------------------
`doc.meta["ledger"]` carries the ATTRIBUTION map (object id -> realization key
-> recording site) plus a small summary. The 0-claim and >1-claim listings are
NOT persisted: they are recomputed from the live document whenever the ledger
is read, so a ledger can never describe a document the model no longer holds.
The attribution is the one thing that cannot be recomputed — it is the memory
of who attached what, in a process that has since exited.

That is what makes the ledger read the same for a fresh build and for a full
drill. `model` records the base build; `bibliography`, `lists`, `annotate` and
`clean` each load that model, add objects in their own process, and save. The
attribution loaded from disk is merged with what THIS process recorded, so an
object built by `paragraph` three commands ago is still attributed to
`paragraph`, and a Citation added by `bibliography` a moment ago to
`bibliography`. Where an object carries `added_by`, that wins — it is the
pass's own name for itself, and it is what the later commands write.

An attribution that cannot be resolved reads `unattributed` rather than being
guessed at from the type. A ledger built on a model whose realizations were
attached before this code existed is entirely `unattributed`, and says so
(`recorded: false`), which is the honest reading of a model that predates the
measurement.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from typing import Any

#: The stream the ledger is about. One anchor = one OCR line.
LEDGER_STREAM = "mathpix_lines"

#: Types whose `mathpix_lines` surface range is a CONTAINER, not a claim.
#: Kept identical to `docops.conserve.CONTAINER_TYPES` on purpose — the two
#: instruments are cross-checked against each other and a private list here
#: would make a divergence look like a finding.
CONTAINER_TYPES = ("Page",)

#: 637 — A PASS WHOSE OWN NAME FOR ITSELF IS NOT ITS MODULE FILE.
#: The module is normally read off `added_by` (the pass's own name, on the
#: object) and only falls back to the recording SITE. That works while every
#: claim a pass makes lands on an object it CREATED. 637 broke the assumption:
#: `heading_cleanup.extract_footnote_paragraphs` now FILLS a Footnote that
#: `FootnoteProcessor` built, so the claim's object carries `added_by:
#: "footnote"` — or none at all — and the site is the only witness. Without
#: this map the same 35 anchors would be reported as `heading_cleanup+paragraph`
#: where out/634.txt reports `footnote_cleanup+paragraph`: a rename that reads
#: as a finding. The map is the pass's own `added_by` value, written down.
SITE_MODULE = {
    "heading_cleanup.extract_footnote_paragraphs": "footnote_cleanup",
    "heading_cleanup._fill_footnote": "footnote_cleanup",
}

#: Beyond this many recorded objects the recorder stops and says so, rather
#: than growing without bound in a process that builds a whole corpus. A
#: truncated ledger that announces itself is recoverable; one that quietly
#: eats a gigabyte is not.
MAX_RECORDED_OBJECTS = 200_000

#: Off by default. `DocObject.add_realization` tests this bool and nothing
#: else when it is False, so a process that only READS models pays one
#: attribute lookup per realization and records nothing.
RECORDING = False

_STORE: dict[str, dict[str, str]] = {}
_OVERFLOW = False

_MAX_EXAMPLES = 25


# ----------------------------------------------------------------- recording

def realization_key(r: Any) -> str:
    """The stable identity of one realization ON its object.

    Not the list index: several commands rebuild `obj.realizations` by
    filtering (`commands.py` does it in six places), so an index is not stable
    across a drill. Role + span + sub-anchor is, for every realization any
    module actually attaches.
    """
    p = r.props or {}
    off, ln = p.get("offset"), p.get("length")
    return "|".join((
        r.role or "",
        r.start.id if r.start is not None else "",
        r.end.id if r.end is not None else "",
        str(off) if isinstance(off, int) else "",
        str(ln) if isinstance(ln, int) else "",
    ))


def note(obj: Any, r: Any) -> None:
    """Record one claim. Called by `DocObject.add_realization`, and by nothing
    else — the single hook is the whole point (the alternative was 54 call
    sites, each free to forget)."""
    global _OVERFLOW
    if r.stream != LEDGER_STREAM or (r.role or "surface") != "surface":
        return
    if obj.id not in _STORE and len(_STORE) >= MAX_RECORDED_OBJECTS:
        _OVERFLOW = True
        return
    try:                                    # frame 0 note, 1 add_realization
        f = sys._getframe(2)                # frame 2 is the module that claimed
        mod = (f.f_globals.get("__name__") or "?").rsplit(".", 1)[-1]
        site = f"{mod}.{f.f_code.co_name}"
    except Exception:                       # no frame support -> say so
        site = "?.?"
    _STORE.setdefault(obj.id, {})[realization_key(r)] = site


def start_recording() -> None:
    global RECORDING
    RECORDING = True


def reset() -> None:
    """Forget everything and switch off. For tests and for a long-lived
    process that has finished with one document."""
    global RECORDING, _OVERFLOW
    RECORDING = False
    _STORE.clear()
    _OVERFLOW = False


def recorded() -> dict[str, dict[str, str]]:
    return _STORE


def overflowed() -> bool:
    return _OVERFLOW


@contextmanager
def recording():
    """Record for the duration of the block. The store is NOT cleared on exit:
    a build records in `docmodel.main.run` and is saved by `model_io.save_model`
    afterwards, so throwing the recording away at the end of the build would
    throw away the ledger."""
    global RECORDING
    prev = RECORDING
    start_recording()
    try:
        yield
    finally:
        RECORDING = prev


# -------------------------------------------------------------- the measurement

def _excerpt(s: Any, n: int = 60) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _kind(obj: Any, r: Any) -> str:
    p = r.props or {}
    if isinstance(p.get("offset"), int) and isinstance(p.get("length"), int):
        return "inline"
    if obj.type in CONTAINER_TYPES:
        return "container"
    return "block"


def materialize(doc: Any, stream: str = LEDGER_STREAM) -> dict | None:
    """The ledger for `doc`, recomputed from the live document.

    Returns None when the document has no such stream (a source model, a test
    fixture) — there is nothing to measure and an empty ledger asserting three
    zeros would be a vacuous pass.
    """
    st = doc.streams.get(stream)
    if st is None or not st.anchors:
        return None

    prev = (doc.meta.get("ledger") or {})
    stored: dict[str, dict[str, str]] = prev.get("attribution") or {}

    attribution: dict[str, dict[str, str]] = {}
    claims: dict[Any, list[tuple[Any, str]]] = defaultdict(list)
    by_module: Counter = Counter()
    by_module_inline: Counter = Counter()
    by_module_container: Counter = Counter()
    n_block = n_inline = n_container = 0
    any_recorded = False

    for obj in doc.objects.values():
        for r in obj.realizations:
            if r.stream != stream or (r.role or "surface") != "surface":
                continue
            if r.start is None:
                continue
            key = realization_key(r)
            site = (_STORE.get(obj.id, {}).get(key)
                    or (stored.get(obj.id) or {}).get(key))
            if site:
                any_recorded = True
                attribution.setdefault(obj.id, {})[key] = site
            added = obj.props.get("added_by")
            module = added or SITE_MODULE.get(site or "") \
                or (site.split(".", 1)[0] if site else None) \
                or "unattributed"

            kind = _kind(obj, r)
            end = r.end if r.end is not None else r.start
            try:
                span = st.slice_anchors(r.start, end)
            except KeyError:                 # an anchor from another document
                continue
            if kind == "inline":
                n_inline += 1
                by_module_inline[module] += 1
                continue
            if kind == "container":
                n_container += len(span)
                by_module_container[module] += len(span)
                continue
            n_block += len(span)
            by_module[module] += len(span)
            for a in span:
                claims[a].append((obj, module))

    zero: list[dict] = []
    multi: list[dict] = []
    pairs: Counter = Counter()
    zero_type: Counter = Counter()
    zero_page: Counter = Counter()
    n0 = n1 = nm = 0
    for i, a in enumerate(st.anchors):
        got = claims.get(a)
        pay = st.payload.get(a, {})
        page = pay.get("_page") or pay.get("page")
        if not got:
            n0 += 1
            zero_type[str(pay.get("type") or "<none>")] += 1
            zero_page[str(page)] += 1
            zero.append({"anchor": a.id, "index": i, "page": page,
                         "line_type": pay.get("type"),
                         "text": _excerpt(pay.get("text") or pay.get("_text"))})
        elif len(got) == 1:
            n1 += 1
        else:
            nm += 1
            mods = sorted(m for _, m in got)
            pairs["+".join(mods)] += 1
            multi.append({
                "anchor": a.id, "index": i, "page": page,
                "line_type": pay.get("type"),
                "text": _excerpt(pay.get("text") or pay.get("_text")),
                "modules": mods,
                "types": sorted(o.type for o, _ in got),
                "claimants": [{"id": o.id, "type": o.type, "module": m}
                              for o, m in got],
            })

    return {
        "stream": stream,
        "total": len(st.anchors),
        "rule": ("a claim is a `surface` realization on the stream; BLOCK when "
                 "it carries no sub-anchor offset/length, INLINE when it does "
                 "(nesting, not a second consumption), CONTAINER when the type "
                 "spans its page by construction. The counts are BLOCK claims."),
        "counts": {
            "claimed_0": n0, "claimed_1": n1, "claimed_multi": nm,
            "block_claims": n_block, "inline_claims": n_inline,
            "container_claims": n_container,
        },
        "containers_excluded": list(CONTAINER_TYPES),
        "by_module": dict(by_module.most_common()),
        "by_module_inline": dict(by_module_inline.most_common()),
        "by_module_container": dict(by_module_container.most_common()),
        "module_pairs": dict(pairs.most_common()),
        "zero": zero,
        "zero_by_line_type": dict(zero_type.most_common()),
        "zero_by_page": dict(zero_page.most_common()),
        "multi": multi,
        "attribution": attribution,
        "recorded": any_recorded,
        "attributed_realizations": sum(len(v) for v in attribution.values()),
        "overflow": _OVERFLOW or bool(prev.get("overflow")),
    }


#: What reaches the model file. The listings are left out on purpose: they are
#: recomputed from the document on every read, so a stored ledger can never
#: describe a document the model no longer holds.
_PERSIST = ("stream", "total", "rule", "counts", "containers_excluded",
            "by_module", "by_module_inline", "by_module_container",
            "module_pairs", "zero_by_line_type", "zero_by_page",
            "attribution", "recorded", "attributed_realizations", "overflow")


def persistable(led: dict | None) -> dict | None:
    if led is None:
        return None
    return {k: led[k] for k in _PERSIST if k in led}


def for_save(doc: Any) -> dict | None:
    """The ledger `model_io.save_model` writes into the serialised meta.

    Best-effort by contract: a measurement must never be able to fail a save.
    """
    try:
        return persistable(materialize(doc))
    except Exception:
        return None


# ------------------------------------------------------------------- the report

def format_ledger(led: dict | None, limit: int = _MAX_EXAMPLES,
                  title: str = "") -> str:
    if led is None:
        return ("No `mathpix_lines` stream in this model, so there are no "
                "anchors to claim (a LaTeX-source model has none).")
    c = led["counts"]
    tot = led["total"]
    total = c["claimed_0"] + c["claimed_1"] + c["claimed_multi"]
    L: list[str] = []
    head = "CLAIM LEDGER"
    if title:
        head += f" — {title}"
    L.append(f"{head}  (stream {led['stream']})")
    L.append("")
    L.append("A CLAIM is a `surface` realization on the stream. BLOCK when it")
    L.append("carries no sub-anchor offset/length (the object consumed the whole")
    L.append("line); INLINE when it does (a Formula inside a line is nesting, not")
    L.append("a second consumption); CONTAINER for a type whose range spans its")
    L.append("page by construction. THE COUNTS BELOW ARE BLOCK CLAIMS.")
    L.append("")
    L.append(f"  anchors (stream length)          {tot:8d}")
    L.append(f"  claimed 0 times                  {c['claimed_0']:8d}"
             f"   ({_pct(c['claimed_0'], tot)})")
    L.append(f"  claimed 1 time                   {c['claimed_1']:8d}")
    L.append(f"  claimed more than once           {c['claimed_multi']:8d}"
             f"   ({_pct(c['claimed_multi'], tot)})")
    L.append("  " + "-" * 46)
    ok = "OK" if total == tot else f"MISMATCH ({total} != {tot})"
    L.append(f"  0 + 1 + >1 = {total:<8d}  vs stream length {tot:<8d}  {ok}")
    L.append("")
    L.append(f"  block claims {c['block_claims']:6d}   "
             f"inline claims {c['inline_claims']:6d}   "
             f"container claims {c['container_claims']:6d}")
    L.append(f"  container types recorded but not claiming: "
             f"{', '.join(led['containers_excluded'])}")
    if not led.get("recorded"):
        L.append("  ATTRIBUTION: none recorded — this model was built before the")
        L.append("  ledger existed, or by a path that does not record. Every")
        L.append("  module below reads `unattributed`; rebuild to attribute.")
    if led.get("overflow"):
        L.append("  ATTRIBUTION TRUNCATED: the recorder hit its object cap.")

    L.append("")
    L.append("BLOCK CLAIMS BY MODULE (anchors, so a module claiming a 12-line")
    L.append("paragraph counts 12)")
    for m, n in list(led["by_module"].items()):
        L.append(f"  {m:<28s} {n:6d}")
    if led["by_module_inline"]:
        L.append("")
        L.append("INLINE CLAIMS BY MODULE (nesting; not counted above)")
        for m, n in list(led["by_module_inline"].items()):
            L.append(f"  {m:<28s} {n:6d}")
    if led["by_module_container"]:
        L.append("")
        L.append("CONTAINER CLAIMS BY MODULE (spans, not claims)")
        for m, n in list(led["by_module_container"].items()):
            L.append(f"  {m:<28s} {n:6d}")

    L.append("")
    L.append("ANCHORS CLAIMED MORE THAN ONCE — BY MODULE PAIR")
    if not led["module_pairs"]:
        L.append("  (none)")
    for p, n in list(led["module_pairs"].items()):
        L.append(f"  {p:<40s} {n:6d}")
    for e in led.get("multi", [])[:limit]:
        L.append(f"    p{e['page']} #{e['index']} [{e['line_type']}] "
                 f"{'+'.join(e['modules'])}: {e['text']}")

    L.append("")
    L.append("CLAIMED BY NOBODY — BY MATHPIX LINE TYPE")
    if not led["zero_by_line_type"]:
        L.append("  (none)")
    for t, n in list(led["zero_by_line_type"].items()):
        L.append(f"  {t:<28s} {n:6d}")
    if led["zero_by_page"]:
        L.append("")
        L.append("CLAIMED BY NOBODY — BY PAGE")
        L.append("  " + "  ".join(f"p{p}:{n}" for p, n
                                  in sorted(led["zero_by_page"].items(),
                                            key=lambda kv: _pageno(kv[0]))))
    for e in led.get("zero", [])[:limit]:
        L.append(f"    p{e['page']} #{e['index']} [{e['line_type']}] {e['text']}")
    return "\n".join(L)


def _pct(n: int, tot: int) -> str:
    return f"{(100.0 * n / tot):.1f}%" if tot else "0.0%"


def _pageno(p: str) -> tuple:
    try:
        return (0, int(p))
    except (TypeError, ValueError):
        return (1, 0)
