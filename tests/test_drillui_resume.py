"""
Phase 0.3 of the capability-planner plan: drillui persisted its multi-doc session
store (`.drillui_session.docpack`) but a fresh launch never re-read it ("state
persisted but not loaded"). `existing_session_store` + `session_members` are the
pure resume helpers `main()` now uses to adopt that store as the live context.
"""
import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
_spec = importlib.util.spec_from_file_location("drillui_chat", TOOLS / "drillui_chat.py")
dc = importlib.util.module_from_spec(_spec)
sys.modules["drillui_chat"] = dc
_spec.loader.exec_module(dc)


def test_existing_session_store_found_when_present(tmp_path):
    assert dc.existing_session_store(str(tmp_path)) is None       # nothing yet
    store = tmp_path / dc.SESSION_STORE_NAME
    store.write_text('{"is_combined": true, "meta": {"sources": []}}')
    assert dc.existing_session_store(str(tmp_path)) == str(store)


def test_existing_session_store_ignores_empty_and_missing(tmp_path):
    (tmp_path / dc.SESSION_STORE_NAME).write_text("")             # zero-byte → ignore
    assert dc.existing_session_store(str(tmp_path)) is None
    assert dc.existing_session_store("") is None                  # no dir → None


def test_session_members_reads_sources(tmp_path):
    store = tmp_path / dc.SESSION_STORE_NAME
    store.write_text(json.dumps({"is_combined": True,
                                 "meta": {"sources": ["a.pdf", "b.pdf"]}}))
    assert dc.session_members(str(store)) == ["a.pdf", "b.pdf"]
    # malformed / no meta → [] (never crashes)
    bad = tmp_path / "bad.docpack"; bad.write_text("not json")
    assert dc.session_members(str(bad)) == []


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
