"""
LAYER 1 — ordering.  (Gap 1: relations have no sibling order.)

Composable, zero schema change: the order key rides inside the relation's
existing `grounding` dict under "ord". A Relation written by an older pass with
no "ord" simply sorts first (empty string) and can be back-filled later. When
this layer has proven out, "promote" it by moving "ord" to a real Relation field
— the query helpers below don't change, only `_ord()`/`_set_ord()` do.

    append_child(g, parent, pred, child)   # add at end of the ordered group
    insert_child(g, parent, pred, child, after=None, before=None)
    ordered_children(g, parent, pred)      # subjects' targets, in document order
    first_occurrence(g, target, pred)      # the earliest incoming edge (min ord)
    occurrences_in_order(g, target, pred)
    move(relation, after=None, before=None)  # reorder one edge, touch nothing else
"""
from __future__ import annotations

from typing import List, Optional
from ..fracidx import key_between


def _ord(r) -> str:
    return (r.grounding or {}).get("ord", "")


def _set_ord(r, value: str) -> None:
    if r.grounding is None:
        r.grounding = {}
    r.grounding["ord"] = value


def _last_ord(graph, subject_id: str, predicate) -> Optional[str]:
    keys = [_ord(r) for r in graph.relations_of(subject_id, predicate) if _ord(r)]
    return max(keys) if keys else None


def append_child(graph, parent_id: str, predicate, child_id: str, **kw):
    r = graph.relate(parent_id, predicate, child_id,
                     grounding={"ord": key_between(_last_ord(graph, parent_id, predicate), None)},
                     **kw)
    return r


def insert_child(graph, parent_id: str, predicate, child_id: str,
                 after: Optional[str] = None, before: Optional[str] = None, **kw):
    r = graph.relate(parent_id, predicate, child_id,
                     grounding={"ord": key_between(after, before)}, **kw)
    return r


def ordered_children(graph, parent_id: str, predicate) -> List:
    return sorted(graph.relations_of(parent_id, predicate), key=_ord)


def occurrences_in_order(graph, target_id: str, predicate) -> List:
    return sorted(graph.relations_to(target_id, predicate), key=_ord)


def first_occurrence(graph, target_id: str, predicate):
    occ = occurrences_in_order(graph, target_id, predicate)
    return occ[0] if occ else None


def move(relation, after: Optional[str] = None, before: Optional[str] = None) -> None:
    _set_ord(relation, key_between(after, before))
