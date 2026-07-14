"""
The capability GRAPH — per pdfdrill command, the sidecar facts it PRODUCES and
DESTROYS. This is the action table the capability planner traverses
(`capability_planner.py`), Phase A of
docs/superpowers/plans/2026-07-14-capability-planner.md.

Two sources, deliberately kept distinct:

* **produces** is DERIVED from the handlers' own `add_fact(...)` calls (parsed
  from `commands.py`'s AST, cached). It can never drift from the code — a command
  produces exactly the facts it marks.

* **destroys** is the CLOBBER SEMANTICS the proposal names as the non-negotiable
  first addition. A docmodel rebuild (`model`/`markdown`/`latexbook`) reads
  lines.json and OVERWRITES the model file, silently discarding every A-mode
  enrichment (latex ingest, geometry fusion, eqnums, nlp, bibliography, …) — yet
  it never calls `remove_fact` on those facts, so the sidecar keeps LYING that
  they hold. That invalidation is not in the code as a retraction; it is authored
  here so the planner refuses a plan that rebuilds the model when a still-needed
  enrichment is held. The few explicit `remove_fact` calls (latex/visionocr
  clearing NEEDS_VISION_OCR — a rank UPGRADE) are folded in too.

Pure stdlib. `produces()`/`destroys()`/`capability_graph()` are the API.
"""
from __future__ import annotations

import ast
import functools
from pathlib import Path

_COMMANDS_PY = Path(__file__).with_name("commands.py")

# Commands that (re)build the docmodel from scratch and therefore clobber every
# model-derived enrichment fact.
MODEL_BUILDERS = ("model", "markdown", "latexbook")

# The A-mode enrichment facts a docmodel rebuild invalidates. Everything here is
# a fact set by a command that operates ON the model (or writes a model-derived
# artifact); rebuilding the model from lines.json discards all of it. NOT listed:
# the model's INPUTS (SIZE_KNOWN, MATHPIX_KNOWN, OCR_BUILT = the lines.json) and
# the sidecar/OCR-layer facts that don't live in the docmodel (fonts/images/tsv/
# links/urls/dests/attachments/formfields/tables/qr/rasterized/continuity/
# entities/segmented/md — independent of a model rebuild).
_MODEL_DERIVED = (
    "LATEX_INGESTED", "GEOMETRY_FUSED", "EQNUMS_FUSED", "NLP_ENHANCED",
    "LISTS_BUILT", "ALGORITHMS_BUILT", "ANNOTATIONS_BUILT", "SCORED",
    "ESCALATION_OPEN", "BIBLIOGRAPHY_BUILT", "BIBFETCH_DONE", "BIBSOURCE_BUILT",
    "EMBEDDED_IMAGES_BUILT", "SEMANTIC_BUILT", "ELEMENTS_BUILT",
    "TIDDLERS_BUILT", "COMPARE_BUILT", "REPORT_BUILT", "VISION_DONE",
    "SNIP_RAN", "TRANSLATED", "SPELLQC_BUILT", "FONTID_BUILT",
)


@functools.lru_cache(maxsize=1)
def _parse() -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
    """Parse commands.py once → (fact constants, per-command add_fact facts,
    per-command remove_fact facts)."""
    tree = ast.parse(_COMMANDS_PY.read_text(encoding="utf-8"))
    consts: dict[str, str] = {}
    for n in tree.body:
        if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str)):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    consts[t.id] = n.value.value

    def _fact(arg) -> str | None:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value if arg.value in consts.values() else arg.value
        if isinstance(arg, ast.Name) and arg.id in consts:
            return consts[arg.id]
        return None

    adds: dict[str, list[str]] = {}
    rems: dict[str, list[str]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name.startswith("cmd_"):
            cmd = n.name[4:]
            a: set[str] = set()
            r: set[str] = set()
            for c in ast.walk(n):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.args:
                    f = _fact(c.args[0])
                    if not f:
                        continue
                    # `mark(fact, …)` sets the fact AND records a proof, so it is
                    # a producer exactly like `add_fact(fact)`.
                    if c.func.attr in ("add_fact", "mark"):
                        a.add(f)
                    elif c.func.attr in ("remove_fact", "discard"):
                        r.add(f)
            if a:
                adds[cmd] = sorted(a)
            if r:
                rems[cmd] = sorted(r)
    # values() may include evidence-key strings; keep only real fact NAMES
    return consts, adds, rems


def fact_constants() -> list[str]:
    """Every UPPER_CASE fact/evidence constant declared at module level."""
    return sorted(_parse()[0])


def all_facts() -> set[str]:
    """The full fact UNIVERSE: module constants ∪ every fact a command produces
    or removes (some facts are bare `add_fact("X")` string literals, not module
    constants). This is the set `destroys:`/`requires:` must resolve against."""
    consts, adds, rems = _parse()
    universe: set[str] = set(consts)
    for facts in adds.values():
        universe.update(facts)
    for facts in rems.values():
        universe.update(facts)
    return universe


def produces() -> dict[str, list[str]]:
    """{command: [facts it add_fact()s]} — AST-derived, code-synced."""
    return dict(_parse()[1])


def _removes() -> dict[str, list[str]]:
    return dict(_parse()[2])


@functools.lru_cache(maxsize=1)
def proof_emitting() -> frozenset[str]:
    """Commands whose handler calls `sc.mark(...)` — i.e. records a proof object,
    not just `add_fact`. The census that keeps Phase-B proof adoption VISIBLE: as
    more producers migrate, this set grows (and the census test tracks it)."""
    tree = ast.parse(_COMMANDS_PY.read_text(encoding="utf-8"))
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name.startswith("cmd_"):
            for c in ast.walk(n):
                if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                        and c.func.attr == "mark" and c.args):
                    out.add(n.name[4:])
    return frozenset(out)


def destroys(command: str) -> list[str]:
    """The facts `command` invalidates: the model-rebuild clobber list for a
    docmodel builder, plus any explicit remove_fact the handler performs."""
    out: set[str] = set(_removes().get(command, []))
    if command in MODEL_BUILDERS:
        out.update(_MODEL_DERIVED)
    return sorted(out)


def _manifest_requires() -> dict[str, list[str]]:
    """Command-name prerequisites from the manifest (the existing planner's
    `requires:`), carried into the graph unchanged."""
    try:
        import yaml  # optional; the graph still works without requires
    except Exception:  # noqa: BLE001
        return {}
    mpath = (Path(__file__).resolve().parents[2] / ".claude" / "skills"
             / "pdfdrill" / "commands.yaml")
    if not mpath.is_file():
        mpath = Path(__file__).with_name("skill") / "commands.yaml"
    try:
        data = yaml.safe_load(mpath.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, list[str]] = {}
    for c in data.get("commands", []):
        req = c.get("requires")
        if req:
            out[c["name"]] = list(req)
    return out


def capability_graph() -> dict[str, dict]:
    """The merged action table: {command: {produces, destroys, requires}} for
    every command that produces/destroys a fact or carries a manifest prereq."""
    prod = produces()
    reqs = _manifest_requires()
    names = set(prod) | set(_removes()) | set(reqs) | set(MODEL_BUILDERS)
    graph: dict[str, dict] = {}
    for cmd in sorted(names):
        graph[cmd] = {
            "produces": prod.get(cmd, []),
            "destroys": destroys(cmd),
            "requires": reqs.get(cmd, []),
        }
    return graph
