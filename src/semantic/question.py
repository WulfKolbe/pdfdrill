"""
Question — the reified pass (Process layer, made first-class).

`produced_by` was a bare string ("bib", "ner", "docmodel", …): it named a process
but had no object behind it and no record of *intent*. A `Question` is that
object — the reusable DEFINITION of what a sensor/LLM invocation is FOR (its
description, the prompt/logic version, what entity/relation types it emits, its
fixpoint stratum), decoupled from any single execution (one execution is a
`Transformation`, the next deliverable).

Migration is deliberately non-breaking: `Evidence.produced_by` and
`Relation.produced_by` stay plain strings, but each is now a *reference* to a
`Question.qid`. `get(produced_by)` is the lookup path; the compiler emits an
`info` (never `critical`) warning when a produced_by value has no registered
Question. Every produced_by string currently emitted by the package is
pre-registered below, so nothing regresses.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .entity import EntityType
from .relation import RelationType


@dataclass(frozen=True)
class Question:
    qid: str                                  # stable id; also the produced_by value
    description: str                          # human-readable intent
    prompt_version: str = ""                  # bump when prompt/sensor logic changes
    emits_entities: frozenset = frozenset()   # frozenset[EntityType]
    emits_relations: frozenset = frozenset()  # frozenset[RelationType]
    stratum: int = 0                          # for fixpoint ordering

    def to_dict(self) -> dict[str, Any]:
        return {"qid": self.qid, "description": self.description,
                "prompt_version": self.prompt_version,
                "emits_entities": sorted(t.value for t in self.emits_entities),
                "emits_relations": sorted(t.value for t in self.emits_relations),
                "stratum": self.stratum}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Question":
        return cls(
            qid=d["qid"], description=d.get("description", ""),
            prompt_version=d.get("prompt_version", ""),
            emits_entities=frozenset(EntityType(x) for x in d.get("emits_entities", [])),
            emits_relations=frozenset(RelationType(x) for x in d.get("emits_relations", [])),
            stratum=d.get("stratum", 0))


# --------------------------------------------------------------------------- #
#  Registry
# --------------------------------------------------------------------------- #
REGISTRY: dict[str, Question] = {}


def register(q: Question) -> Question:
    """Register (or replace) a Question by its qid. Returns it."""
    REGISTRY[q.qid] = q
    return q


def get(qid: str) -> Optional[Question]:
    """The Question behind a produced_by value, or None if unregistered."""
    return REGISTRY.get(qid)


def all_questions() -> list[Question]:
    return list(REGISTRY.values())


# --------------------------------------------------------------------------- #
#  Pre-registered passes — one per produced_by string the package emits today.
#  (Keep in sync with build.py / claims.py / concepts.py / content_identity.py.)
# --------------------------------------------------------------------------- #
_E = EntityType
_R = RelationType

for _q in [
    Question("segment", "Partition a bundle into ordered documents and resolve the "
             "sender as the issuing agent.",
             emits_entities=frozenset({_E.DOCUMENT, _E.COMPANY, _E.AUTHORITY}),
             emits_relations=frozenset({_R.ISSUED_BY})),
    Question("ner", "Named-entity recognition over prose: recipient persons / orgs.",
             emits_entities=frozenset({_E.PERSON}),
             emits_relations=frozenset({_R.SENT_TO})),
    Question("iban", "IBAN sensor (mod-97 validated): bank accounts and their owner.",
             emits_entities=frozenset({_E.BANK_ACCOUNT}),
             emits_relations=frozenset({_R.BELONGS_TO, _R.CONTAINS})),
    Question("docmodel", "Ingest the docmodel into the graph: the section/contains "
             "tree, formulas/images/tables/citations/concepts, dual-positioned.",
             emits_entities=frozenset({_E.DOCUMENT, _E.CONCEPT, _E.FORMULA, _E.IMAGE,
                                       _E.TABLE, _E.CITATION}),
             emits_relations=frozenset({_R.CONTAINS, _R.DERIVED_FROM, _R.REFERENCES})),
    Question("bib", "Bibliography entries → Reference/Citation occurrences.",
             emits_entities=frozenset({_E.CITATION}),
             emits_relations=frozenset({_R.REFERENCES})),
    Question("cite", "In-text citation linker → citation occurrences of a reference.",
             emits_entities=frozenset({_E.CITATION}),
             emits_relations=frozenset({_R.REFERENCES, _R.CITES})),
    Question("concepts", "Named-concept layer (acronyms / glossary): define + uses.",
             emits_entities=frozenset({_E.CONCEPT}),
             emits_relations=frozenset({_R.REFERENCES})),
    Question("claims_v1", "Stratum-4 claim/definition sentence extractor → kitems.",
             emits_entities=frozenset({_E.KITEM}),
             emits_relations=frozenset({_R.DERIVED_FROM}),
             stratum=4),
    Question("pdfdrill", "Core pdfdrill extraction: document identity "
             "(doc_id / content_hash) stamping.",
             emits_entities=frozenset({_E.DOCUMENT})),
    Question("mathpix", "MathPix OCR: the rendered LaTeX content of a formula "
             "(the content_identity.resolve_formula default sensor).",
             emits_entities=frozenset({_E.FORMULA, _E.TABLE, _E.IMAGE})),
    Question("bic", "BIC sensor: bank identifier code evidence on an account/agent.",
             emits_entities=frozenset({_E.BANK_ACCOUNT})),
    Question("german_address", "German postal-address sensor (PLZ-anchored).",
             emits_entities=frozenset({_E.COMPANY, _E.PERSON})),
    Question("extract_ids", "German admin-id sensor (Steuer-/Kassen-/Aktenzeichen, …).",
             emits_entities=frozenset({_E.COMPANY, _E.DOCUMENT})),
    # invocation-level questions — one Transformation per ingest call groups the
    # fine-grained sensor evidence/edges above under a single recorded execution.
    Question("ingest_document", "Ingest one commercial document's extractor output "
             "(sender/recipient/IBAN/…) into the graph as one invocation.",
             emits_entities=frozenset({_E.DOCUMENT, _E.COMPANY, _E.PERSON,
                                       _E.BANK_ACCOUNT})),
    Question("ingest_docmodel", "Ingest one scientific docmodel (sections/formulas/"
             "tables/citations/concepts) into the graph as one invocation.",
             emits_entities=frozenset({_E.DOCUMENT, _E.CONCEPT, _E.FORMULA, _E.IMAGE,
                                       _E.TABLE, _E.CITATION})),
    Question("ask", "Chat-proxy Q&A: an LLM answer grounded in retrieved document "
             "units, stored as a kitem with the cited units as evidence.",
             emits_entities=frozenset({_E.KITEM}),
             emits_relations=frozenset({_R.DERIVED_FROM}),
             stratum=5),
]:
    register(_q)
