"""Sidecar — persistent state file next to the PDF.

paper.pdf → paper.pdf.drill.json  (state, evidence, transitions)
paper.pdf → paper.pdf.drill/      (heavy blobs: md, mmd, layers)

The sidecar is the single source of truth. Every command reads it on entry,
does its work, appends to it, and writes it on exit. Cumulative: states are
facts that accumulate, not a linear sequence.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


VERSION = "0.4.0"


class Sidecar:
    """Read/write the drill.json sidecar for a PDF file."""

    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path).resolve()
        self.json_path = self.pdf_path.parent / f"{self.pdf_path.name}.drill.json"
        self.blob_dir = self.pdf_path.parent / f"{self.pdf_path.name}.drill"
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        if self.json_path.exists():
            self._data = json.loads(self.json_path.read_text(encoding="utf-8"))
        else:
            self._data = {
                "pdf": str(self.pdf_path.name),
                "pdfdrill_version": VERSION,
                "facts": [],
                "evidence": {},
                "pdfinfo": None,
                "bibtex": None,
                "urls": None,
                "dests": None,
                "fonts_layer": None,
                "images_layer": None,
                "pix2tex_results": None,
                "tsv_layer": None,
                "layers": {},
                "transitions": [],
            }

    def save(self):
        self._data["pdfdrill_version"] = VERSION
        self.json_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    # -- Facts (cumulative state) --

    @property
    def facts(self) -> set[str]:
        return set(self._data.get("facts", []))

    def add_fact(self, fact: str):
        facts = self._data.setdefault("facts", [])
        if fact not in facts:
            facts.append(fact)

    def remove_fact(self, fact: str):
        """Clear a fact (e.g. NEEDS_VISION_OCR once equations are folded in).
        No-op if absent. Note: `facts` is a copy, so `.discard()` won't persist —
        use this."""
        facts = self._data.get("facts", [])
        if fact in facts:
            facts.remove(fact)

    def has(self, fact: str) -> bool:
        return fact in self.facts

    # -- Evidence --

    @property
    def evidence(self) -> dict:
        return self._data.setdefault("evidence", {})

    def set_evidence(self, key: str, value: Any):
        self._data.setdefault("evidence", {})[key] = value

    def get_evidence(self, key: str, default=None):
        return self._data.get("evidence", {}).get(key, default)

    # -- Top-level structured layers --

    @property
    def pdfinfo(self) -> dict | None:
        return self._data.get("pdfinfo")

    def set_pdfinfo(self, info: dict):
        self._data["pdfinfo"] = info

    @property
    def bibtex(self) -> dict | None:
        return self._data.get("bibtex")

    def set_bibtex(self, bib: dict):
        self._data["bibtex"] = bib

    @property
    def urls(self) -> list | None:
        return self._data.get("urls")

    def set_urls(self, urls: list):
        self._data["urls"] = urls

    @property
    def dests(self) -> list | None:
        return self._data.get("dests")

    def set_dests(self, dests: list):
        self._data["dests"] = dests

    @property
    def fonts_layer(self) -> list | None:
        return self._data.get("fonts_layer")

    def set_fonts_layer(self, fonts: list):
        self._data["fonts_layer"] = fonts

    @property
    def images_layer(self) -> list | None:
        return self._data.get("images_layer")

    def set_images_layer(self, images: list):
        self._data["images_layer"] = images

    @property
    def pix2tex_results(self) -> list | None:
        return self._data.get("pix2tex_results")

    def set_pix2tex_results(self, results: list):
        self._data["pix2tex_results"] = results

    def append_pix2tex_result(self, result: dict):
        existing = self._data.setdefault("pix2tex_results", []) or []
        existing.append(result)
        self._data["pix2tex_results"] = existing

    @property
    def tsv_layer(self) -> list | None:
        return self._data.get("tsv_layer")

    def set_tsv_layer(self, words: list):
        self._data["tsv_layer"] = words

    # -- Layers (references to blobs) --

    @property
    def layers(self) -> dict:
        return self._data.setdefault("layers", {})

    def set_layer(self, name: str, meta: dict):
        self._data.setdefault("layers", {})[name] = meta

    def get_layer(self, name: str) -> dict | None:
        return self._data.get("layers", {}).get(name)

    # -- Blob storage --

    def write_blob(self, name: str, content: str) -> str:
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        path = self.blob_dir / name
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self.pdf_path.parent))

    def read_blob(self, name: str) -> str | None:
        path = self.blob_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    # -- Transition log --

    def log_transition(self, node: str, from_facts: str, to_fact: str,
                       cost_ms: float = 0, detail: str = ""):
        self._data.setdefault("transitions", []).append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "node": node,
            "from": from_facts,
            "to": to_fact,
            "cost_ms": round(cost_ms, 1),
            "detail": detail,
        })

    @property
    def transitions(self) -> list[dict]:
        return self._data.get("transitions", [])

    @property
    def last_node(self) -> str:
        tr = self.transitions
        return tr[-1]["node"] if tr else "none"

    # -- Convenience --

    @property
    def pdf_exists(self) -> bool:
        return self.pdf_path.exists()

    @property
    def page_count(self) -> int:
        return self.get_evidence("pages", 0)

    @property
    def file_size(self) -> int:
        return self.get_evidence("bytes", 0)
