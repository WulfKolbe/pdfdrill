# L8 — Ontology / theory level

Status: **mostly planned** (thinnest layer in the repo today) · Tower:
[README](README.md) · Semantics: [TOWER](TOWER.md)

Naming what belongs here clarifies the abstraction target. Four kinds of
content:

## 1. Concept grounding

Linking CONCEPT entities to external vocabularies:

- OntoMathPRO classes and VerbNet senses (the `semdrill` direction — with
  explicit `verbnet=None` for wrong-sense verbs: **grounded *absence* is
  itself a record**);
- research-domain vocabularies (the ORKG research-field/property vocabulary is
  the first implemented instance — see `docops/projectors/scikgtex.py`, which
  projects L7 content into ORKG P-IDs);
- unit/quantity ontologies for numeric facts.

## 2. Theory modules (the MMT/sTeX little-theories shape)

Grouping the concepts a document declares into **scopes-with-imports**:

- the glossary section of paper A *is a theory*;
- "paper B uses paper A's notation" is an **import**;
- "paper B's ⊗ is paper A's ∘" is a **view** (an interpretation map).

This is the *scope structure* whose absence made the raw LaTeX AST useless
(see [L6's negative result](L6-expression-syntax.md)): a symbol is only
meaningful as **(theory, name)**, never as a bare token. First implemented
step: `semantic/stex.py` projects each document's concepts as an sTeX
`smodule` with `\symdecl`/`sdefinition`/`\symref` — one theory per document;
imports and views are open work.

## 3. Document-class schemas (the commercial counterpart of theories)

A schema is a **typed frame whose slots are filled by L7 entities with
evidence**:

- the invoice schema (creditor, IBAN, amount, reference, due date — exactly
  the EPC/GiroCode field set, which is why a QR payload can populate this
  level directly: an L1→L8 edge);
- tax-form schemas, delivery notes;
- the BibTeX-like record `to_bibtex` already projects for commercial documents
  (publisher = sender, the non-standard `receiver` field) is a proto-schema.

## 4. Obligations / affordances

"What do I have to do with this document": EVENT/action entities derived from
filled schemas (a payment obligation with amount, account, deadline). The same
machinery that answers *"give me the Lean-projectable statement of Theorem
3.2"* answers *"prepare the bank transfer"* — both are:

> select an L8 frame, demand its slot fills, and follow grounding down until
> every slot is evidence-backed.

## Native metric

L8 is where Gärdenfors-style **conceptual-space quality dimensions** become
the *intended* metric (the HCSD/CSP program), with everything below supplying
coordinates. See [TOWER — metrics](TOWER.md).

## Open work (≈ everything beyond the seeds named above)

- Theory imports/views across documents (multi-document concept algebra).
- Schema registry + deterministic schema-filling from the L7 graph.
- Obligation derivation (filled invoice frame → payment EVENT).
- OntoMathPRO/VerbNet grounding ingestion.
