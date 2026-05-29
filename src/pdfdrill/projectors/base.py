"""Base class for document projectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..context import DocumentContext


class Projector(ABC):
    name: str = "base"

    @abstractmethod
    def project(self, ctx: DocumentContext) -> str:
        """Produce output string from the DocumentContext."""
