"""
LLM-facing rendering of the semantic graph.

The consumer of `pdfdrill semantic` is an LLM, not a human. So the output is:
  * structured  — ENTITIES / RELATIONS / MARGIN MARKERS / WARNINGS sections;
  * complete    — the whole graph, not a truncated teaser (the LLM decides what
                  matters); only scan-noise margin fragments are dropped;
  * clean       — no human narration, no philosophy;
  * grounded    — every fact carries its source docs (⟵), and a pointer to the
                  JSON gives per-fact evidence/provenance/confidence.
"""
from __future__ import annotations

from typing import Any

from .entity import EntityType
from .geometry_columns import is_substantive_marker
from . import proof

_AGENT = {EntityType.COMPANY, EntityType.AUTHORITY, EntityType.PERSON,
          EntityType.BANK, EntityType.ORGANIZATION, EntityType.DEPARTMENT}
# evidence props worth inlining per entity (others live in the JSON)
_KEY_PROPS = ("iban", "bic", "address", "steuernummer", "kassenzeichen",
              "aktenzeichen", "customer_number", "blz", "konto")


def _clip(s: str, n: int = 48) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _w(warning: Any, attr: str) -> str:
    return warning.get(attr, "") if isinstance(warning, dict) else getattr(warning, attr, "")


def _entity_line(e) -> str:
    props = e.properties()
    shown = [k for k in _KEY_PROPS if k in props]
    shown += [k for k in props if k.startswith("margin_") and k not in shown]
    facts = "; ".join(f"{k}={_clip(props[k], 40)}" for k in shown)
    srcs = ",".join(sorted(proof.sources(e)))
    return (f'  {e.id} "{_clip(e.value)}"' + (f" · {facts}" if facts else "")
            + (f"  ⟵{srcs}" if srcs else ""))


def render_for_llm(graph, *, bibkey: str, validity: str, warnings: list,
                   markers: list, json_name: str, n_docs: int = 1,
                   store_note: str = "", language: str = "") -> str:
    ents = list(graph.entities.values())
    agents = [e for e in ents if e.type in _AGENT]
    accounts = [e for e in ents if e.type == EntityType.BANK_ACCOUNT]
    docs = [e for e in ents if e.type in (EntityType.DOCUMENT, EntityType.PAPER)]
    others = [e for e in ents if e.type not in _AGENT
              and e.type not in (EntityType.BANK_ACCOUNT, EntityType.DOCUMENT, EntityType.PAPER)]

    lang_note = f" · lang={language}" if language else ""
    out = [f"SEMANTIC GRAPH {bibkey} · validity={validity}{lang_note} · {n_docs} doc(s) · "
           f"{len(ents)} entities · {len(graph.relations)} relations{store_note}",
           f"full graph + per-fact evidence/provenance: {json_name}", "", "ENTITIES"]
    for e in agents + accounts + others:
        out.append(_entity_line(e))
    if docs:
        ids = ", ".join(d.id for d in docs[:12]) + (" …" if len(docs) > 12 else "")
        out.append(f"  documents: {len(docs)} ({ids})")

    out += ["", "RELATIONS"]
    if graph.relations:
        for r in graph.relations[:120]:
            s, o = graph.get(r.subject_id), graph.get(r.object_id)
            sv = f' "{_clip(s.value, 28)}"' if s else ""
            ov = f' "{_clip(o.value, 28)}"' if o else ""
            conf = f"  (conf {r.confidence:.2f})" if r.confidence < 1.0 else ""
            out.append(f"  {r.subject_id}{sv} —{r.predicate.value}→ {r.object_id}{ov}{conf}")
        if len(graph.relations) > 120:
            out.append(f"  … +{len(graph.relations) - 120} more (see JSON)")
    else:
        out.append("  (none)")

    # margin markers: drop scan noise; show substantive out-of-column confirmation
    keep = [m for m in markers if is_substantive_marker(m.get("text", ""), m.get("role"))]
    suppressed = len(markers) - len(keep)
    out += ["", "MARGIN MARKERS (out-of-column geometry; confirmation, not body text)"]
    if keep:
        for m in keep[:25]:
            out.append(f'  p{m["page"]} {m["role"]} [{m["side"]}] "{_clip(m["text"], 40)}"')
        if len(keep) > 25:
            out.append(f"  … +{len(keep) - 25} more (see JSON)")
    if suppressed:
        out.append(f"  ({suppressed} low-content margin fragment(s) suppressed)")
    if not keep and not suppressed:
        out.append("  (none)")

    out += ["", "WARNINGS"]
    if warnings:
        for w in warnings[:20]:
            out.append(f"  [{_w(w, 'severity')}/{_w(w, 'code')}] {_w(w, 'message')}")
    else:
        out.append("  none")
    return "\n".join(out)
