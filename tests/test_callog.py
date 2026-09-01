"""447 — a paid call whose prompt and reply are not kept cannot be repeated."""
import json
from pathlib import Path

from pdfdrill import callog


def test_a_run_leaves_a_header_calls_and_a_footer(tmp_path):
    rid = callog.open_run(tmp_path, "t", script="tools/t.py", note="n")
    callog.log_call(tmp_path, rid, prompt="P", system="S", reply="R",
                    model="m", subject="EQ1", arm="with_error")
    p = callog.close_run(tmp_path, rid, calls=1, outcome="ok")
    recs = callog.read_run(p)
    assert [r["kind"] for r in recs] == ["run", "call", "end"]
    assert recs[0]["script"] == "tools/t.py"
    assert recs[1]["prompt"] == "P" and recs[1]["reply"] == "R"
    assert recs[2]["outcome"] == "ok"


def test_the_prompt_is_kept_VERBATIM(tmp_path):
    r"""Nothing is redacted or truncated. A redacted prompt is not the prompt
    that was sent, and a truncated one cannot be re-sent — which is the whole
    point. If a prompt must not be kept, it must not be sent.
    """
    rid = callog.open_run(tmp_path, "t")
    long_prompt = "x" * 50_000 + "\n\\begin{aligned} a & = b \\end{aligned}"
    callog.log_call(tmp_path, rid, prompt=long_prompt, system="S", reply="R")
    got = [r for r in callog.read_run(callog.path_for(tmp_path, rid))
           if r["kind"] == "call"][0]
    assert got["prompt"] == long_prompt


def test_the_arm_is_recorded(tmp_path):
    """444 needed this and did not have it: two calls about one subject that
    differ by a line of prompt are a comparison only if the record says which
    was which."""
    rid = callog.open_run(tmp_path, "t")
    for arm in ("with_error", "without_error"):
        callog.log_call(tmp_path, rid, prompt="p", system="s", reply="r",
                        subject="EQ1", arm=arm)
    calls = [r for r in callog.read_run(callog.path_for(tmp_path, rid))
             if r["kind"] == "call"]
    assert sorted(c["arm"] for c in calls) == ["with_error", "without_error"]
    assert {c["subject"] for c in calls} == {"EQ1"}


def test_a_run_that_dies_still_leaves_what_it_spent(tmp_path):
    """Appended per call, never buffered: a run killed half way has paid for
    what it already sent, and that has to survive."""
    rid = callog.open_run(tmp_path, "t")
    callog.log_call(tmp_path, rid, prompt="p", system="s", reply="r")
    recs = callog.read_run(callog.path_for(tmp_path, rid))
    assert len(recs) == 2                      # no footer, and still readable
    assert not [r for r in recs if r["kind"] == "end"]


def test_a_foreign_file_in_the_directory_is_not_a_run(tmp_path):
    """The evidence directory sits beside a document and other things land in
    it. `runs_for` takes only `.jsonl`, so a stray file cannot be read as a
    run — one appeared during 447 from a shell-quoting slip of mine."""
    (tmp_path / "calls").mkdir()
    (tmp_path / "calls" / "v.json").write_text("{ not jsonl }")
    rid = callog.open_run(tmp_path, "t")
    assert [p.name for p in callog.runs_for(tmp_path)] == ["%s.jsonl" % rid]


def test_every_model_call_routes_through_the_logged_wrapper():
    """The hook is module-level, not a parameter: a runner cannot forget it,
    and threading an argument through every call site is exactly what gets
    forgotten."""
    import inspect
    from pdfdrill import refine
    src = inspect.getsource(refine._novita_chat)
    assert "_novita_chat_raw" in src
    assert "callog.log_call" in src
    assert hasattr(refine, "set_call_log")
