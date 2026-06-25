"""docOS — a document-set operating system over pdfdrill.

A working SET of documents managed like a Unix shell (`cd`, glob `add`/`remove`),
with a strict materialization ladder L0→L1→L1.5→L2→L3→L4. Each layer demands the
lower ones be materialized for the set; higher commands auto-build what's missing
(the set-level form of pdfdrill's prerequisite state machine). State persists to
disk so the shell is stateful across invocations.

Step 1 (this module) implements **L0** — the selector — fully, plus the compact
state UI with level-gated command listing. L1+ verbs are recognised and report
as planned (wired in later steps), so the shell skeleton is complete and honest.
"""
from __future__ import annotations

import fnmatch
import glob as _glob
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

# the materialization ladder, in order
LEVELS = ["L0", "L1", "L1.5", "L2", "L3", "L4"]
_DOC_EXTS = (".pdf", ".md")

# representations per layer (docOS `make <repr>`)
L1_REPRS = ("md", "toc", "math", "figures", "refs")
L15_REPRS = ("abstract", "conclusion", "claims", "contributions")
_ALL_REPRS = L1_REPRS + L15_REPRS


def state_path() -> Path:
    env = os.environ.get("PDFDRILL_DOCOS_STATE")
    if env:
        return Path(env).expanduser()
    from . import config
    return config.config_path().parent / "docos.json"


@dataclass
class DocosState:
    folder: str = ""
    documents: list = field(default_factory=list)      # absolute doc paths
    saved_sets: dict = field(default_factory=dict)      # name -> {folder, documents}
    level: str = "L0"                                   # highest materialized
    materialized: dict = field(default_factory=dict)    # per-doc layer flags (later)

    def __post_init__(self):
        if not self.folder:
            try:
                from . import config
                self.folder = str(config.download_dir())
            except Exception:
                self.folder = os.getcwd()

    # ----- L0 selector operations -----
    def cd(self, path: str) -> str:
        p = os.path.expanduser(path)
        if not os.path.isabs(p):
            p = os.path.join(self.folder, p)
        p = os.path.abspath(p)
        if not os.path.isdir(p):
            raise NotADirectoryError(f"not a folder: {path}")
        self.folder = p
        return p

    def _expand(self, pattern: str) -> list:
        p = os.path.expanduser(pattern)
        if not os.path.isabs(p):
            p = os.path.join(self.folder, p)
        out = []
        for h in _glob.glob(p, recursive=True):
            if os.path.isdir(h):                         # a dir → its PDFs
                out += _glob.glob(os.path.join(h, "*.pdf"))
            else:
                out.append(h)
        return [os.path.abspath(x) for x in out
                if x.lower().endswith(_DOC_EXTS)]

    def add(self, pattern: str) -> int:
        have = set(self.documents)
        added = 0
        for m in self._expand(pattern):
            if m not in have:
                self.documents.append(m)
                have.add(m)
                added += 1
        return added

    def remove(self, pattern: str) -> int:
        pat = os.path.expanduser(pattern)

        def match(m: str) -> bool:
            return (fnmatch.fnmatch(m, pat)
                    or fnmatch.fnmatch(os.path.basename(m), pattern))
        before = len(self.documents)
        self.documents = [m for m in self.documents if not match(m)]
        return before - len(self.documents)

    def clear(self) -> None:
        self.documents = []
        self.level = "L0"

    def save_set(self, name: str) -> None:
        self.saved_sets[name] = {"folder": self.folder,
                                 "documents": list(self.documents)}

    def load_set(self, name: str) -> None:
        if name not in self.saved_sets:
            raise KeyError(name)
        rec = self.saved_sets[name]
        self.folder = rec.get("folder", self.folder)
        self.documents = list(rec.get("documents", []))
        self.level = "L0"                               # load demotes (spec)
        self.materialized = {}

    def sets(self) -> list:
        return sorted(self.saved_sets)

    def show(self) -> str:
        n = len(self.documents)
        ex = ", ".join(os.path.basename(p) for p in self.documents[:5])
        more = f" … (+{n - 5})" if n > 5 else ""
        return (f"Set: {n} document(s) in {self.folder}\n"
                + (f"  e.g. {ex}{more}" if n else "  (empty — `add <glob>`)")
                + (f"\n  saved sets: {', '.join(self.sets())}" if self.saved_sets else ""))


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def load_state() -> DocosState:
    p = state_path()
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return DocosState(**{k: d.get(k) for k in
                                 ("folder", "documents", "saved_sets",
                                  "level", "materialized") if d.get(k) is not None})
        except Exception:
            pass
    return DocosState()


def save_state(state: DocosState) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# L1 / L1.5 fan-out — run a per-doc representation over the whole set
# --------------------------------------------------------------------------- #
def _ensure_model(pdf) -> None:
    from . import commands as K
    from .sidecar import Sidecar
    sc = Sidecar(pdf)
    mp = K._model_path(sc)
    if K._stale_or_absent(sc, mp, K._lines_json_path(pdf)):
        K.cmd_model(pdf)


_CLAIM_CUES = (r"we find that", r"we show that", r"we demonstrate", r"we observe",
               r"our results? (?:show|indicate|demonstrate)",
               r"results? (?:show|indicate|demonstrate)",
               r"\boutperform", r"\bachieve[sd]?\b")
_CONTRIB_CUES = (r"we propose", r"we introduce", r"we present", r"we contribute",
                 r"we develop", r"our (?:main |key )?contribution",
                 r"in this (?:paper|work),? we")


def _cue_sentences(pdf, cues, key: str) -> int:
    """Materialize cue-matched sentences (claims/contributions) from the model's
    prose into the sidecar; returns the count. Builds the model if missing."""
    import re as _re
    from . import commands as K, model_io
    from .sidecar import Sidecar
    _ensure_model(pdf)
    sc = Sidecar(pdf)
    g = model_io.load_docgraph(K._model_path(sc))
    rx = _re.compile("|".join(cues), _re.I)
    hits = []
    for n in g:
        if getattr(n, "type", None) != "Paragraph":
            continue
        for s in _re.split(r"(?<=[.!?])\s+", (n.props.get("text") or "")):
            s = s.strip()
            if s and rx.search(s):
                hits.append(s)
    sc.set_evidence(f"docos_{key}", hits)
    sc.save()
    return len(hits)


def _run_make(repr_name: str, path: str) -> tuple[str, str]:
    """Materialize one representation for one document. Returns (status, detail),
    status ∈ ok|err|na. Each per-doc command auto-builds its own model."""
    from pathlib import Path
    from . import commands as K
    p = Path(path)
    try:
        if repr_name == "md":
            K.cmd_md(p)
        elif repr_name == "toc":
            K.cmd_booktoc(p)
        elif repr_name == "math":
            K.cmd_mathir(p)
        elif repr_name == "figures":
            K.cmd_embedimages(p)
        elif repr_name == "refs":
            K.cmd_bibsource(p)
        elif repr_name == "abstract":
            K.cmd_abstract(p)
        elif repr_name == "conclusion":
            K.cmd_conclusion(p)
        elif repr_name == "claims":
            return ("ok", f"{_cue_sentences(p, _CLAIM_CUES, 'claims')} claims")
        elif repr_name == "contributions":
            return ("ok", f"{_cue_sentences(p, _CONTRIB_CUES, 'contributions')} contrib")
        else:
            return ("na", "unknown representation")
        return ("ok", "")
    except Exception as e:                              # noqa: BLE001
        return ("err", str(e).splitlines()[0][:80] if str(e).strip() else type(e).__name__)


def _recompute_level(state: "DocosState") -> None:
    if not state.documents:
        state.level = "L0"
        return
    docs = state.documents

    def all_ok(r):
        return all(state.materialized.get(d, {}).get(r) == "ok" for d in docs)
    if all(all_ok(r) for r in L15_REPRS):
        state.level = "L1.5"
    elif any(state.materialized.get(d, {}).get(r) == "ok"
             for d in docs for r in _ALL_REPRS):
        state.level = "L1"
    else:
        state.level = "L0"


def make(state: "DocosState", repr_name: str, runner=None) -> dict:
    """Fan a representation out over the whole set; record per-doc status; update
    the materialized level. `runner(repr, path)->(status,detail)` is injectable."""
    run = runner or _run_make
    res = {"ok": 0, "err": 0, "na": 0, "details": []}
    for doc in state.documents:
        st, detail = run(repr_name, doc)
        res[st] = res.get(st, 0) + 1
        state.materialized.setdefault(doc, {})[repr_name] = st
        if detail:
            res["details"].append((os.path.basename(doc), detail))
    _recompute_level(state)
    return res


def status(state: "DocosState") -> str:
    docs = state.documents
    n = len(docs)
    lines = [f"representations (ok/{n}):"]
    for r in _ALL_REPRS:
        c = sum(1 for d in docs if state.materialized.get(d, {}).get(r) == "ok")
        layer = "L1.5" if r in L15_REPRS else "L1  "
        lines.append(f"  [{layer}] {r:13s} {c}/{n}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Compact UI (level-gated command listing)
# --------------------------------------------------------------------------- #
def _mat_index(state: DocosState) -> int:
    """Index in LEVELS of the highest materialized level (L0 once a set exists)."""
    if not state.documents:
        return -1
    try:
        return LEVELS.index(state.level)
    except ValueError:
        return 0


def render_ui(state: DocosState) -> str:
    mi = _mat_index(state)
    hi = state.level if state.documents else "—"
    lines = [
        f"Folder: {state.folder}",
        f"Set: {len(state.documents)} documents | Highest materialized: {hi}",
        "Available commands:",
        "  L0 Select: cd, add, remove, clear, save-set, load-set, sets, show",
    ]

    # (label, requires-index, command list)  — requires-index into LEVELS
    rows = [
        ("L1 Represent", LEVELS.index("L0"), "make md|toc|math|figures|refs, status"),
        ("L1.5 Summary", LEVELS.index("L0"), "make abstract|conclusion|claims|contributions"),
        ("L2 Extract", LEVELS.index("L1.5"), "extract entities|methods|claims|datasets|equations"),
        ("L3 Ensemble", LEVELS.index("L2"), "ensemble build|stats|topics|graph|search|compare"),
        ("L4 Synthesis", LEVELS.index("L3"), "synthesize review|survey|timeline|relatedwork, compile latex"),
    ]
    for label, need, cmds in rows:
        if mi >= need:
            lines.append(f"  {label}: {cmds}")
        else:
            lines.append(f"  {label}: {cmds}   [requires {LEVELS[need]}]")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Dispatch (one command line → message + new state)
# --------------------------------------------------------------------------- #
_L0_VERBS = {"cd", "add", "remove", "clear", "save-set", "load-set", "sets", "show"}
_PLANNED_VERBS = {"extract", "ensemble", "synthesize", "compile"}


def dispatch(state: DocosState, line: str) -> tuple[str, DocosState]:
    parts = line.strip().split()
    if not parts:
        return "", state
    verb, args = parts[0], parts[1:]
    arg = " ".join(args)
    try:
        if verb == "cd":
            return f"folder → {state.cd(arg)}", state
        if verb == "add":
            return f"added {state.add(arg)} document(s) ({len(state.documents)} total)", state
        if verb == "remove":
            return f"removed {state.remove(arg)} document(s) ({len(state.documents)} total)", state
        if verb == "clear":
            state.clear(); return "set cleared", state
        if verb == "save-set":
            state.save_set(arg); return f"saved set '{arg}'", state
        if verb == "load-set":
            state.load_set(arg); return f"loaded set '{arg}' ({len(state.documents)} docs); level → L0", state
        if verb == "sets":
            return ("saved sets: " + (", ".join(state.sets()) or "(none)")), state
        if verb == "show":
            return state.show(), state
        if verb == "make":
            if not args:
                return ("usage: make " + "|".join(_ALL_REPRS)), state
            r = args[0]
            if r not in _ALL_REPRS:
                return f"unknown representation: {r}", state
            if not state.documents:
                return "empty set — `add <glob>` first", state
            res = make(state, r)
            msg = (f"make {r}: {res['ok']} ok, {res['err']} err, {res['na']} n/a "
                   f"(level → {state.level})")
            if res["details"][:3]:
                msg += "\n  " + "; ".join(f"{n}: {d}" for n, d in res["details"][:3])
            return msg, state
        if verb == "status":
            if not state.documents:
                return "empty set — `add <glob>` first", state
            return status(state), state
    except Exception as e:                              # noqa: BLE001
        return f"error: {e}", state

    if verb in _PLANNED_VERBS:
        return (f"`{line}` is planned — docOS L1+ materialization is wired in a "
                f"later step; L0 selector commands are live now."), state
    return f"unknown command: {verb}", state
