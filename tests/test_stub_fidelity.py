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
        except (Exception, pytest.skip.Exception):
            # a module that will not import is its own test's problem, not
            # this one — and `pytest.importorskip` is how it says so. `Skipped`
            # is NOT an Exception (Skipped -> OutcomeException ->
            # BaseException), so `except Exception` alone let it escape here
            # while this file was being collected, and pytest then skipped the
            # whole file: 0 of 23 pairs checked, reported as "1 skipped", on
            # every install without pyvips.
            continue
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


#: The floor under `_PAIRS`, one below the MEASURED minimum.
#:
#: Measured 2026-10-30 on two installs: 23 pairs on a full one, and 23 on one
#: with none of sympy, pikepdf, pyvips or img2pdf — the four optional packages
#: that decide what this suite collects. They agree because no module that
#: declares a stub needs any of the four, which is a fact about today's corpus
#: and not a guarantee, so this stays a floor: an install that legitimately
#: cannot import one stub-declaring module should not fail here.
#:
#: What the floor is FOR is the collapse. The gate checked 0 of its 23 pairs on
#: every install without pyvips and said so only as "1 skipped" — see
#: `test_a_module_that_skips_at_import_does_not_take_the_whole_gate_with_it`.
#: `>= 4` was too low to notice that, since 4 is also what a badly broken scan
#: returns.
_PAIR_FLOOR = 22


def test_the_scan_actually_found_stubs():
    """A pass because nothing was inspected is the failure this file exists
    to prevent, so the scan asserts its own reach."""
    assert len(_PAIRS) >= _PAIR_FLOOR, [p[0] for p in _PAIRS]
    assert any(p[1].__name__ == "_SC" for p in _PAIRS)


def test_a_module_that_skips_at_import_does_not_take_the_whole_gate_with_it(
        tmp_path, monkeypatch):
    """`pytest.importorskip` raises `Skipped`, and `Skipped` is NOT an
    `Exception`: its MRO is Skipped -> OutcomeException -> BaseException. So
    `except Exception` around the import let it escape `_pairs()` while this
    module was being COLLECTED, and pytest skipped the whole file — 0 of 23
    pairs checked, reported as "1 skipped" (25 node ids: the 23 pairs and the
    two plain tests).

    Measured 2026-10-30 on an install without pyvips, which is every install
    the README documents: `pytest --collect-only -rs tests/test_stub_fidelity.py`
    gave "collected 0 items / 1 skipped — could not import 'pyvips'".
    """
    (tmp_path / "test_a_module_that_skips_itself.py").write_text(
        "import pytest\n"
        "pytest.importorskip('a_package_this_machine_does_not_have')\n",
        encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(sys.modules[__name__], "_test_modules",
                        lambda: iter(["test_a_module_that_skips_itself"]))
    try:
        pairs = _pairs()
    except BaseException as exc:          # noqa: BLE001 — the point of the test
        raise AssertionError(
            f"_pairs() let {type(exc).__name__} escape, which skips this whole "
            f"file and every pair it should have checked") from None
    assert pairs == []


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
