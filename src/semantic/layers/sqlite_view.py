"""
LAYER 4 — SQLite read view.  (Indexed queries + the bun:sqlite bridge.)

Fully decoupled: consumes ONLY the graph.json sidecar dict, not the Python
classes. Builds the converged two-table shape, and — because the brief needs
dual positioning — lifts the occurrence layer's PDF page and logical position
out of grounding into indexed columns. A `bun:sqlite` reader on the TiddlyWiki
side opens the identical file; the TS projector reads the graph with no Python.

    conn = load_view(graph_dict)                 # in-memory (or path=...)
    children_in_order(conn, parent, predicate)
    occurrences_of(conn, item_id)                # role, pdf_page, bbox, logical, ord
    items_on_page(conn, page)                    # item 1 axis: everything on a PDF page
    occurrences_in_node(conn, node_id)           # item 2 axis: everything in a section
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

_SCHEMA = """
CREATE TABLE node (id TEXT PRIMARY KEY, type TEXT, subtype TEXT, props TEXT);
CREATE TABLE edge (
    subject TEXT, predicate TEXT, object TEXT,
    ord TEXT, layer TEXT, role TEXT,
    pdf_page INTEGER, bbox TEXT, logical_path TEXT,
    confidence REAL, produced_by TEXT, grounding TEXT
);
CREATE INDEX edge_fwd   ON edge(subject, predicate, ord);
CREATE INDEX edge_back  ON edge(object,  predicate, ord);
CREATE INDEX edge_page  ON edge(pdf_page);
CREATE INDEX node_type  ON node(type);
"""


def load_view(graph: dict[str, Any], path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.executemany(
        "INSERT INTO node VALUES (?,?,?,?)",
        [(e["id"], e["type"], e.get("subtype", ""), json.dumps(e.get("properties", {})))
         for e in graph.get("entities", [])])
    rows = []
    for r in graph.get("relations", []):
        g = r.get("grounding") or {}
        pdf = g.get("pdf") or {}
        rows.append((
            r["subject_id"], r["predicate"], r["object_id"],
            g.get("ord", ""), g.get("layer", ""), g.get("role", ""),
            pdf.get("page"), json.dumps(pdf.get("bbox")) if pdf.get("bbox") else None,
            g.get("path", ""), r.get("confidence", 1.0), r.get("produced_by", ""),
            json.dumps(g) if g else None))
    conn.executemany(
        "INSERT INTO edge VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def children_in_order(conn, parent: str, predicate: str):
    return conn.execute(
        "SELECT object, ord FROM edge WHERE subject=? AND predicate=? ORDER BY ord",
        (parent, predicate)).fetchall()


def occurrences_of(conn, item_id: str):
    return conn.execute(
        "SELECT role, pdf_page, bbox, object AS logical_node, logical_path, ord "
        "FROM edge WHERE subject=? AND layer='occurrence' ORDER BY ord",
        (item_id,)).fetchall()


def items_on_page(conn, page: int):
    """Item-1 axis: every item occurring on a given PDF page."""
    return conn.execute(
        "SELECT e.subject, n.type, n.subtype, e.role, e.bbox "
        "FROM edge e JOIN node n ON n.id=e.subject "
        "WHERE e.layer='occurrence' AND e.pdf_page=? ORDER BY e.ord",
        (page,)).fetchall()


def occurrences_in_node(conn, node_id: str):
    """Item-2 axis: every item occurring within a given logical/structural node."""
    return conn.execute(
        "SELECT e.subject, n.type, e.role, e.pdf_page, e.ord "
        "FROM edge e JOIN node n ON n.id=e.subject "
        "WHERE e.layer='occurrence' AND e.object=? ORDER BY e.ord",
        (node_id,)).fetchall()
