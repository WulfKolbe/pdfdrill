r"""The guards around a METERED account, and the scorer that makes a reader
verifiable without using it.

The account behind the model lane is a fixed prepayment: 10 EUR, 0.28 of it
spent over three days of testing, and when it empties the endpoint stops
answering — mid-document. Every test here is about one of the three
consequences:

  * a paid command must never be auto-run for the operator;
  * a read must be refused BEFORE the first call if it cannot be finished;
  * what a call cost must be a fact on disk, not a figure on someone's
    dashboard.
"""
from __future__ import annotations

import json

import pytest


# ── a paid step is named, never inserted ───────────────────────────────────

def test_the_manifest_declares_every_lane_that_spends_money():
    from pdfdrill.planner import load_manifest, network_commands
    paid = network_commands(load_manifest())
    for name in ("mathpix", "gemmaocr", "visionocr", "snip", "vision",
                 "translate", "bibfetch", "refine"):
        assert name in paid, f"{name} spends money and is not declared"


def test_the_free_counterparts_are_not_declared_paid():
    """`ocr` is tesseract and `model`, `linescmp`, `spend` touch no network.
    Declaring a free step paid would stop `--ensure` running it, which costs
    the operator a step they never had to ask for."""
    from pdfdrill.planner import load_manifest, network_commands
    paid = network_commands(load_manifest())
    for name in ("ocr", "model", "inspect", "linescmp", "spend", "report"):
        assert name not in paid, f"{name} is free and is declared paid"


def test_auto_running_a_paid_command_raises():
    from pdfdrill import commands
    commands._auto_run_offline_only("ocr")               # offline: fine
    for paid in ("mathpix", "gemmaocr", "visionocr"):
        with pytest.raises(RuntimeError, match="refusing to AUTO-RUN"):
            commands._auto_run_offline_only(paid)


def test_every_direct_auto_fallback_asserts_its_step_is_offline():
    """The planner enforces "declared, never auto-run" for the steps IT
    inserts. The places where one command calls another directly are
    invisible to it, and those are where a free command silently becomes a
    bill when an engine changes underneath. Each such site must pass through
    the assertion.
    """
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src/pdfdrill/commands.py"
    text = src.read_text(encoding="utf-8")
    # every direct call to another command's handler from inside commands.py
    sites = [m.start() for m in re.finditer(r"^\s+cmd_ocr\(pdf\)", text,
                                            re.M)]
    assert sites, "the auto-fallback call sites moved — re-point this test"
    for at in sites:
        window = text[max(0, at - 300):at]
        assert "_auto_run_offline_only(" in window, (
            "an auto-fallback at offset %d calls another command without "
            "asserting it is offline" % at)


def test_gemmaocr_refuses_outright_when_paid_steps_are_blocked(tmp_path):
    """Reached from an auto-inserted prerequisite: no spend, and the command
    to run by hand is named."""
    from pdfdrill import commands
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    token = commands._NO_PAID.set(True)
    try:
        out = commands.cmd_gemmaocr(pdf)
    finally:
        commands._NO_PAID.reset(token)
    assert "NOT run" in out and "pdfdrill gemmaocr" in out


def test_gemmaocr_refuses_a_read_that_would_outlive_the_budget(tmp_path,
                                                               monkeypatch):
    from pdfdrill import commands
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setenv("PDFDRILL_OCR_BUDGET_EUR", "0.0001")
    monkeypatch.setattr("pdfdrill.probes.ensure", lambda *a, **k: None)
    monkeypatch.setattr("pdfdrill.probes.page_count", lambda sc: 500)
    out = commands.cmd_gemmaocr(pdf)
    assert "refused" in out.lower()
    assert "PDFDRILL_OCR_BUDGET_EUR" in out


# ── the Makora host is its own provider, not Novita's names ───────────────

def test_makora_has_its_own_key_and_endpoint():
    """Reaching it by overriding NOVITA_API_BASE would file the Makora key
    under a Novita name: `doctor` would report a credential that is not one,
    and the two hosts do not behave the same anyway."""
    from pdfdrill import gemma_client as gc
    assert "makora" in gc.makora_base_url()
    assert gc.MAKORA_EXTRA_BODY == {"reasoning_effort": "none"}
    with pytest.raises(RuntimeError, match="MAKORA_API_KEY"):
        import os
        old = os.environ.pop("MAKORA_API_KEY", None)
        try:
            gc.makora_api_key()
        finally:
            if old is not None:
                os.environ["MAKORA_API_KEY"] = old


def test_makora_is_the_cheapest_provider_and_is_offered_the_reader_task():
    from pdfdrill import vision_router as vr
    vr.route("page_ocr_markdown")                  # force task registration
    assert vr.PROVIDERS["makora"].cost_rank == 0
    assert vr.TASKS["page_ocr_markdown"].providers[0] == "makora"


def test_the_transport_passes_extra_body_and_returns_the_usage(monkeypatch):
    """A host that loops on an image prompt unless `reasoning_effort: none`
    is sent cannot be talked to at all by a transport with no way to pass
    one; and a metered account cannot be tracked without `usage`."""
    from pdfdrill import gemma_client as gc
    sent = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "hi"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                "model": "m"}).encode()

    def fake_urlopen(req, timeout=None, host=None):
        sent["payload"] = json.loads(req.data.decode())
        sent["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(gc.net, "urlopen", fake_urlopen)
    rec = gc.chat_completion_full("prompt", None, model="m",
                                  base_url="https://h/v1", api_key="k",
                                  extra_body={"reasoning_effort": "none"})
    assert sent["payload"]["reasoning_effort"] == "none"
    assert rec["usage"] == {"prompt_tokens": 11, "completion_tokens": 7}
    assert rec["finish_reason"] == "stop" and rec["text"] == "hi"


def test_the_text_only_wrapper_still_returns_a_string(monkeypatch):
    """Four existing callers want the text and nothing else."""
    from pdfdrill import gemma_client as gc
    monkeypatch.setattr(gc, "chat_completion_full",
                        lambda *a, **k: {"text": "T", "usage": {},
                                         "finish_reason": "", "model": "",
                                         "host": ""})
    assert gc.chat_completion("p", None, model="m", base_url="b",
                              api_key="k") == "T"


# ── what a call cost is a fact on disk ─────────────────────────────────────

def test_the_call_log_records_the_providers_own_usage(tmp_path):
    from pdfdrill import callog
    run = callog.new_run_id("gemmaocr")
    callog.open_run(tmp_path, "gemmaocr")
    callog.log_call(tmp_path, run, prompt="p", system="s", reply="r",
                    model="google/gemma-4-26B-A4B",
                    usage={"prompt_tokens": 3280, "completion_tokens": 1088},
                    eur_per_page=0.000718)
    rec = [r for r in callog.read_run(callog.path_for(tmp_path, run))
           if r.get("kind") == "call"][0]
    assert rec["usage"]["prompt_tokens"] == 3280
    assert rec["usage"]["total_tokens"] == 4368
    assert rec["usage"]["eur_estimate"] == 0.000718


def test_a_call_without_usage_records_none_rather_than_a_guess(tmp_path):
    from pdfdrill import callog
    run = callog.new_run_id("x")
    callog.open_run(tmp_path, "x")
    callog.log_call(tmp_path, run, prompt="p", system="s", reply="r")
    rec = [r for r in callog.read_run(callog.path_for(tmp_path, run))
           if r.get("kind") == "call"][0]
    assert "usage" not in rec


def test_spend_adds_up_what_the_document_has_cost(tmp_path):
    from pdfdrill import callog
    run = callog.new_run_id("gemmaocr")
    callog.open_run(tmp_path, "gemmaocr")
    for _ in range(3):
        callog.log_call(tmp_path, run, prompt="p", system="s", reply="r",
                        model="m",
                        usage={"prompt_tokens": 100, "completion_tokens": 50},
                        eur_per_page=0.001)
    callog.log_call(tmp_path, run, prompt="p", system="s", reply="r")
    s = callog.spend(tmp_path)
    assert s["calls"] == 4 and s["calls_with_usage"] == 3
    assert s["prompt_tokens"] == 300 and s["completion_tokens"] == 150
    assert s["eur_estimate"] == pytest.approx(0.003)
    assert s["by_model"]["m"]["calls"] == 3


def test_cmd_spend_says_so_when_nothing_has_been_spent(tmp_path):
    from pdfdrill import commands
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert "No logged model calls" in commands.cmd_spend(pdf)


# ── the scorer: a reader is verifiable for free ────────────────────────────

def _reading(pages):
    """pages: {page_no: (w, h, [(type, x, y, w, h)])}"""
    return {"pages": [
        {"page": n, "page_width": w, "page_height": h,
         "lines": [{"type": t, "region": {"top_left_x": x, "top_left_y": y,
                                          "width": bw, "height": bh}}
                   for t, x, y, bw, bh in lines]}
        for n, (w, h, lines) in sorted(pages.items())]}


def test_two_readings_at_different_resolutions_still_compare():
    """THE REASON `page_width` IS PART OF THE CONTRACT. MathPix reads at its
    own resolution and this reader renders at 400 dpi; comparing raw regions
    would score every line zero."""
    from pdfdrill import linescmp
    small = _reading({1: (1000, 2000, [("text", 100, 200, 800, 40)])})
    big = _reading({1: (2000, 4000, [("text", 200, 400, 1600, 80)])})
    res = linescmp.compare(big, small)
    assert res["hit"] == 1 and res["median_iou"] == 1.0
    assert res["hit_rate"] == 1.0 and res["type_rate"] == 1.0


def test_a_box_in_the_wrong_place_is_not_a_hit():
    from pdfdrill import linescmp
    ref = _reading({1: (1000, 2000, [("text", 100, 200, 800, 40)])})
    ours = _reading({1: (1000, 2000, [("text", 100, 900, 800, 40)])})
    res = linescmp.compare(ours, ref)
    assert res["hit"] == 0 and res["lines"] == 1


def test_our_extra_boxes_are_counted_and_do_not_flatter_the_score():
    """A reader that emits twice as many boxes covers everything and would
    score well on recall alone. The extras are reported instead."""
    from pdfdrill import linescmp
    ref = _reading({1: (1000, 2000, [("text", 100, 200, 800, 40)])})
    ours = _reading({1: (1000, 2000, [("text", 100, 200, 800, 40),
                                      ("text", 100, 600, 800, 40),
                                      ("text", 100, 900, 800, 40)])})
    res = linescmp.compare(ours, ref)
    assert res["hit"] == 1 and res["ours_lines"] == 3
    assert res["ours_unmatched"] == 2


def test_page_info_is_left_out_of_the_score_and_counted_separately():
    from pdfdrill import linescmp
    ref = _reading({1: (1000, 2000, [("page_info", 10, 10, 50, 30),
                                     ("text", 100, 200, 800, 40)])})
    ours = _reading({1: (1000, 2000, [("page_info", 10, 10, 50, 30),
                                      ("text", 100, 200, 800, 40)])})
    res = linescmp.compare(ours, ref)
    assert res["lines"] == 1
    assert res["page_info_ours"] == res["page_info_theirs"] == 1


def test_a_heading_read_as_prose_is_not_counted_a_type_disagreement():
    """Both are prose a sentence runs through and `line_types` treats them
    identically. A disagreement inside that set is not a defect."""
    from pdfdrill import linescmp
    ref = _reading({1: (1000, 2000, [("section_header", 100, 200, 800, 40)])})
    ours = _reading({1: (1000, 2000, [("text", 100, 200, 800, 40)])})
    assert linescmp.compare(ours, ref)["type_ok"] == 1


def test_a_display_read_as_prose_is_a_type_disagreement():
    from pdfdrill import linescmp
    ref = _reading({1: (1000, 2000, [("math", 100, 200, 800, 40)])})
    ours = _reading({1: (1000, 2000, [("text", 100, 200, 800, 40)])})
    res = linescmp.compare(ours, ref)
    assert res["hit"] == 1 and res["type_ok"] == 0


def test_pages_the_two_readings_do_not_share_are_skipped():
    from pdfdrill import linescmp
    ref = _reading({5: (1000, 2000, [("text", 1, 1, 10, 10)])})
    ours = _reading({9: (1000, 2000, [("text", 1, 1, 10, 10)])})
    res = linescmp.compare(ours, ref)
    assert res["pages"] == 0 and res["lines"] == 0


def test_a_zero_sized_region_is_not_scored_as_a_box():
    from pdfdrill import linescmp
    ours = _reading({1: (1000, 2000, [("text", 0, 0, 0, 0)])})
    ref = _reading({1: (1000, 2000, [("text", 100, 200, 800, 40)])})
    assert linescmp.compare(ours, ref)["hit"] == 0


def test_the_report_is_prose_a_person_can_read():
    from pdfdrill import linescmp
    ref = _reading({1: (1000, 2000, [("text", 100, 200, 800, 40)])})
    out = linescmp.report(linescmp.compare(ref, ref), ours_name="a",
                          theirs_name="b")
    assert "a vs b" in out and "1/1" in out and "median IoU" in out


# ── two commands, one prerequisite ─────────────────────────────────────────

def test_commands_that_satisfy_the_same_condition_are_known_to_be_alternatives():
    """`requires` names what a layer READS; which command produces it is the
    operator's choice. `mathpix` and `gemmaocr` both end with a typed,
    geometry-bearing reading beside the PDF."""
    from pdfdrill.planner import equivalent_commands, load_manifest
    alts = equivalent_commands(load_manifest())
    assert alts.get("mathpix") == {"mathpix", "gemmaocr"}
    assert alts.get("gemmaocr") == {"mathpix", "gemmaocr"}


def test_a_missing_paid_prerequisite_names_the_cheaper_alternative(tmp_path):
    """A message that names only `mathpix` sends the operator to the dearer
    lane — about fifty times dearer per page — because it happens to be the
    one the consumer's `requires` lists."""
    from pdfdrill import planner
    pdf = tmp_path / "unread.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    out = planner.describe("inspect", pdf)
    assert "mathpix (paid" in out
    assert "`pdfdrill gemmaocr`" in out
    assert "satisfies the same prerequisite" in out


# --------------------------------------------------------------------------- #
#  --rebuild: the free half of a paid lane, said out loud
# --------------------------------------------------------------------------- #

def test_rebuild_refuses_rather_than_buying_the_pages_it_is_missing(tmp_path,
                                                                    monkeypatch):
    """`--rebuild` means "assemble again from what has been bought". A rebuild
    that quietly bought the missing pages would be the opposite of what it
    says, and on a fixed prepayment that is the difference that matters: every
    change to the geometry, the types or the containers wants re-measuring and
    none of them should cost anything."""
    from pathlib import Path

    import pytest
    from pdfdrill import gemma_reader as gr

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(gr, "read_page",
                        lambda *a, **k: pytest.fail("a rebuild must not spend"))

    def fake_rasterize(path, out, pages=None, dpi=400, gray=True):
        np = pytest.importorskip("numpy")
        Image = pytest.importorskip("PIL.Image", reason="Pillow")
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        dst = out / "page-0001.png"
        Image.fromarray(np.full((80, 60), 255, dtype="uint8"),
                        mode="L").save(dst)
        return [dst]

    from pdfdrill import pdf_reading
    monkeypatch.setattr(pdf_reading, "rasterize", fake_rasterize)
    monkeypatch.setattr(pdf_reading, "page_of", lambda p: 1)

    with pytest.raises(gr.ReadRefused) as exc:
        gr.fetch_gemma(pdf, rebuild=True, layout=False,
                       blob_dir=tmp_path / "blob")
    assert "--rebuild" in str(exc.value)
    assert "SPENDS" in str(exc.value)
