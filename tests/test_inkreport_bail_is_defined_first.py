"""578 — a guard placed after the code it guards is not a guard.

`_bail` restores the reading build when a measurement fails; step 2b calls it
when the measure build names a table with no rows. It was DEFINED forty lines
below that call. Python binds a name assigned anywhere in a function for the
whole function, so the call raised UnboundLocalError, the restore never ran,
and report.pdf was left as the 1-page phase-1 scaffolding — on precisely the
document that needed the refusal.

Same shape as 575's decorator landing away from its function: a definition
separated from what depends on it is invisible in review and fatal at runtime.
"""
import ast
import inspect

from pdfdrill import commands as C


def _inkreport_ast():
    src = inspect.getsource(C.cmd_inkreport)
    return ast.parse(src.lstrip())


def test_bail_is_defined_before_every_call_to_it():
    tree = _inkreport_ast()
    defs = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_bail"]
    loads = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Name) and n.id == "_bail"
             and isinstance(n.ctx, ast.Load)]
    assert defs, "cmd_inkreport must define _bail"
    assert loads, "…and must use it"
    early = [n for n in loads if n < defs[0]]
    assert not early, (
        "_bail is called at line(s) %s of cmd_inkreport but not defined until "
        "line %d — those calls raise UnboundLocalError and the reading build "
        "is never restored." % (early, defs[0]))


def test_no_local_function_in_cmd_inkreport_is_used_before_it_is_defined():
    """The general form, so the next helper does not repeat this."""
    tree = _inkreport_ast()
    defs = {n.name: n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name != "cmd_inkreport"}
    bad = [(n.id, n.lineno, defs[n.id]) for n in ast.walk(tree)
           if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
           and n.id in defs and n.lineno < defs[n.id]]
    assert not bad, "used before defined: %s" % (bad,)


def test_bail_restores_the_stashed_ink_before_rebuilding():
    """578 — step 2 stashes report.ink.json and un-stashes it in a `finally`.
    `_bail` is called from inside that `try`, and a `return`'s expression is
    evaluated BEFORE the `finally` runs, so the restore build saw no ink and
    stamped ink_adopted=False. The reading build it restored was not the
    reading build."""
    src = inspect.getsource(C.cmd_inkreport)
    i = src.index("def _bail(lines):")
    j = src.index("cmd_reporttex(", i)
    head = src[i:j]
    assert "inkreport-hold" in head, (
        "_bail rebuilds without restoring the stashed report.ink.json first")
