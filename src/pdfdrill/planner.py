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
    """(requires, done_when) maps from the manifest.

    310 — `reporttex` and `inkconvert` require EACH OTHER, and that is not a
    modelling error: the report is built twice. The first build is the
    `measure` phase, inkdrill measures its PDF, `inkconvert` turns that
    measurement into report.ink.json, and the second build adopts it and
    becomes the `reading` phase. One command name, two phases, so the edge
    genuinely points both ways.

    `plan` drops the back edge, so asking for `reporttex` plans
    `... inkconvert -> reporttex` and asking for `inkconvert` plans
    `... reporttex -> inkconvert` — each the right order for what was asked.
    It did not do that until 310: the guard stopped the RECURSION but still
    appended the dependency, so a fresh document planned reporttex twice.
    """
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
            if dep in stack:
                # 310 — the back edge of a cycle. Recursing was already
                # guarded, but the append was not, so `reporttex` requiring
                # `inkconvert` requiring `reporttex` planned reporttex TWICE:
                # once as its own prerequisite, once as the target. It only
                # stayed hidden because every document that had a report
                # already satisfied the edge.
                continue
            add(dep, stack | {cmd})
            if dep not in out:
                out.append(dep)

    add(target, frozenset())
    out.append(target)
    return out


def detect(spec: str, sc, pdf: Path, model_path: Path) -> bool:
    """Is a prerequisite's `done_when` spec satisfied for this document?
      model                    the docmodel artifact exists
      model:geometry           …and its objects actually carry regions
      model:citations_resolved …and it holds the References its Citations need
      artifact:tiddlers        a tiddler array exists and is not older than the
                               model it was projected from
      artifact:report          report.tex AND report.pdf exist, the pdf is not
                               older than the tex, and neither is empty
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
    if spec == "model:translated":
        return _model_has_translation(model_path)
    if spec == "artifact:tiddlers":
        return _tiddlers_current(sc, model_path)
    if spec == "artifact:report":
        return _report_current(sc)
    if spec == "lines":
        base = pdf.name[:-4] if pdf.name.lower().endswith(".pdf") else pdf.name
        return (pdf.parent / f"{base}.lines.json").exists()
    if spec.startswith("fact:"):
        return sc.has(spec[5:])
    if spec == "lines:mathpix":
        # genuine MathPix geometry: lines.json exists, post-dates the PDF,
        # and IS MathPix (keyless routes stamp a `source` key; MathPix none)
        base = pdf.name[:-4] if pdf.name.lower().endswith(".pdf") else pdf.name
        lp = pdf.parent / f"{base}.lines.json"
        if not lp.exists() or not pdf.exists():
            return False
        if lp.stat().st_mtime < pdf.stat().st_mtime:
            return False
        from .commands import _is_mathpix_lines
        return _is_mathpix_lines(lp)
    if spec == "artifact:cdncrops":
        return _cdncrops_done(sc, pdf)
    if spec == "artifact:ink":
        return _ink_current(sc)
    return False


def _ink_current(sc) -> bool:
    """310 — report.ink.json exists and is not empty.

    PRESENCE, not freshness, and deliberately: `inkconvert` refuses to
    overwrite an existing report.ink.json without --force, so a freshness test
    would report the document unsatisfied forever while the step that is meant
    to satisfy it declines to act. A detector must agree with the command it
    detects, or the planner asks for the same thing on every run.
    """
    f = sc.blob_dir / "report.ink.json"
    return f.is_file() and f.stat().st_size > 0


def _report_current(sc) -> bool:
    """234 — `reporttex` had no done_when at all, so the planner treated it as
    never satisfied and it could not be named as anyone's prerequisite. It
    produces report.tex and report.pdf; this is the detector it should have
    carried.

    A .tex written beside an OLDER .pdf is the stale pair cmd_reporttex already
    warns about, and a zero-byte pdf passes any name-only check — the pages
    repo's CI learned that one ("the guard checked names, so a zero-byte
    report.pdf passed it"), so size is part of the test here too.
    """
    tex = sc.blob_dir / "report.tex"
    pdf_out = sc.blob_dir / "report.pdf"
    if not (tex.is_file() and pdf_out.is_file()):
        return False
    if tex.stat().st_size == 0 or pdf_out.stat().st_size == 0:
        return False
    return pdf_out.stat().st_mtime >= tex.stat().st_mtime


def _cdncrops_done(sc, pdf: Path) -> bool:
    """Every EQ tiddler with a CDN canonical_uri has its crop on disk. A
    document whose math carries no CDN crops (keyless routes) is trivially
    satisfied — there is nothing to fetch."""
    import json as _json
    rel = None
    try:
        rel = sc.get_evidence("tiddlers_path")
    except Exception:
        pass
    tid = (pdf.parent / rel) if rel else (pdf.parent / f"{pdf.stem}.tiddlers.json")
    if not tid.is_file():
        return False
    try:
        tiddlers = _json.loads(tid.read_text(encoding="utf-8",
                                             errors="replace"))
    except Exception:
        return False
    crops = pdf.parent / "report-crops"
    need = [t["title"] for t in tiddlers
            if "_EQ" in t.get("title", "")
            and str(t.get("canonical_uri", "")).startswith("http")]
    if not need:
        return True
    return all((crops / f"{t}.jpg").is_file()
               and (crops / f"{t}.jpg").stat().st_size > 500 for t in need)


def network_commands(manifest: dict) -> set:
    """Commands the manifest marks network/paid — DECLARED as dependencies,
    NEVER auto-run: `ensure` names them instead (a dependency that is not in
    the manifest is not a dependency, it is a hope — but a paid step that
    auto-runs is a bill nobody signed)."""
    return {c["name"] for c in manifest.get("commands", [])
            if c.get("network")}


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


def _model_has_translation(model_path: Path) -> bool:
    """Does the model still carry translated prose (a `<field>_source` twin)?

    `translate` writes into the MODEL; `model --force` rebuilds it from
    lines.json, which never held the translation. The TRANSLATED fact and
    `translated_lang` survive in the sidecar, so the document keeps REPORTING as
    translated while showing a single language. Asked of the model, not the
    fact.
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
    for o in it:
        pr = o.get("props") or {}
        for k in pr:
            if k.endswith("_source") and k[:-7] in pr:
                return True
    return False


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


def _tiddlers_current(sc, model_path: Path) -> bool:
    """Is there a tiddler array, and is it NEWER than the model?

    Delegates to `layer_detect.has_tiddlers`, which is the same rule used by
    the rebuild-time retraction. Two implementations of "is this projection
    current" is how they drift apart, and there were already two staleness
    notions in commands.py before this.
    """
    from .layer_detect import has_tiddlers
    blob = getattr(sc, "blob_dir", None)
    if not blob:
        return False
    return has_tiddlers(Path(blob), Path(model_path))


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
    paid = network_commands(load_manifest())
    def _tag(c):
        return f"{c} (paid — run `pdfdrill {c}` yourself)" if c in paid else c
    return (f"`{target}` for {pdf.name} would run, in order:\n  "
            + " → ".join(f"{s}" for s in steps)
            + f"\n  (missing prerequisites: {', '.join(_tag(c) for c in prereqs)}; "
            f"--ensure auto-runs the offline ones and NAMES the paid ones; "
            f"already done: {', '.join(sorted(sat)) or 'none'})")


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
    from .commands import no_paid_steps
    steps, _ = resolve_steps(target, pdf)
    paid = network_commands(load_manifest())
    ran, blocked = [], []
    # 159: refusing the paid STEPS is not enough. `model` is offline in the
    # manifest but calls cmd_mathpix directly when no lines.json exists, so a
    # paid call was reachable through an offline-looking prerequisite — it
    # bought 32 pages for bradley_spring22 during a run meant to spend nothing.
    # The guard wraps the whole prerequisite run, so any depth of auto-chain
    # beneath it refuses too.
    with no_paid_steps():
        for step in steps[:-1]:               # everything except the target
            if step in paid:
                blocked.append(
                    f"{target} requires {step} — run `pdfdrill {step} "
                    f"{pdf.name}` (network/paid; never auto-run)")
                continue
            fn = handlers.get(step)
            if fn is None:
                continue
            out = fn([pdf_arg])
            if out and not quiet:
                print(out)
            ran.append(step)
    for msg in blocked:
        print(f"[ensure] {msg}", file=__import__("sys").stderr)
    return ran
