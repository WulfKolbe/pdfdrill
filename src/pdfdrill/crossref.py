"""P10 — crossref: ONE index over (bibkey, kind, id, signature, evidence).

The signature is supplied PER KIND and is opaque to the index — for formulas
it is the Symbol Layout Tree serialized to .lg (mathgold.slt), which
canonicalizes LaTeX spelling variants (x_{5} == x_5). The index only stores
and ranks; it never interprets a signature.

Ranking: exact signature match scores 1.0; otherwise the Jaccard overlap of
the signature's LINES (order-free) — meaningful for any line- or
token-structured signature, still opaque.

First use: the formula mapping between two books — each book of the Heim
corpus against BH3FR, the formula REGISTER (every formula of the other books
should be findable in it; the register entry number becomes the canonical
cross-book id).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_STORE = Path.home() / "pdfdrill-library" / "crossref.json"


# --------------------------------------------------------------------------- #
#  Store
# --------------------------------------------------------------------------- #
def load_store(path: Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("entries", []) if isinstance(d, dict) else d
    except Exception:
        return []


def save_store(path: Path, entries: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"crossref": 1, "entries": entries},
                            ensure_ascii=False), encoding="utf-8")


def add_entries(path: Path, entries: list[dict], bibkey: str,
                kind: str | None = None) -> int:
    """Replace `bibkey`'s (kind-filtered) entries with the given ones —
    re-indexing a book is idempotent, never additive-duplicating."""
    store = load_store(path)
    store = [e for e in store
             if not (e.get("bibkey") == bibkey
                     and (kind is None or e.get("kind") == kind))]
    store.extend(entries)
    save_store(path, store)
    return len(store)


# --------------------------------------------------------------------------- #
#  Signatures (per kind; the index never looks inside)
# --------------------------------------------------------------------------- #
def formula_signature(latex: str) -> str | None:
    """SLT .lg signature for a formula/equation latex, or None (unparsed)."""
    try:
        from mathgold.slt import parse_latex_slt, slt_to_lg
        lg = slt_to_lg(parse_latex_slt(latex))
        # drop the comment header — it is presentation, not identity
        return "\n".join(l for l in lg.splitlines()
                         if l and not l.startswith("#"))
    except Exception:
        return None


def _sig_lines(sig: str) -> frozenset:
    return frozenset(l.strip() for l in sig.splitlines() if l.strip())


def rank(entries: list[dict], signature: str, kind: str | None = None,
         k: int = 10, exclude_bibkey: str | None = None) -> list[tuple]:
    """Ranked (score, entry) for a signature across all bibkeys."""
    want = _sig_lines(signature)
    out = []
    for e in entries:
        if kind and e.get("kind") != kind:
            continue
        if exclude_bibkey and e.get("bibkey") == exclude_bibkey:
            continue
        sig = e.get("signature") or ""
        if sig == signature:
            out.append((1.0, e))
            continue
        have = e.get("_lines")
        if have is None:
            have = e["_lines"] = _sig_lines(sig)
        union = len(want | have)
        score = (len(want & have) / union) if union else 0.0
        if score > 0.0:
            out.append((round(score, 4), e))
    out.sort(key=lambda t: (-t[0], t[1].get("bibkey", ""),
                            t[1].get("id", "")))
    return out[:k]


# --------------------------------------------------------------------------- #
#  Harvesting a drilled book (tiddlers carry latex + page + eq number)
# --------------------------------------------------------------------------- #
def entries_from_tiddlers(tiddlers_path: Path, bibkey: str) -> tuple[list, int]:
    """(entries, unparsed_count) — one formula entry per EQ/FO tiddler whose
    latex yields an SLT signature."""
    tiddlers = json.loads(Path(tiddlers_path).read_text(encoding="utf-8"))
    entries, unparsed = [], 0
    pat = re.compile(re.escape(bibkey) + r"_(EQ|FOX?)")
    for t in tiddlers:
        title = t.get("title", "")
        if not pat.match(title):
            continue
        latex = t.get("latex") or ""
        if not latex:
            continue
        sig = formula_signature(latex)
        if sig is None:
            unparsed += 1
            continue
        entries.append({
            "bibkey": bibkey, "kind": "formula", "id": title,
            "signature": sig,
            "evidence": {"latex": latex, "page": t.get("page", ""),
                         "equation_number": t.get("equation_number", "")}})
    return entries, unparsed


# --------------------------------------------------------------------------- #
#  The first use: formula mapping between two books
# --------------------------------------------------------------------------- #
def map_books(entries: list[dict], src_bibkey: str, dst_bibkey: str,
              threshold: float = 0.8) -> dict:
    """For every src formula, the best dst match. Buckets: exact (1.0),
    near (>= threshold), none. Returns counts + the pair list."""
    dst = [e for e in entries
           if e.get("bibkey") == dst_bibkey and e.get("kind") == "formula"]
    src = [e for e in entries
           if e.get("bibkey") == src_bibkey and e.get("kind") == "formula"]
    exact, near, none = [], [], 0
    for e in src:
        top = rank(dst, e["signature"], kind="formula", k=1)
        if not top:
            none += 1
            continue
        score, m = top[0]
        pair = (e, m, score)
        if score >= 0.9999:
            exact.append(pair)
        elif score >= threshold:
            near.append(pair)
        else:
            none += 1
    return {"src": src_bibkey, "dst": dst_bibkey, "total": len(src),
            "exact": exact, "near": near, "unmatched": none}


# --------------------------------------------------------------------------- #
#  P11/P12 — SLT edit distance (beyond equality)
# --------------------------------------------------------------------------- #
def slt_tokens(sig: str) -> tuple[list, list]:
    """(node labels in id order, edge relations in (src,dst) order) from an
    .lg signature. The two sequences are the SLT linearized: labels carry the
    SYMBOLS, relations the LAYOUT."""
    def _nid(t: str) -> int:
        digits = "".join(c for c in t if c.isdigit())
        return int(digits) if digits else -1     # 'none' (Unresolved) -> -1

    nodes, edges = [], []
    for line in sig.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4 and parts[0] == "N":
            nodes.append((_nid(parts[1]), ",".join(parts[2:-1])))
        elif len(parts) >= 5 and parts[0] == "E":
            edges.append((_nid(parts[1]), _nid(parts[2]), parts[3]))
    nodes.sort()
    edges.sort()
    return [l for _i, l in nodes], [r for _s, _d, r in edges]


def _lev(a: list, b: list, bound: int | None = None) -> int:
    """Levenshtein over token lists; early-exits past `bound`."""
    if a == b:
        return 0
    if bound is not None and abs(len(a) - len(b)) >= bound:
        return bound
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, y in enumerate(b, 1):
            c = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
            cur.append(c)
            row_min = min(row_min, c)
        if bound is not None and row_min >= bound:
            return bound
        prev = cur
    return prev[-1]


def slt_edit_distance(sig_a: str, sig_b: str,
                      bound: int | None = None) -> int:
    """Symbol edits + layout edits: Levenshtein over node labels plus
    Levenshtein over edge relations. Distance 1-2 reads as divergent OCR;
    large distance as a genuinely different formula."""
    la, ra = slt_tokens(sig_a)
    lb, rb = slt_tokens(sig_b)
    d = _lev(la, lb, bound)
    if bound is not None and d >= bound:
        return d
    return d + _lev(ra, rb, None if bound is None else bound - d)


def nearest_by_distance(candidates: list[dict], signature: str
                        ) -> tuple[int, dict] | None:
    """The minimum-SLT-edit-distance candidate (bound-pruned scan)."""
    best_d, best = None, None
    for e in candidates:
        d = slt_edit_distance(signature, e.get("signature") or "",
                              bound=best_d)
        if best_d is None or d < best_d:
            best_d, best = d, e
            if best_d == 0:
                break
    return (best_d, best) if best is not None else None
