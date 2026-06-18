"""
Batched CLI delegation transport: in the Claude Code CLI runtime, `delegate_batch`
must process same-kind IMAGE tasks (eq_ocr / page_md / vision) in ONE `claude -p`
call per chunk instead of one subprocess per page — each `claude -p` re-pays the
~180K-token Claude Code startup tax, so per-page calls waste it N times. Batching
pays it once per chunk and maps the combined JSON response back to each task_id.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import llm_delegate as D, openai_vision as ov


def _eq_tasks(n, tmp):
    tasks = []
    for i in range(n):
        img = tmp / f"page-{i}.png"
        img.write_bytes(b"\x89PNG" + str(i).encode())
        tasks.append(D.LLMTask(kind="eq_ocr", prompt=ov.EQ_OCR_PROMPT,
                               image_path=str(img), meta={"page": i}))
    return tasks


import re as _re


def _imgids(prompt):
    """The ordinal ids (img1, img2, …) the batch prompt assigns, in order."""
    return list(dict.fromkeys(_re.findall(r"\bimg\d+\b", prompt)))


def test_cli_batches_same_kind_into_one_call(tmp_path, monkeypatch):
    tasks = _eq_tasks(3, tmp_path)
    calls = {"n": 0}

    def fake_invoke(prompt, **kw):
        calls["n"] += 1
        ids = _imgids(prompt)
        assert len(ids) == 3                       # all three pages in one prompt
        return json.dumps({sid: [{"latex": "x^{2}", "kind": "equation"}] for sid in ids})
    monkeypatch.setattr(D, "_cli_invoke", fake_invoke)

    results, deferred = D.delegate_batch(tasks, runtime=D.Runtime.CLI)
    assert deferred is None
    assert calls["n"] == 1                         # ONE claude -p, not three
    assert len(results) == 3
    for t in tasks:
        recs = results[t.task_id]["records"]
        assert recs and recs[0]["latex"] == "x^{2}"


def test_cli_batch_chunks_large_runs(tmp_path, monkeypatch):
    tasks = _eq_tasks(23, tmp_path)               # > one chunk
    calls = {"n": 0}

    def fake_invoke(prompt, **kw):
        calls["n"] += 1
        ids = _imgids(prompt)
        return json.dumps({sid: [{"latex": "a", "kind": "math"}] for sid in ids})
    monkeypatch.setattr(D, "_cli_invoke", fake_invoke)

    results, _ = D.delegate_batch(tasks, runtime=D.Runtime.CLI)
    # 23 tasks, chunk size 10 -> 3 calls (not 23)
    assert calls["n"] == 3
    assert len(results) == 23


def test_cli_batch_missing_id_falls_back_per_task(tmp_path, monkeypatch):
    tasks = _eq_tasks(2, tmp_path)
    seen = {"batch": 0, "single": 0}

    def fake_invoke(prompt, **kw):
        ids = _imgids(prompt)
        if len(ids) == 2:                          # the batch prompt
            seen["batch"] += 1
            # answer only the FIRST image -> the second falls back to a single call
            return json.dumps({ids[0]: [{"latex": "p", "kind": "math"}]})
        seen["single"] += 1                        # the per-task retry
        return json.dumps([{"latex": "q", "kind": "math"}])
    monkeypatch.setattr(D, "_cli_invoke", fake_invoke)

    results, _ = D.delegate_batch(tasks, runtime=D.Runtime.CLI)
    assert seen["batch"] == 1 and seen["single"] == 1      # one retry for the gap
    assert len(results) == 2
    assert results[tasks[0].task_id]["records"][0]["latex"] == "p"
    assert results[tasks[1].task_id]["records"][0]["latex"] == "q"


def test_single_image_task_not_batched(tmp_path, monkeypatch):
    # one task: no batch wrapper, the plain per-task path (no id-map prompt)
    tasks = _eq_tasks(1, tmp_path)

    def fake_invoke(prompt, **kw):
        assert "JSON object mapping" not in prompt    # not the batch prompt
        return json.dumps([{"latex": "z", "kind": "math"}])
    monkeypatch.setattr(D, "_cli_invoke", fake_invoke)

    results, _ = D.delegate_batch(tasks, runtime=D.Runtime.CLI)
    assert results[tasks[0].task_id]["records"][0]["latex"] == "z"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
