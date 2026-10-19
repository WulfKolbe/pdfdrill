r"""YOLO page layout: the boxes the model lane could not measure from ink.

WHY THE LANE NEEDS A DETECTOR AT ALL
------------------------------------
The model returns no coordinates, so every box in this lane is measured from
the page's own ink and assigned BY ORDER — a monotone matching of printed
items against printed ink rows. That works for prose, where one item is one
row, and it fails for everything that is not prose, because the failure is not
inaccuracy but ambiguity:

    a display formula is several ink rows and ONE item (or one ink block and
    several `$$` items, when the model writes the rows of a system
    separately), so the matching has to guess how many rows to take;
    a figure is a large connected mass of ink belonging to NO item, and the
    matching, which must consume rows monotonically, hands it to whatever
    item is passing;
    an equation number shares its row with the formula it numbers.

MEASURED on penev_A, with the ink alignment alone: 5 of 116 display formulas
and 3 of 116 equation numbers found a box at IoU >= 0.5. With the detector's
boxes used as ANCHORS the same reading gives 110 and 112. That is not a
tuning difference; it is the difference between guessing a formula's extent
and being told it.

The detector supplies three things the ink cannot:

    isolate_formula / isolated  -> a display formula's box, used as an ANCHOR:
        the items between two anchors are aligned to the ink rows of that band
        only, so a drift on a dense page cannot cross a formula.
    formula_caption             -> the equation number's box.
    figure / table              -> ink that belongs to no printed line, so it
        is WHITENED before the paid read (the model stops transcribing a
        picture) and claimed by a `diagram` line afterwards, so a figure's
        strokes never join a text line's box.

WHY IT RUNS IN ANOTHER INTERPRETER
----------------------------------
The detectors are torch. pdfdrill's own environment is poppler, pdfplumber and
numpy, and a 2 GB torch dependency in it would be paid for by every user of
every command. So this is an EXTERNAL TOOL, wrapped the way poppler and
ghostscript are wrapped: a configured interpreter, a cached artefact beside
the document, and a typed refusal when it is absent. `pdfdrill doctor` reports
it like any other tool.

OFFLINE. The weights come from the local Hugging Face cache and `detect` will
not download them; `allow_download=True` is the explicit opt-in. pdfdrill
routes every network call through `net.urlopen` so a blocked host raises a
typed, host-named error, and a subprocess fetching weights silently would be
the one call that escaped it.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

#: Where the interpreter of the detector environment is looked for, in order.
#: The env var wins so a machine can say it once; the rest are the layouts a
#: torch venv is actually found in beside this project.
INTERPRETER_ENV = "PDFDRILL_YOLO_PYTHON"
INTERPRETER_CANDIDATES = (
    "~/Gemma4/.venv-yolo/bin/python",
    "~/.venv-yolo/bin/python",
    "~/MX/PDFDRILL/.venv-yolo/bin/python",
)

#: Classes that mark ink belonging to no printed line. Whitened before the
#: paid read and claimed by a container afterwards.
FIGURE_CLASSES = ("figure", "table")

#: Display-formula classes, in the two detectors' vocabularies.
DISPLAY_LAYOUT = "isolate_formula"
DISPLAY_MFD = "isolated"
#: The layout model's name for an equation number.
EQNUM_CLASS = "formula_caption"
#: The MFD weights call an inline formula "embedding"; newer ones say "inline".
INLINE_CLASSES = ("embedding", "inline")

Box = tuple[float, float, float, float]


@dataclass
class Det:
    model: str
    cls: str
    conf: float
    box: Box

    @property
    def area(self) -> float:
        return max(0.0, self.box[2] - self.box[0]) * max(
            0.0, self.box[3] - self.box[1])


# --------------------------------------------------------------------------- #
#  Availability
# --------------------------------------------------------------------------- #

def interpreter() -> Optional[str]:
    """The detector environment's python, or None."""
    env = os.environ.get(INTERPRETER_ENV, "").strip()
    if env:
        p = Path(env).expanduser()
        return str(p) if p.is_file() and os.access(p, os.X_OK) else None
    for cand in INTERPRETER_CANDIDATES:
        p = Path(cand).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def weights_cached() -> bool:
    """True when both weight files are already in the Hugging Face cache.

    Asked separately from `interpreter()` because the two fail differently:
    no interpreter is "this machine has no detector", no weights is "it has
    one and it would have to download 300 MB first".
    """
    from .yolo_driver import LAYOUT_FILE, MFD_FILE
    root = Path(os.environ.get("HF_HOME", "~/.cache/huggingface")
                ).expanduser() / "hub"
    if not root.is_dir():
        return False
    want = {Path(LAYOUT_FILE).name, Path(MFD_FILE).name}
    found: set[str] = set()
    for p in root.rglob("*.pt"):
        if p.name in want:
            found.add(p.name)
    return found == want


def available() -> bool:
    return interpreter() is not None and weights_cached()


def describe() -> str:
    """One line for `doctor`."""
    py = interpreter()
    if py is None:
        return (f"no detector interpreter (set {INTERPRETER_ENV} to the python "
                f"of an environment with torch + doclayout-yolo + ultralytics)")
    if not weights_cached():
        return f"{py} — but the weights are not in the local cache"
    return f"{py} — weights cached"


class DetectorMissing(RuntimeError):
    """Raised, with the reason named, instead of running without boxes."""


# --------------------------------------------------------------------------- #
#  Running it
# --------------------------------------------------------------------------- #

def expected_tsv(out_dir: Path, png: Path) -> Path:
    return Path(out_dir) / f"{Path(png).stem}.yolo.tsv"


def detect(images: Sequence[Path], out_dir: Path, *, force: bool = False,
           allow_download: bool = False, batch: int = 24,
           timeout: int = 3600) -> dict:
    """Run the detector over `images`, caching one TSV per image.

    IDEMPOTENT: an image whose TSV is already on disk is not run again, which
    matters because this is minutes of CPU per document and a lane that
    re-runs it on every assemble is a lane nobody waits for. Returns
    `{"status", "ran", "cached", "out_dir"}`.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [p for p in images
            if force or not expected_tsv(out_dir, p).is_file()]
    cached = len(images) - len(todo)
    if not todo:
        return {"status": "cached", "ran": 0, "cached": cached,
                "out_dir": str(out_dir)}

    py = interpreter()
    if py is None:
        raise DetectorMissing(
            f"page layout detection needs a separate interpreter: "
            f"{describe()}")
    if not allow_download and not weights_cached():
        raise DetectorMissing(
            "the layout weights are not in the local Hugging Face cache. "
            "Pass allow_download=True (pdfdrill yololayout --allow-download) "
            "to fetch them once; pdfdrill does not download them silently.")

    driver = Path(__file__).with_name("yolo_driver.py")
    ran = 0
    for i in range(0, len(todo), max(1, batch)):
        chunk = todo[i:i + max(1, batch)]
        cmd = [py, str(driver), str(out_dir)] + [str(p) for p in chunk]
        if allow_download:
            cmd.append("--allow-download")
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()
            why = tail[-1] if tail else "no output on stderr"
            raise DetectorMissing(
                f"page layout detection failed (exit {proc.returncode}): {why}")
        ran += len(chunk)
    return {"status": "ran", "ran": ran, "cached": cached,
            "out_dir": str(out_dir)}


def load(path: Path) -> list[Det]:
    """One image's detections. A missing TSV is an empty list and not an
    error: a lane that works WITHOUT the detector must keep working, just with
    the boxes it can measure from ink."""
    path = Path(path)
    if not path.is_file():
        return []
    out: list[Det] = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if n == 0 or not raw.strip():
            continue
        parts = raw.split("\t")
        if len(parts) < 7:
            continue
        try:
            out.append(Det(parts[0], parts[1], float(parts[2]),
                           (float(parts[3]), float(parts[4]),
                            float(parts[5]), float(parts[6]))))
        except ValueError:
            continue
    return out


def load_for(out_dir: Path, png: Path) -> list[Det]:
    return load(expected_tsv(out_dir, png))


# --------------------------------------------------------------------------- #
#  The three things the aligner asks for
# --------------------------------------------------------------------------- #

def _iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / u if u > 0 else 0.0


def _inside_share(a: Box, b: Box) -> float:
    """Share of a's area that lies inside b."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    ar = (a[2] - a[0]) * (a[3] - a[1])
    return (ix * iy / ar) if ar > 0 else 0.0


def display_boxes(dets: Iterable[Det]) -> list[Box]:
    """Display-formula boxes, top to bottom, the two detectors reconciled.

    The layout box is kept where both found the same formula. An MFD box that
    repeats a layout box, or is a PIECE of one — one column of a formula
    block, one line of a system — is not a formula of its own, and letting it
    through would give the alignment two anchors for one printed object and
    guarantee one of them is wrong.
    """
    dets = list(dets)
    lay = [d.box for d in dets
           if d.model == "layout" and d.cls == DISPLAY_LAYOUT]
    mfd = [d.box for d in dets if d.model == "mfd" and d.cls == DISPLAY_MFD]
    extra = [m for m in mfd
             if all(_iou(m, l) < 0.3 and _inside_share(m, l) < 0.6
                    for l in lay)]
    return sorted(lay + extra, key=lambda b: b[1])


def eqnum_boxes(dets: Iterable[Det]) -> list[Box]:
    return sorted((d.box for d in dets
                   if d.model == "layout" and d.cls == EQNUM_CLASS),
                  key=lambda b: b[1])


def inline_boxes(dets: Iterable[Det]) -> list[Box]:
    return sorted((d.box for d in dets
                   if d.model == "mfd" and d.cls in INLINE_CLASSES),
                  key=lambda b: (b[1], b[0]))


def figure_boxes(dets: Iterable[Det], *, classes: Sequence[str] = FIGURE_CLASSES
                 ) -> list[Box]:
    """Figure and table boxes, largest first so a nested one is seen second."""
    return sorted((d.box for d in dets
                   if d.model == "layout" and d.cls in classes),
                  key=lambda b: -((b[2] - b[0]) * (b[3] - b[1])))


def caption_boxes(dets: Iterable[Det]) -> list[Box]:
    return sorted((d.box for d in dets
                   if d.model == "layout"
                   and d.cls in ("figure_caption", "table_caption")),
                  key=lambda b: b[1])


def abandon_boxes(dets: Iterable[Det]) -> list[Box]:
    """Running heads and folios — what the layout model calls `abandon`."""
    return sorted((d.box for d in dets
                   if d.model == "layout" and d.cls == "abandon"),
                  key=lambda b: b[1])


def whiten(png: Path, boxes: Sequence[Box], dst: Path, *,
           pad: int = 2) -> Path:
    """Fill `boxes` with paper white and write the result to `dst`.

    Done BEFORE the paid read, for two separate reasons. The model stops
    trying to transcribe a picture — which it does at length, inventing axis
    labels and tick values that are not printed anywhere — and the ink
    alignment afterwards sees no figure strokes to hand to a passing text
    line. A figure that is whitened is also a figure the model mentions once,
    as a description, which is what `diagram`'s `description` field is for.
    """
    from PIL import Image, ImageDraw
    with Image.open(png) as im:
        img = im.convert("L")
        draw = ImageDraw.Draw(img)
        for x0, y0, x1, y1 in boxes:
            draw.rectangle([x0 - pad, y0 - pad, x1 + pad, y1 + pad], fill=255)
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        img.save(dst)
    return Path(dst)
