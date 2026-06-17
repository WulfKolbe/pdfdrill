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
      model        the docmodel artifact exists
      lines        a MathPix lines.json sits next to the PDF
      fact:NAME    the sidecar carries that fact"""
    if spec == "model":
        return model_path.exists()
    if spec == "lines":
        base = pdf.name[:-4] if pdf.name.lower().endswith(".pdf") else pdf.name
        return (pdf.parent / f"{base}.lines.json").exists()
    if spec.startswith("fact:"):
        return sc.has(spec[5:])
    return False


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


def ensure(target: str, pdf: Path, handlers: dict, pdf_arg: str) -> list[str]:
    """Run the missing OFFLINE prerequisites of `target` (not `target` itself)
    via their handlers, in order. Returns the prereq steps that were run. Each
    handler is idempotent, so this is safe even if a step turns out to be done."""
    steps, _ = resolve_steps(target, pdf)
    ran = []
    for step in steps[:-1]:                   # everything except the target
        fn = handlers.get(step)
        if fn is None:
            continue
        out = fn([pdf_arg])
        if out:
            print(out)
        ran.append(step)
    return ran
