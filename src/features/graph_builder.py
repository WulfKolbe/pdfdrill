"""
graph_builder — build a NetworkX DiGraph from a flat list of Relations.

NetworkX is the primary choice (connected_components / pagerank / clustering).
igraph is only worth it if networkx is a proven bottleneck on very large graphs;
graph-tool is intentionally avoided.
"""
from __future__ import annotations

from .relations import Relation


def build_graph(relations: list[Relation]):
    """Return an `nx.DiGraph` with one edge per Relation (type + weight on edge)."""
    import networkx as nx  # lazy: only needed for graph ops
    g = nx.DiGraph()
    for rel in relations:
        g.add_edge(rel.source, rel.target, type=rel.type, weight=rel.weight)
    return g
