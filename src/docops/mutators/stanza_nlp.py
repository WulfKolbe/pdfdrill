"""
StanzaNlpMutator.

Enhances prose DocObjects in place with Stanza ("STANTA") NLP annotations:
for every annotatable object (Paragraph, Abstract, Section, ListItem,
Footnote) it projects the object's text to clean prose, runs the Stanza neural
pipeline per sentence, and attaches the result under ``props.nlp``. The raw
source field (``text`` / ``caption`` / ``content``) is left untouched.

Stanza is an optional, heavy dependency, so this mutator is NOT part of the
default docops pipeline; enable it via a config entry (see
``docops/nlp_config.json``). When the library/model is missing it logs and
skips by default (``params.require: true`` turns that into a hard error).

Params (all optional):
  lang        Stanza language code            (default "en")
  processors  Stanza processor list           (default tokenize,mwt,pos,lemma,depparse,ner)
  types       object types to annotate        (default all of TEXT_FIELDS)
  max_page    only annotate props.page <= N   (default: no limit)
  limit       only the first N objects         (default: no limit)
  require     raise instead of skip if Stanza is unavailable (default false)
"""
from __future__ import annotations

from docmodel.core import Document

from ..base import BaseMutator
from ..nlp_stanza import (
    DEFAULT_LANG,
    DEFAULT_PROCESSORS,
    TEXT_FIELDS,
    StanzaAnnotator,
    StanzaUnavailable,
    clean_text,
    object_text,
)


class StanzaNlpMutator(BaseMutator):

    def __init__(self, config, flags=None):
        super().__init__(config, flags)
        self.lang = self.params.get("lang", DEFAULT_LANG)
        self.processors = self.params.get("processors", DEFAULT_PROCESSORS)
        self.types = list(self.params.get("types", list(TEXT_FIELDS)))
        self.max_page = self.params.get("max_page")
        self.limit = self.params.get("limit")
        self.require = bool(self.params.get("require", False))
        # Injectable (tests pass a fake); lazily built on first real use.
        self.annotator = None

    def _ensure_annotator(self):
        if self.annotator is None:
            self.annotator = StanzaAnnotator(self.lang, self.processors)
        return self.annotator

    def _targets(self, doc: Document) -> list:
        objs = [o for t in self.types for o in doc.objects_of_type(t)]
        objs.sort(key=lambda o: (o.props or {}).get("flow_index", 0))
        if self.max_page is not None:
            objs = [o for o in objs if (o.props or {}).get("page", 0) <= self.max_page]
        if self.limit is not None:
            objs = objs[: self.limit]
        return objs

    def apply(self, doc: Document) -> None:
        annotator = self._ensure_annotator()
        targets = self._targets(doc)
        for obj in targets:
            clean = clean_text(object_text(obj))
            try:
                sentences = annotator.annotate(clean)
            except StanzaUnavailable as exc:
                if self.require:
                    raise
                self.log(f"Stanza unavailable; skipping NLP enhancement: {exc}")
                self.bump("skipped_stanza_unavailable")
                return
            obj.props["nlp"] = {
                "engine": "stanza",
                "lang": self.lang,
                "processors": self.processors,
                "clean_text": clean,
                "sentences": sentences,
            }
            self.bump("objects_annotated")
            self.bump(f"annotated_{obj.type}")

        if self.debug:
            self.log(f"counters: {self.counters}")
