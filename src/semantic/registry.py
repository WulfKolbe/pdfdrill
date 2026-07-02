"""
FnSpec registry — every semantic function (extractor / operator / metric /
verifier / physical constraint / calibrator) as a first-class, versioned,
law-carrying spec (Stage 0 of the quantitative semantic layer).

This deliberately mirrors `semantic/question.py`'s `Question`/`REGISTRY` shape
(read that module first): a frozen dataclass, a module-level dict, register
REPLACES on the same id, `to_dict`/`from_dict` round-trip. Where a `Question`
reifies a PASS (what an invocation is for), an `FnSpec` reifies a FUNCTION —
the unit a `Transformation` records having composed (`Transformation.fns`).

Namespace convention for fids:
    SO.*   extractors        (e.g. SO.QUANT.EXTRACT, SO.MEAS.BIND)
    OP.*   operators         (e.g. OP.GROUND)
    SIM.*  similarity metrics
    VER.*  verifiers         (e.g. VER.EQ.RECOMPUTE)
    PHY.*  physical constraints (e.g. PHY.BOUNDS, PHY.CONSERVE)
    CAL.*  calibration       (e.g. CAL.PRECISION.WILSON)

`laws` name the algebraic properties an impl is expected to satisfy
("symmetric", "monotone", …) — documentation-grade today, property-test hooks
tomorrow. `params` document the impl's tunables with their defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class FnSpec:
    fid: str                                   # stable id, namespaced (SO./VER./…)
    description: str                           # human-readable intent
    version: str = "1"                         # bump when the impl's logic changes
    params: dict = field(default_factory=dict, hash=False, compare=True)
    laws: tuple[str, ...] = ()                 # named algebraic properties

    def to_dict(self) -> dict[str, Any]:
        return {"fid": self.fid, "description": self.description,
                "version": self.version, "params": dict(self.params),
                "laws": list(self.laws)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FnSpec":
        return cls(fid=d["fid"], description=d.get("description", ""),
                   version=d.get("version", "1"), params=dict(d.get("params", {})),
                   laws=tuple(d.get("laws", ())))


@dataclass(frozen=True)
class RegisteredFn:
    spec: FnSpec
    impl: Callable


# --------------------------------------------------------------------------- #
#  Registry — register replaces on the same fid (question.py semantics).
# --------------------------------------------------------------------------- #
REGISTRY: dict[str, RegisteredFn] = {}


def register_fn(spec: FnSpec, impl: Callable) -> RegisteredFn:
    """Register (or replace) a function by its spec's fid. Returns the entry."""
    entry = RegisteredFn(spec=spec, impl=impl)
    REGISTRY[spec.fid] = entry
    return entry


def get_fn(fid: str) -> Optional[RegisteredFn]:
    """The registered function behind an fid, or None if unregistered."""
    return REGISTRY.get(fid)


def all_fns() -> list[FnSpec]:
    return [e.spec for e in REGISTRY.values()]


def explain(fid: str, *args, **kwargs) -> dict[str, Any]:
    """Run a registered function and wrap the result with its spec provenance —
    the auditable form callers/tests use: {fid, version, args, result}."""
    entry = REGISTRY.get(fid)
    if entry is None:
        raise KeyError(f"no registered function: {fid}")
    return {"fid": entry.spec.fid, "version": entry.spec.version,
            "args": args, "kwargs": kwargs or {},
            "result": entry.impl(*args, **kwargs)}
