"""
planner — the prerequisite state machine.

pdfdrill commands form a dependency chain (most analysis commands need a built
`model`; `bibfetch`/`citedrill` need a parsed `bibliography`). Historically each
handler chained its own prerequisites ad-hoc. This module makes the chain
DECLARATIVE and introspectable: each command declares `requires:` and a
`done_when:` detector in `commands.yaml`, and `plan()` computes — from the
current sidecar/artifact state — the ordered list of missing steps to run before
a target command.

  pdfdrill steps <cmd> <pdf>     show the chain: what's done, what would run
  pdfdrill <cmd> <pdf> --ensure  auto-run the missing prerequisites, then <cmd>

SAFETY: only OFFLINE, idempotent prerequisites (`model`, `bibliography`) are ever
declared/auto-run. Paid/network steps (mathpix/bibfetch/vision/translate) are
never auto-inserted — `model` self-bootstraps mathpix-or-OCR internally, so the
planner stays free and side-effect-light. The target itself always runs (it is
what the user asked for); only its missing prerequisites are inserted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def load_manifest() -> dict:
    """The canonical command manifest (bundled copy, else the repo's .claude/)."""
    from . import skill_cmd
    import yaml
    return yaml.safe_load((skill_cmd._skill_dir() / "commands.yaml").read_text())


def load_graph(manifest: dict) -> tuple[dict[str, list[str]], dict[str, str]]:
    """(requires, done_when) maps from the manifest."""
    requires: dict[str, list[str]] = {}
    done: dict[str, str] = {}
    for c in manifest.get("commands", []):
        if c.get("requires"):
            requires[c["name"]] = list(c["requires"])
        if c.get("done_when"):
            done[c["name"]] = c["done_when"]
    return requires, done


def plan(target: str, requires: dict[str, list[str]], satisfied: set[str]) -> list[str]:
    """Ordered steps to satisfy `target`: each UNSATISFIED transitive prerequisite
    (deepest first), then `target` itself (which always runs). Cycle-safe."""
    out: list[str] = []

    def add(cmd: str, stack: frozenset) -> None:
        if cmd in stack:                      # cycle guard
            return
        for dep in requires.get(cmd, []):
            if dep in satisfied or dep in out:
                continue
            add(dep, stack | {cmd})
            if dep not in out:
                out.append(dep)

    add(target, frozenset())
    out.append(target)
    return out


def detect(spec: str, sc, pdf: Path, model_path: Path) -> bool:
    """Is a prerequisite's `done_when` spec satisfied for this document?
      model           the docmodel artifact exists
      model:geometry  …and its objects actually carry regions
      lines           a MathPix lines.json sits next to the PDF
      fact:NAME       the sidecar carries that fact

    `model` is a PRESENCE test and `model:geometry` an ADEQUACY one. The
    distinction matters: a model built by a lane that produces no object regions
    is a perfectly good file that `inspect` can draw nothing from, and a
    presence test calls that state satisfied.
    """
    if spec == "model":
        return model_path.exists()
    if spec == "model:geometry":
        return _model_has_regions(model_path)
    if spec == "model:citations_resolved":
        return _citations_resolved(model_path)
    if spec == "lines":
        base = pdf.name[:-4] if pdf.name.lower().endswith(".pdf") else pdf.name
        return (pdf.parent / f"{base}.lines.json").exists()
    if spec.startswith("fact:"):
        return sc.has(spec[5:])
    return False


def _model_has_regions(model_path: Path) -> bool:
    """True if ANY object in the model carries a region. Reads the objects list
    directly (no Document build) so the check stays cheap enough to run on every
    plan; any read error answers False, so a missing capability is never assumed.
    """
    import json
    if not model_path.exists():
        return False
    try:
        with open(model_path, "r", encoding="utf-8") as f:
            objs = json.load(f).get("objects") or []
    except (OSError, json.JSONDecodeError):
        return False
    it = objs.values() if isinstance(objs, dict) else objs
    return any((o.get("props") or {}).get("region") for o in it)


def _citations_resolved(model_path: Path) -> bool:
    """Does the model have the References its Citations point at?

    True when there is nothing to resolve (no Citations) or at least one
    Reference exists. Deliberately reads the MODEL rather than a sidecar fact:
    the fact records that `bibliography` once ran, but the References it
    produced live in the model, and rebuilding the model discards them while the
    fact stays set — so the machine believed the bibliography existed while
    every citation rendered as a placeholder stub.
    """
    import json
    if not model_path.exists():
        return False
    try:
        with open(model_path, "r", encoding="utf-8") as f:
            objs = json.load(f).get("objects") or []
    except (OSError, json.JSONDecodeError):
        return False
    it = list(objs.values()) if isinstance(objs, dict) else objs
    has_cit = has_ref = False
    for o in it:
        t = o.get("type")
        if t == "Citation":
            has_cit = True
        elif t == "Reference":
            has_ref = True
            break                       # one is enough to call it resolved
    return has_ref or not has_cit


def satisfied_set(done: dict[str, str], sc, pdf: Path, model_path: Path) -> set[str]:
    return {cmd for cmd, spec in done.items() if detect(spec, sc, pdf, model_path)}


# --------------------------------------------------------------------------- #
#  Command-level glue (used by cli._do_steps and the --ensure pre-step).
# --------------------------------------------------------------------------- #
def resolve_steps(target: str, pdf: Path) -> tuple[list[str], set[str]]:
    """(ordered steps incl. target, satisfied set) for `target` on `pdf`."""
    from .sidecar import Sidecar
    from .commands import _model_path
    man = load_manifest()
    requires, done = load_graph(man)
    sc = Sidecar(pdf)
    sat = satisfied_set(done, sc, pdf, _model_path(sc))
    return plan(target, requires, sat), sat


def describe(target: str, pdf: Path) -> str:
    steps, sat = resolve_steps(target, pdf)
    prereqs = steps[:-1]
    if not prereqs:
        return (f"`{target}` for {pdf.name}: prerequisites satisfied "
                f"({', '.join(sorted(sat)) or 'none required'}) — runs directly.")
    return (f"`{target}` for {pdf.name} would run, in order:\n  "
            + " → ".join(f"{s}" for s in steps)
            + f"\n  (missing prerequisites auto-inserted by --ensure: "
            f"{', '.join(prereqs)}; already done: {', '.join(sorted(sat)) or 'none'})")


def ensure(target: str, pdf: Path, handlers: dict, pdf_arg: str,
           quiet: bool = True) -> list[str]:
    """Run the missing OFFLINE prerequisites of `target` (not `target` itself)
    via their handlers, in order. Returns the prereq steps that were run. Each
    handler is idempotent, so this is safe even if a step turns out to be done.

    SILENT by default. A prerequisite is machinery, not an answer: printing each
    step's report turns one request into a wall of intermediate commentary and
    buries the result the user actually asked for. Pass `quiet=False` when
    debugging a chain (`pdfdrill steps` shows the plan without running it).
    """
    steps, _ = resolve_steps(target, pdf)
    ran = []
    for step in steps[:-1]:                   # everything except the target
        fn = handlers.get(step)
        if fn is None:
            continue
        out = fn([pdf_arg])
        if out and not quiet:
            print(out)
        ran.append(step)
    return ran
