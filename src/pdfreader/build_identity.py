"""R6 — WHICH pdfminer PRODUCED THIS OUTPUT.

CR-pdfminer-single-version R6: "pdfdrill outputs should record the same
[as psred's `pdfminer: {version, glyph_identity_patch}`], so every finding
names the build that produced it."

WHY A GIT REVISION IS NOT ENOUGH. Every artefact here already records the
commit that made it (`provenance.identity()`), and that sufficed while the
reader was the only variable. It is not enough now: the reader's answers
depend on a PATCHED pdfminer, applied at install time into a venv or a user
site-packages that git knows nothing about. Two machines on the same commit
can emit different glyph names — which is how ser7 ran 784 for a week while
this machine ran 820, one directory level down.

The failure it prevents is silent. Stock pdfminer answers "what Unicode is
this cid" and drops the entry when it cannot; the fork adds the twin question,
cid -> PostScript glyph name. A machine quietly running STOCK pdfminer still
produces a complete-looking `equations.json` — every `text` present, every
region right — with `glyphname` null throughout. Nothing in the output said
which pdfminer wrote it.

AND ONE BOOLEAN IS NO LONGER ENOUGH EITHER, which is this module's own
finding. psred's `glyph_identity_patch` was a fair summary when the patch did
one thing. The patch has since grown R2 (`glyphname_reliable`) and R3
(`font.spec`, `LTChar.fontsize/scaling/rise`), and the bool cannot see the
difference. Measured on this machine, the two builds side by side:

    live user site-packages   version …d20260930   patch: True
        font.spec False   glyphname_reliable False
    vendor/.pdfmm-venv        version …d20261003   patch: True
        font.spec True    glyphname_reliable True

Both say True. One of them cannot do what R3 and R4 depend on. So the record
carries `glyph_identity_patch` unchanged — psred compares against it, and a
key that quietly changed meaning would be worse than useless — and a
`features` map beside it saying what is actually there.

EVERY QUESTION IS ASKED OF THE LOADED MODULE, not of a file on disk or a
version string: the question is what THIS process is running, and an
installer that exited 0 is not an answer.
"""
from __future__ import annotations

import functools
import hashlib
from pathlib import Path

#: The ONE patch (R1). Named relative to this file so there is no second path
#: convention to drift from.
PATCH = Path(__file__).resolve().parents[2] / "vendor" / "pdfminer-glyph-identity.patch"


def patch_sha256() -> str | None:
    try:
        return hashlib.sha256(PATCH.read_bytes()).hexdigest()
    except OSError:
        return None


def _has_char_text_state() -> bool:
    """R3's `LTChar.fontsize/scaling/rise`. They are set in `__init__`, so the
    class carries no attribute to ask about and the source is the only honest
    source — matched on the ASSIGNMENT, not on the parameter name, which stock
    pdfminer also has."""
    try:
        import inspect

        from pdfminer.layout import LTChar
        src = inspect.getsource(LTChar.__init__)
        return "self.fontsize" in src and "self.scaling" in src
    except Exception:                                        # noqa: BLE001
        return False


def features() -> dict:
    """What the loaded pdfminer can actually do, question by question."""
    out = {"glyph_identity": False, "font_spec": False,
           "char_text_state": False, "glyphname_reliable": False,
           "render_mode": False}
    try:
        from pdfminer.encodingdb import EncodingDB
        out["glyph_identity"] = hasattr(EncodingDB, "get_encoding_names")
    except Exception:                                        # noqa: BLE001
        pass
    try:
        from pdfminer.pdffont import PDFFont
        out["font_spec"] = hasattr(PDFFont, "spec")
    except Exception:                                        # noqa: BLE001
        pass
    try:
        import pdfminer.layout as _L
        out["glyphname_reliable"] = hasattr(_L, "glyphname_reliable")
        import inspect
        out["render_mode"] = "self.render_mode" in inspect.getsource(
            _L.LTChar.__init__)
    except Exception:                                        # noqa: BLE001
        pass
    out["char_text_state"] = _has_char_text_state()
    return out


#: A feature -> the text that proves the patch on disk provides it. Used only
#: to tell a STALE BUILD from an old patch, never to claim a feature exists.
_PATCH_MARKERS = {
    "glyph_identity": "get_encoding_names",
    "font_spec": "spec: Mapping[str, Any] = MappingProxyType",
    "char_text_state": "self.fontsize = fontsize",
    "glyphname_reliable": "def glyphname_reliable",
    "render_mode": "self.render_mode = render_mode",
}


def stale_build(feats: dict | None = None) -> list:
    """Features the PATCH IN THIS TREE provides and the LOADED build does not.

    `patch_sha256` names the patch on disk; the loaded pdfminer was built from
    whatever patch was current when the installer last ran. Those differ the
    moment the patch is edited, and recording the first while describing the
    second is the kind of provenance that is worse than none. Non-empty here
    means: rebuild the fork (`vendor/install-pdfminer-fork.sh --rebuild`) —
    and note that the installer SILENTLY REUSES an existing venv without that
    flag, which is exactly how this drifts.
    """
    feats = features() if feats is None else feats
    try:
        text = PATCH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return sorted(k for k, marker in _PATCH_MARKERS.items()
                  if marker in text and not feats.get(k))


@functools.lru_cache(maxsize=1)
def identity() -> dict:
    """The build record. `version` and `glyph_identity_patch` are psred's keys
    and mean exactly what they mean there, so the two tools' outputs can be
    compared directly."""
    out: dict = {"version": None, "glyph_identity_patch": False,
                 "features": features(),
                 "patch": PATCH.name, "patch_sha256": patch_sha256(),
                 "path": None}
    try:
        import inspect

        import pdfminer
        out["version"] = getattr(pdfminer, "__version__", None)
        out["path"] = str(Path(inspect.getfile(pdfminer)).parent)
    except Exception as e:                                   # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    out["glyph_identity_patch"] = bool(out["features"]["glyph_identity"])
    # Empty unless the patch in this tree is ahead of the installed build.
    out["build_behind_patch"] = stale_build(out["features"])
    return out


def summary() -> str:
    d = identity()
    f = d["features"]
    have = ", ".join(k for k, v in f.items() if v) or "none"
    behind = d.get("build_behind_patch") or []
    note = ("; BUILD BEHIND THE PATCH (missing %s) — rebuild with "
            "vendor/install-pdfminer-fork.sh --rebuild" % ", ".join(behind)) if behind else ""
    return ("pdfminer %s, glyph-identity patch %s [%s], patch %s%s"
            % (d.get("version") or "?",
               "yes" if d["glyph_identity_patch"] else "NO",
               have, (d.get("patch_sha256") or "?")[:12], note))
