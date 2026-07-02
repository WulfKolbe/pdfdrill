"""
CAL.* — the calibration seed (S6.3): per-producer precision estimates from
verdict feedback, gating as a Readout.

The loop: `pdfdrill chatlog --verdict correct|wrong` records how a producer's
past answers judged out; `CAL.PRECISION.WILSON` turns the (correct, total)
tally into a Wilson-score LOWER bound — the humble estimate (1/1 is not "100%",
it is "we barely know"); `CAL.GATE` (implemented AS an aggregate Readout, so it
inherits the monotone property discipline) thresholds an answer part's
calibrated component — `ask --precision p` prefers this gate when tallies
exist and falls back to the span-status gate otherwise (A4).

Storage: tallies persist as Evidence rows (prop="verdict") on a CONCEPT entity
of subtype `question-record`, keyed content_hash("qrec|"+qid) — the smallest
footprint, no new EntityType.
"""
from __future__ import annotations

import math
from typing import Optional

from .entity import EntityType
from .evidence import Evidence
from .aggregate import Threshold
from .registry import FnSpec, register_fn
from .layers.content_identity import content_hash


def wilson_lower(correct: int, total: int, z: float = 1.96) -> Optional[float]:
    """The Wilson score interval's LOWER bound — the humble precision estimate
    (small samples stay far from their raw rate). None with no data."""
    if total <= 0:
        return None
    phat = correct / total
    denom = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    return (centre - margin) / denom


def _qrec_entity(graph, resolver, qid: str):
    h = content_hash("qrec|" + qid)
    e = resolver.find_existing_entity(EntityType.CONCEPT, [("content_hash", h)])
    if e is None:
        e = resolver.resolve(EntityType.CONCEPT, keys=[("content_hash", h)],
                             evidence=[Evidence("calibration", "content_hash",
                                                h, "calibration", confidence=1.0),
                                       Evidence("calibration", "name",
                                                f"question-record:{qid}",
                                                "calibration")])
        e.subtype = "question-record"
    return e


def record_verdict(graph, resolver, qid: str, correct: bool) -> None:
    """Append one verdict to the producer's tally (an Evidence row on its
    question-record entity)."""
    e = _qrec_entity(graph, resolver, qid)
    e.evidence.append(Evidence("calibration", "verdict",
                               "correct" if correct else "wrong", qid))


def tally(graph, qid: str) -> tuple[int, int]:
    """(correct, total) verdicts recorded for a producer. (0, 0) when none."""
    h = content_hash("qrec|" + qid)
    for e in graph.entities.values():
        if e.type == EntityType.CONCEPT and e.subtype == "question-record" and \
                any(ev.prop == "content_hash" and ev.value == h
                    for ev in e.evidence):
            verdicts = [ev.value for ev in e.evidence if ev.prop == "verdict"]
            return sum(1 for v in verdicts if v == "correct"), len(verdicts)
    return 0, 0


def precision_estimate(graph, qid: str) -> Optional[float]:
    """The producer's calibrated precision (Wilson lower bound), or None when
    no tally exists — grounded absence, the caller falls back to span-status."""
    correct, total = tally(graph, qid)
    return wilson_lower(correct, total)


class CalGate(Threshold):
    """CAL.GATE — the precision gate AS a Readout (A4): a part's calibrated
    component through Threshold(p). Inherits the monotone law (and its property
    tests) from Threshold."""
    name, space_in, space_out = "cal_gate", "ratio", "bool"


register_fn(FnSpec(
    fid="CAL.PRECISION.WILSON",
    description="Per-producer calibrated precision: Wilson score lower bound "
                "over the (correct, total) verdict tally; None with no data.",
    version="1", laws=("monotone",), space_in="count", space_out="ratio",
), wilson_lower)

register_fn(FnSpec(
    fid="CAL.GATE",
    description="The precision gate as a Readout: calibrated component >= p.",
    version="1", laws=("monotone", "threshold-sound"),
    space_in="ratio", space_out="bool",
), CalGate)
