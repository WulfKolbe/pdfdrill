"""The uniform enhancement pass-pipeline abstraction.

ChatGPT's linear `IR → math → citation → glossary → acronym → index → toc →
Enhanced IR` is a single-format slice of our tower; this is its general form: an
ordered, dependency-aware pipeline of idempotent PASSES over the L5 Document
(the IR), each a discrete enrichment, with multi-format input upstream and
multi-target projectors downstream unchanged.

Tested: topological ordering by `requires`, the runner (run / not-applicable /
unmet-deps-skip / error-isolation), and the real `math` pass end-to-end.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _o(id, t, **props):
    return types.SimpleNamespace(id=id, type=t, props=props)


def _doc(objs, meta=None):
    d = types.SimpleNamespace()
    d.objects = {o.id: o for o in objs}
    d.meta = meta or {}
    return d


def _fake(name, requires=(), applies=True, boom=False):
    from passes import EnhancementPass, PassResult

    class _F(EnhancementPass):
        def __init__(self):
            self.name = name
            self.requires = tuple(requires)
        def applies(self, ctx):
            return applies
        def run(self, ctx):
            if boom:
                raise RuntimeError("boom")
            ctx.doc.meta.setdefault("ran", []).append(name)
            return PassResult(name, "ran", changed=True, summary="ok")
    return _F()


def test_topological_order_by_requires():
    from passes import order
    a, b, c = _fake("a"), _fake("b", ["a"]), _fake("c", ["b"])
    seq = [p.name for p in order([c, a, b])]   # registration order shuffled
    assert seq == ["a", "b", "c"]


def test_pipeline_runs_in_dependency_order():
    from passes import PassContext, run_pipeline
    ctx = PassContext(doc=_doc([]))
    res = run_pipeline(ctx, passes=[_fake("b", ["a"]), _fake("a")])
    assert [r.name for r in res] == ["a", "b"]
    assert all(r.status == "ran" for r in res)
    assert ctx.doc.meta["ran"] == ["a", "b"]


def test_not_applicable_skips_dependents():
    from passes import PassContext, run_pipeline
    res = {r.name: r for r in run_pipeline(
        PassContext(doc=_doc([])),
        passes=[_fake("a", applies=False), _fake("b", ["a"])])}
    assert res["a"].status == "n/a"
    assert res["b"].status == "skipped"      # its dependency never ran


def test_error_is_isolated_and_pipeline_continues():
    from passes import PassContext, run_pipeline
    res = {r.name: r for r in run_pipeline(
        PassContext(doc=_doc([])),
        passes=[_fake("a", boom=True), _fake("b", ["a"]), _fake("c")])}
    assert res["a"].status == "error"
    assert res["b"].status == "skipped"      # depended on the failed pass
    assert res["c"].status == "ran"          # independent pass still ran


def test_builtin_passes_registered_in_sane_order():
    from passes import builtin_passes, order
    names = [p.name for p in order(builtin_passes())]
    assert {"math", "citation", "concepts", "toc"} <= set(names)
    assert names.index("concepts") < names.index("index")
    assert names.index("math") < names.index("summary")


def test_real_math_pass_through_pipeline():
    from passes import PassContext, run_pipeline
    from mathlayer import parse as mlparse
    fo = _o("f1", "Formula", latex=r"\frac{x^2+1}{2}")
    ctx = PassContext(doc=_doc([fo]))
    res = {r.name: r for r in run_pipeline(ctx, only={"math"})}
    if not mlparse.available():
        assert res["math"].status == "n/a"; print("SKIP (no parser)"); return
    assert res["math"].status == "ran"
    assert "math" in fo.props and fo.props["math"]["ir"] == "sympy"


if __name__ == "__main__":
    for fn in [test_topological_order_by_requires,
               test_pipeline_runs_in_dependency_order,
               test_not_applicable_skips_dependents,
               test_error_is_isolated_and_pipeline_continues,
               test_builtin_passes_registered_in_sane_order,
               test_real_math_pass_through_pipeline]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
