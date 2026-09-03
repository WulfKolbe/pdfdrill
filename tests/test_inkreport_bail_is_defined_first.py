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


def test_step_2_does_not_hide_the_ink_from_its_own_build():
    """579 — step 2 no longer stashes report.ink.json. While it did, phase 1
    could not select `flagged` or `doubted` (they are chosen BY the ink code),
    so the measure build was a different document from the published one, and
    `_bail` — called from inside the stashing `try`, whose `finally` runs
    AFTER a return is evaluated — rebuilt with the file still hidden."""
    src = inspect.getsource(C.cmd_inkreport)
    assert "held.replace(stash)" not in src, (
        "step 2 still hides the ink from the measure build")
    assert "ink_bullets=False" in src, (
        "the measure build must read the ink and withhold only the bullet")


def test_bail_still_recovers_a_hold_left_by_an_older_run():
    """An interrupted pre-579 run can have left the file stashed; an upgrade
    must not strand it."""
    src = inspect.getsource(C.cmd_inkreport)
    i = src.index("def _bail(lines):")
    j = src.index("cmd_reporttex(", i)
    assert "inkreport-hold" in src[i:j]
