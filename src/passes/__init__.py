"""passes — the uniform document-enhancement pass pipeline.

An ordered, dependency-aware sequence of idempotent PASSES over the L5 Document
(the IR): frontmatter / math / citation / concepts (glossary+acronym) / abstract
/ toc / index / summary. The general form of ChatGPT's linear
`IR → pass → … → Enhanced IR`, decoupled from any single input format or output
backend (multi-format acquisition feeds it; any projector consumes the result).

    from passes import PassContext, run_pipeline
    results = run_pipeline(PassContext(doc=document))
    # each result: .name .status(ran|n/a|skipped|error) .changed .summary .stats
"""
from __future__ import annotations

from .base import (EnhancementPass, PassContext, PassResult, REGISTRY,
                   builtin_passes, order, register_pass, run_pipeline)
from . import builtin as _builtin   # noqa: F401  (registers the built-in passes)

__all__ = [
    "EnhancementPass", "PassContext", "PassResult",
    "REGISTRY", "register_pass", "builtin_passes", "order", "run_pipeline",
]
