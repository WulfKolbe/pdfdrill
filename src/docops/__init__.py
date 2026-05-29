"""
docops — modular operators on DocObject documents.

Two operator categories:
  - Mutator:    receives a Document, modifies it in place (adds streams,
                objects, alignments, or updates props). Returns nothing.
  - Projector:  receives a Document, produces a derived artifact (text,
                JSON, markdown, tokens). Does NOT modify the Document.

A pipeline is a config-driven sequence of operators applied in order.
"""
from .base import (
    BaseOperator, BaseMutator, BaseProjector, OperatorConfig,
)

__all__ = ["BaseOperator", "BaseMutator", "BaseProjector", "OperatorConfig"]
