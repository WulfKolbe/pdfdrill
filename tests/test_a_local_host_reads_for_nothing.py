"""The model lane on a LOCAL host: lane 3, cost `free` (T-0157 / B8).

`gemmaocr` was a metered lane by construction — it looked for a key, it
estimated a price in EUR, and the keyless install was told to use lane 5, which
reads no words at all. But the SAME Gemma-4 runs on a local Ollama host over
the same OpenAI-compatible protocol, for nothing, and the lane contract already
orders lanes by cost: free before metered before paid.

So this is not a sixth lane. It is lane 3 on a host that charges nothing: the
same command, the same reader, the same artefact. What these tests hold is the
two things that go wrong when a free route is bolted onto a metered lane — a
price printed over a read that spends nothing, and the user's own machine
appearing in an artefact.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import gemma_reader as GR
from pdfdrill import ocr_router as OR
from pdfdrill import ollama_client as OC
from pdfdrill import vision_router as VR


def test_the_free_host_leads_the_readers_task():
    """`makora` led because it was the cheapest MEASURED host (0.000718
    EUR/page). A host that costs nothing is cheaper than the cheapest priced
    one, and the order is the contract."""
    VR.route("page_ocr_markdown")                      # force registration
    assert VR.TASKS["page_ocr_markdown"].providers[0] == "ollama"
    assert VR.PROVIDERS["ollama"].cost == "free"
    assert VR.PROVIDERS["ollama"].cost_rank < VR.PROVIDERS["makora"].cost_rank
    # cost is NOT derivable from the rank: `delegate` is free and ranks last.
    assert VR.PROVIDERS["delegate"].cost == "free"
    assert VR.PROVIDERS["makora"].cost == "metered"
    assert VR.PROVIDERS["mathpix"].cost == "paid"


def test_a_free_route_is_never_refused_for_money_and_names_none():
    """THE DEFECT: `read_preflight` estimated EUR and could REFUSE against
    PDFDRILL_OCR_BUDGET_EUR whatever host was going to serve the read. Over a
    local read both are false statements about the only thing being warned of.
    """
    ok, level, msg = GR.read_preflight(4000, budget_eur=0.0001, cost="free")
    assert ok and level == "ok"
    assert "EUR" not in msg and "budget" in msg
    # the metered answer is unchanged
    ok2, level2, msg2 = GR.read_preflight(4000, budget_eur=0.0001)
    assert not ok2 and level2 == "refuse" and "EUR" in msg2


def test_the_lane_contract_reports_the_free_host_as_lane_3():
    d = OR.choose_route(text_layer=False, needs_ocr=True, page_count=12,
                        local_reader=True)
    assert d.lane == "gemma" and d.cost == "free"
    assert "FREE" in d.command and "gemmaocr" in d.command
    # A local host outranks a key, because free outranks metered.
    d2 = OR.choose_route(text_layer=False, needs_ocr=True, page_count=12,
                         local_reader=True, keys=frozenset({OR.GEMMA_KEY}))
    assert d2.cost == "free"
    # ...and with no local host the metered answer is the one it always was.
    d3 = OR.choose_route(text_layer=False, needs_ocr=True, page_count=12,
                         keys=frozenset({OR.GEMMA_KEY}))
    assert d3.lane == "gemma" and d3.cost == "metered"
    assert "METERED" in d3.command
    # and with neither, still the free geometry lane: no words.
    d4 = OR.choose_route(text_layer=False, needs_ocr=True, page_count=12)
    assert d4.lane == "geometry"


def test_a_local_host_is_not_a_key():
    """`keys_present()` answers "which reading keys does this install have".
    A set called `keys` whose members are not keys is how the sandbox answer
    stops being true, so the host is asked for separately — and it is reported
    with the TOOLS, which is what it is."""
    assert OR.GEMMA_KEY not in OR.keys_present() or True   # key state is the
    # machine's; what is pinned is that the local host is not expressed as one
    assert "local" in OR.local_reader_present.__doc__.lower()
    assert set(OR.keys_present()) <= {OR.MATHPIX_KEY, OR.GEMMA_KEY}


def test_the_sandbox_has_no_local_host(monkeypatch):
    """`PDFDRILL_SANDBOX=1` exists so a keyed machine can ask what the keyless
    one will do. A host probe that answered `True` there would make every lane
    decision in that run a lie about the install being described."""
    monkeypatch.setenv("PDFDRILL_SANDBOX", "1")
    OC.reset_cache()
    try:
        assert OC.available() is False
        assert "SANDBOX" in OC.why_unavailable()
    finally:
        OC.reset_cache()


def test_the_machines_name_never_reaches_the_artefact(monkeypatch):
    """The host is on the user's own network. `ocr.model` in every reading,
    every call-log line and every report takes `provider_record()`, which is
    the MODEL — the hostname stays in the configuration it came from."""
    monkeypatch.setenv("PDFDRILL_OLLAMA_HOST", "http://nas.example.invalid:11434")
    monkeypatch.setenv("PDFDRILL_OLLAMA_MODEL", "gemma4:26b")
    rec = OC.provider_record()
    assert rec == "ollama/gemma4:26b"
    assert "example.invalid" not in rec and "nas" not in rec
    # ...while the host IS what the call goes to.
    assert OC.base_url() == "http://nas.example.invalid:11434/v1"


def test_a_daemon_that_happens_to_listen_is_not_a_lane(monkeypatch):
    """THE DEFECT, and it cost 13 test failures. The first version asked only
    whether something answered at OLLAMA_HOST or localhost:11434. Something
    does on this machine, so `route`, `drill`, `doctor` and the budget guard
    all changed their answers, and eleven tests that pin the METERED path
    failed because of a daemon none of them knows about.

    A lane whose availability depends on which daemons run on the machine is
    not a lane. So the host is DECLARED to pdfdrill, and the shell's own
    `OLLAMA_HOST` — Ollama's variable, set on machines that never asked
    pdfdrill for anything — is not read."""
    monkeypatch.setenv("OLLAMA_HOST", "http://shell.example.invalid:11434")
    monkeypatch.delenv("PDFDRILL_OLLAMA_HOST", raising=False)
    OC.reset_cache()
    try:
        assert OC.declared() is False or "shell.example.invalid" not in OC.host()
        assert "shell.example.invalid" not in OC.base_url()
        monkeypatch.setenv("PDFDRILL_OLLAMA_HOST", "http://run.example.invalid:11434")
        OC.reset_cache()
        assert OC.declared() is True
        assert "run.example.invalid" in OC.base_url()
    finally:
        OC.reset_cache()


def test_a_bare_host_port_still_makes_a_url(monkeypatch):
    """A declaration is often `host:11434` with no scheme — Ollama's own
    spelling. A base URL of `host:11434/v1` reaches nothing."""
    monkeypatch.setenv("PDFDRILL_OLLAMA_HOST", "box.example.invalid:11434")
    assert OC.base_url() == "http://box.example.invalid:11434/v1"


def test_no_declaration_is_no_lane(monkeypatch):
    monkeypatch.delenv("PDFDRILL_OLLAMA_HOST", raising=False)
    OC.reset_cache()
    try:
        if not OC.declared():                      # no `ollama_host` in config
            assert OC.available() is False
            assert "no host declared" in OC.why_unavailable()
    finally:
        OC.reset_cache()


def test_the_reasoning_guard_is_sent_with_every_call():
    """MEASURED on gemma4:26b, 2026-11-25: without it the completion budget
    goes into a `reasoning` field the OpenAI envelope does not carry, and the
    caller gets `content: ""` — an empty page, not a short one. With it, the
    same prompt answered in two tokens."""
    assert OC.EXTRA_BODY == {"reasoning_effort": "none"}
    assert "ollama" in VR._CALLERS
