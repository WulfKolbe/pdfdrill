"""
semantic — the CSP-style semantic graph layer for PDFDRILL.

A domain-agnostic, evidence-backed, typed entity/relation graph that unifies
scientific (paper/formula/citation/concept) and commercial (company/person/
invoice/bank-account) documents under one model:

  Entity layer    : stable typed identities         (entity.py)
  Relation layer  : typed edges with provenance      (relation.py)
  Process layer   : the sensors that emit evidence   (process.py — registry)
  Proof layer     : why/what-evidence/which-process  (evidence.py + proof queries)

The graph is the primary artifact; extractors are sensors that emit Evidence,
which an IdentityResolver attaches to find-or-created entities (identity.py).
Additive — reads pdfdrill's existing layers; never modifies that pipeline.
"""
from .entity import Entity, EntityType
from .evidence import Evidence
from .graph import SemanticGraph
from .identity import IdentityResolver
from .relation import Relation, RelationType
from . import proof

__all__ = ["Entity", "EntityType", "Evidence", "SemanticGraph", "IdentityResolver",
           "Relation", "RelationType", "proof"]
