"""
pdfdrill/vision_router.py — ONE routing layer over every vision/text LLM call.

The state machine (not the user) decides which provider + prompt serve a TASK:
MathPix is the only promptless provider; Gemma-4 on Novita is the cheap vision
route; Mercury (diffusion) is the fast text route; GPT-4o the heavy vision
route; the Claude delegation the keyless fallback. Tasks carry their prompt in
a registry (register_task) — the slot the commercial-document prompts land in.
All routing tests run with availability monkeypatched — no network, no keys.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import vision_router as VR


def _force(monkey: dict):
    """Override provider availability: {name: bool}. Returns a restore fn."""
    saved = {n: p.available for n, p in VR.PROVIDERS.items()}
    for n, avail in monkey.items():
        VR.PROVIDERS[n].available = (lambda a: (lambda: a))(avail)
    def restore():
        for n, fn in saved.items():
            VR.PROVIDERS[n].available = fn
    return restore


def test_provider_table_shape():
    for name in ("mathpix", "gemma", "mercury", "openai", "delegate"):
        assert name in VR.PROVIDERS, f"{name} missing"
    assert VR.PROVIDERS["mathpix"].promptless is True
    assert all(not p.promptless for n, p in VR.PROVIDERS.items()
               if n != "mathpix")
    # mercury is the fast TEXT route, not a vision provider
    assert VR.PROVIDERS["mercury"].kind == "text"
    # gemma is cheaper than openai (the routing tiebreak the user asked for)
    assert VR.PROVIDERS["gemma"].cost_rank < VR.PROVIDERS["openai"].cost_rank


def test_route_equation_ocr_prefers_mathpix_then_gemma():
    restore = _force({"mathpix": True, "gemma": True, "openai": True,
                      "mercury": False, "delegate": False})
    try:
        prov, prompt = VR.route("equation_ocr")
        assert prov == "mathpix" and prompt is None        # promptless
    finally:
        restore()
    restore = _force({"mathpix": False, "gemma": True, "openai": True,
                      "mercury": False, "delegate": False})
    try:
        prov, prompt = VR.route("equation_ocr")
        assert prov == "gemma" and prompt                  # prompt-driven
    finally:
        restore()


def test_route_table_prefers_cheap_gemma():
    restore = _force({"mathpix": True, "gemma": True, "openai": True,
                      "mercury": False, "delegate": False})
    try:
        prov, prompt = VR.route("table_to_latex")
        assert prov == "gemma"
        assert "multirow" in prompt                        # the tested table prompt
    finally:
        restore()


def test_route_fast_text_prefers_mercury():
    restore = _force({"mercury": True, "gemma": True, "openai": True,
                      "mathpix": False, "delegate": False})
    try:
        prov, _ = VR.route("fast_text")
        assert prov == "mercury"
    finally:
        restore()


def test_route_nothing_available_is_honest():
    restore = _force({n: False for n in VR.PROVIDERS})
    try:
        prov, prompt = VR.route("equation_ocr")
        assert prov is None
    finally:
        restore()


def test_register_task_for_commercial_prompts():
    """The user's upcoming scanned-commercial-document prompts drop in here."""
    VR.register_task("commercial_invoice",
                     prompt="EXTRACT the invoice fields as simplified syntax…",
                     providers=("gemma", "openai", "delegate"), kind="vision")
    restore = _force({"gemma": True, "openai": True, "mathpix": False,
                      "mercury": False, "delegate": False})
    try:
        prov, prompt = VR.route("commercial_invoice")
        assert prov == "gemma" and "simplified syntax" in prompt
    finally:
        restore()
    assert "commercial_invoice" in VR.TASKS


def test_unknown_task_raises():
    try:
        VR.route("no_such_task")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "no_such_task" in str(e)


def test_run_dispatches_to_the_routed_provider():
    """run() executes the routed provider's caller — monkeypatched, no network."""
    calls = {}
    restore = _force({"gemma": True, "mathpix": False, "openai": False,
                      "mercury": False, "delegate": False})
    real = VR._CALLERS["gemma"]
    def _fake(task, prompt, image, text, **kw):
        calls["gemma"] = (task, prompt, image)
        return {"provenance": "gemma",
                "latex": "\\begin{tabular}{l}x\\end{tabular}",
                "text": "", "confidence": None, "lines": []}
    VR._CALLERS["gemma"] = _fake
    try:
        rec = VR.run("table_to_latex", image="/tmp/x.png")
        assert rec["provider"] == "gemma"
        assert rec["latex"].startswith("\\begin{tabular}")
        assert calls["gemma"][0] == "table_to_latex"
        assert "multirow" in calls["gemma"][1]
        assert calls["gemma"][2] == "/tmp/x.png"
    finally:
        VR._CALLERS["gemma"] = real
        restore()


def test_cmd_snip_routes_when_no_provider_given():
    """The user does not decide: cmd_snip with provider=None consults the
    router — no MathPix keys + Gemma available → gemma serves."""
    import tempfile, types
    from pdfdrill import commands
    restore = _force({"mathpix": False, "gemma": True, "openai": False,
                      "mercury": False, "delegate": False})
    seen = {}
    import pdfdrill.gemma_client as GC
    real = GC.snip_result
    GC.snip_result = lambda img, **kw: seen.setdefault("called", True) and {
        "provenance": "gemma", "latex": "x", "text": "x",
        "confidence": None, "lines": []}
    try:
        with tempfile.TemporaryDirectory() as d:
            pdf = Path(d) / "x.pdf"; pdf.write_bytes(b"%PDF-1.4")
            out = commands.cmd_snip(pdf, image="/tmp/nonexistent.png",
                                    provider=None)
            assert seen.get("called") is True          # gemma was routed to
    finally:
        GC.snip_result = real
        restore()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
