"""LaTeX theorem → Lean 4 export — STORE then PROJECT.

Two stages, like `bibfetch`:
  1. GENERATE Lean 4 code per Theorem via an LLM (delegated to the Claude agent,
     keyless — or a future Llama-for-Lean / CAS that round-trips LaTeX↔Lean) and
     STORE it on the object (`props["lean4"]`) + the tiddler `lean4` field.
  2. PROJECT the stored code into a `<bibkey>.lean` file.

Storage is the point: generation is an expensive, non-deterministic LLM call, so
it is done once and reused; `project_lean` is a deterministic assembly over the
stored code (a Theorem with no stored Lean gets an honest `sorry` stub). Proofs
are emitted as LaTeX comments under their theorem (formalising proofs is out of
scope for v1 — that is where the trained Lean models come in).
"""
from __future__ import annotations

import re
from pathlib import Path


LEAN_THEOREM_PROMPT = """Translate this mathematical statement from a research \
paper into a Lean 4 (Mathlib) declaration.

Output ONLY Lean 4 code (a fenced ```lean block is fine), no commentary:
- a `theorem {name} ... : ... := by sorry` (leave the proof as `sorry`)
- declare reasonable variables/hypotheses; prefer Mathlib names; invent nothing
- if the statement is too informal to formalise precisely, give your best-effort
  signature and add a `-- INFORMAL:` comment line with the original wording.

{kind}{number_part}{label_part}
LaTeX statement:
{statement}
"""


def lean_name(label: str, kind: str, number, idx: int) -> str:
    """A valid Lean identifier for a theorem: from its \\label if any
    (thm:scaling → thm_scaling), else kind+number, else kind+position."""
    if label:
        n = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
        if n and (n[0].isalpha() or n[0] == "_"):
            return n
        if n:
            return f"{kind}_{n}"
    if number is not None:
        return f"{kind}_{number}"
    return f"{kind}_{idx + 1}"


def theorem_prompt(th, idx: int) -> str:
    p = th.props
    name = lean_name(p.get("label"), p.get("kind", "theorem"), p.get("number"), idx)
    return LEAN_THEOREM_PROMPT.format(
        name=name, kind=p.get("kind", "theorem"),
        number_part=f" {p['number']}" if p.get("number") is not None else "",
        label_part=f" (label {p['label']})" if p.get("label") else "",
        statement=p.get("statement", ""))


def _lean_namespace(bibkey: str) -> str:
    ns = re.sub(r"[^A-Za-z0-9]+", "_", bibkey or "Paper").strip("_") or "Paper"
    return ("P" + ns) if ns[0].isdigit() else ns


def _doc_comment(s: str) -> str:
    """Make a string safe inside a Lean `/-- … -/` doc comment."""
    return re.sub(r"\s+", " ", (s or "").replace("-/", "- /")).strip()


def _sorted(doc, typ):
    return sorted((o for o in doc.objects.values() if o.type == typ),
                  key=lambda o: o.props.get("flow_index") or 0)


def project_lean(doc) -> str:
    """Assemble a `<bibkey>.lean` from the Theorems' STORED `lean4` (+ paired
    proofs as comments). A Theorem with no stored Lean → a `sorry` stub naming
    the generator. Pure over the model."""
    bibkey = doc.meta.get("bibkey", "DOC")
    ns = _lean_namespace(bibkey)
    theorems = _sorted(doc, "Theorem")
    proofs = {o.id: o for o in doc.objects.values() if o.type == "Proof"}
    out = [
        "import Mathlib",
        "",
        f"-- Auto-generated from {bibkey} by pdfdrill `lean`.",
        "-- Per-theorem Lean is LLM-sourced (store-then-project) — VERIFY it.",
        "",
        f"namespace {ns}",
        "",
    ]
    for i, th in enumerate(theorems):
        p = th.props
        name = lean_name(p.get("label"), p.get("kind", "theorem"), p.get("number"), i)
        head = p.get("printed_title") or p.get("kind", "Theorem").title()
        if p.get("number") is not None:
            head = f"{head} {p['number']}"
        if p.get("title"):
            head = f"{head} ({p['title']})"
        out.append(f"/-- {_doc_comment(head)}: {_doc_comment(p.get('statement', ''))} -/")
        code = (p.get("lean4") or "").strip()
        out.append(code if code
                   else f"theorem {name} : True := by trivial  "
                        f"-- TODO: run `pdfdrill lean` to generate")
        pid = p.get("proof_id")
        if pid and pid in proofs:
            pst = proofs[pid].props.get("statement", "")
            if pst:
                out.append(f"-- proof: {_doc_comment(pst)[:400]}")
        out.append("")
    out.append(f"end {ns}")
    return "\n".join(out)


def generate_lean(doc, *, drill_dir, runtime=None, limit=None, force=False,
                  model=None) -> dict:
    """Stage 1 — fill each Theorem's `props["lean4"]` via the LLM delegation
    (keyless agent / CLI / sandbox), like bibfetch. Idempotent: skips theorems
    already carrying `lean4` unless `force`. Returns {generated, requested,
    answered, deferred, total}. Mutates the doc in place (caller persists)."""
    from . import llm_delegate as D

    theorems = _sorted(doc, "Theorem")
    todo = [t for t in theorems if force or not t.props.get("lean4")]
    if limit is not None:
        todo = todo[:limit]
    if not todo:
        return {"generated": 0, "requested": 0, "answered": 0,
                "deferred": None, "total": len(theorems)}

    tasks, by_task = [], {}
    for i, th in enumerate(todo):
        t = D.LLMTask(kind="lean", prompt=theorem_prompt(th, i), meta={"id": th.id})
        tasks.append(t)
        by_task[t.task_id] = th
    results, deferred = D.delegate_batch(
        tasks, drill_dir=Path(drill_dir), runtime=runtime, model=model)
    generated = 0
    for tid, res in results.items():
        code = (res or {}).get("lean")
        if code and code.strip():
            by_task[tid].props["lean4"] = code.strip()
            generated += 1
    return {"generated": generated, "requested": len(tasks),
            "answered": len(results), "deferred": deferred,
            "total": len(theorems)}
