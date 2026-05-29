"""
Base classes for docops operators.

Mirrors the modular pattern of the docmodel converter, but with two
operator subtypes (Mutator and Projector) since their contracts differ:

  Mutator.apply(doc)         -> None    (modifies doc in place)
  Projector.project(doc)     -> result  (produces an artifact, doesn't touch doc)
  Projector.write(result, p) -> None    (persists the artifact to disk)

Operators are configured via small JSON entries; the loader instantiates
them in order. Each operator can also receive per-instance `params` from
the config — independent of the framework so authors can keep operators
self-contained.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from docmodel.core import Document


@dataclass
class OperatorConfig:
    """Configuration entry for a single operator in the pipeline."""
    op: str                       # 'mutator' or 'projector'
    classname: str
    title: str = ""               # human-readable label
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> "OperatorConfig":
        if "classname" not in d:
            raise ValueError(f"OperatorConfig requires 'classname': {d}")
        if "op" not in d:
            raise ValueError(f"OperatorConfig requires 'op': {d}")
        return cls(
            op=d["op"],
            classname=d["classname"],
            title=d.get("title", d["classname"]),
            params=dict(d.get("params", {})),
            enabled=bool(d.get("enabled", True)),
        )


class BaseOperator(ABC):
    """Common parent for both Mutators and Projectors."""

    def __init__(self, config: OperatorConfig, flags: Optional[dict] = None):
        self.config = config
        self.params = dict(config.params)
        self.flags = flags or {}
        self.debug = bool(self.flags.get("debug", False))
        self.counters: dict[str, int] = {}

    def name(self) -> str:
        return self.config.title or self.config.classname

    def log(self, message: str) -> None:
        import sys
        print(f"[{self.name()}] {message}", file=sys.stderr)

    def bump(self, key: str, n: int = 1) -> int:
        self.counters[key] = self.counters.get(key, 0) + n
        return self.counters[key]


class BaseMutator(BaseOperator):
    """Operator that modifies the Document in place."""

    @abstractmethod
    def apply(self, doc: Document) -> None: ...


class BaseProjector(BaseOperator):
    """
    Operator that derives an artifact from the Document without modifying it.

    Subclasses implement `project(doc) -> Any` and optionally override
    `output_extension()` and `write(result, path)` if their output isn't
    a simple UTF-8 string.
    """

    def output_extension(self) -> str:
        """Filename suffix for the artifact this projector produces."""
        return ".txt"

    @abstractmethod
    def project(self, doc: Document) -> Any: ...

    def write(self, result: Any, path: str) -> None:
        """Default writer: if result is bytes, write binary; else UTF-8 text."""
        if isinstance(result, bytes):
            with open(path, "wb") as f:
                f.write(result)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(result if isinstance(result, str) else str(result))
