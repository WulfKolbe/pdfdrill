"""
vocabnet — one consistent interface over every controlled vocabulary, thesaurus
and classification index feeding pdfdrill (MSC, DLMF, OntoMathPRO, PhySH, ACM
CCS, STW, GND, GermaNet), plus a federation layer that always queries all of
them at once and keeps the misses as signal.

Whatever the native format — SKOS/RDF, OWL Manchester, GermaNet XML, MathPix
Markdown, the MSC JSON — a source compiles to the SAME `Vocabulary` shape and
answers the same queries (lookup/ancestors/siblings/narrower/classify).

The CONVERTERS live here (committed); the downloaded vocabularies are
licence-bound and stay out of git (see `vocab/sources/*/STUB.md` for each
source's download link + build command, and `.gitignore`).
"""
from .vocab import Vocabulary, Concept, Hit
from .federate import Federation, FederatedResult

__all__ = ["Vocabulary", "Concept", "Hit", "Federation", "FederatedResult"]
