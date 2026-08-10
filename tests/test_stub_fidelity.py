"""Every test stub must be a subset of the real class it stands in for.

`_SC` diverged from `Sidecar` three times in one week, and the failure mode is
the bad one: the stub invented `add_evidence`, the production call raised
AttributeError, an `except Exception` swallowed it, and the test passed having
exercised nothing. Later, when retraction started calling `set_evidence`, seven
tests failed for the same reason in reverse.

The rule this pins is one-directional and cheap: a public method a stub defines
must EXIST on the real class. A stub may cover less than the real thing — that
is what a stub is for — but it may never offer a name the real thing does not
have, because that name is exactly what production code will call and find
missing at runtime.
"""
import importlib
import inspect
import pkgutil
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests"))

# stub class name -> the real class it stands in for
_STANDS_FOR = {
    "_SC": ("pdfdrill.sidecar", "Sidecar"),
    "_Sidecar": ("pdfdrill.sidecar", "Sidecar"),
    "_Doc": ("docmodel.core", "Document"),
    "_Obj": ("docmodel.core", "DocObject"),
}


def _test_modules():
    for m in pkgutil.iter_modules([str(_ROOT / "tests")]):
        if m.name.startswith("test_") and m.name != Path(__file__).stem:
            yield m.name


def _public(cls):
    return {n for n, _v in inspect.getmembers(cls)
            if not n.startswith("_") and n in vars(cls)}


def _real_names(cls) -> set:
    """Every public name the real class offers — including the ones `hasattr`
    on the CLASS cannot see. `Document.objects` is a dataclass field set in
    __init__, so a class-level check reported it missing and flagged two honest
    stubs. Fields and annotations are part of the surface."""
    names = {n for n in dir(cls) if not n.startswith("_")}
    names |= set(getattr(cls, "__dataclass_fields__", {}) or {})
    names |= set(getattr(cls, "__annotations__", {}) or {})
    for base in getattr(cls, "__mro__", ()):
        names |= set(getattr(base, "__annotations__", {}) or {})
    return names


def _pairs():
    """(module, stub class, real class) for every stub we can resolve."""
    out = []
    for name in _test_modules():
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue                      # a module that will not import is
                                          # its own test's problem, not this one
        for attr, obj in vars(mod).items():
            if not inspect.isclass(obj) or attr not in _STANDS_FOR:
                continue
            if getattr(obj, "__module__", None) != name:
                continue                  # imported, not declared here
            real_mod, real_name = _STANDS_FOR[attr]
            try:
                real = getattr(importlib.import_module(real_mod), real_name)
            except Exception:
                continue
            out.append((name, obj, real))
    return out


_PAIRS = _pairs()


def test_the_scan_actually_found_stubs():
    """A pass because nothing was inspected is the failure this file exists
    to prevent, so the scan asserts its own reach."""
    assert len(_PAIRS) >= 4, [p[0] for p in _PAIRS]
    assert any(p[1].__name__ == "_SC" for p in _PAIRS)


@pytest.mark.parametrize("modname,stub,real",
                         _PAIRS, ids=[f"{m}:{s.__name__}" for m, s, _r in _PAIRS])
def test_a_stub_offers_no_name_the_real_class_lacks(modname, stub, real):
    offered = _real_names(real)
    invented = sorted(n for n in _public(stub) if n not in offered)
    assert not invented, (
        f"{modname}:{stub.__name__} defines {invented}, which {real.__name__} "
        f"does not have — production calling that name would raise")


def test_the_rule_catches_the_bug_it_was_written_for():
    """`add_evidence` is the exact name that was invented; a stub offering it
    must be rejected by the same predicate."""
    from pdfdrill.sidecar import Sidecar

    class _Bad:
        def add_evidence(self, k, v): ...

    assert sorted(n for n in _public(_Bad)
                  if n not in _real_names(Sidecar)) == ["add_evidence"]
