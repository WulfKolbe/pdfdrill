"""466 — runtime prompts live in files, and a call log records which file."""
import hashlib, json, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from pdfdrill import prompts

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Every prompt moved out of Python by 466, with the sha256 of its value AS IT
#: STOOD IN PYTHON before the move. This is the whole guarantee: a move that
#: dropped a newline, changed an escape, or truncated at a quote fails here.
#: A DELIBERATE prompt change updates the hash in the same commit as the file,
#: which is the point — a prompt cannot change unnoticed.
MOVED = {
    "refine-propose-system":  "54dbc803f38a0648",
    "refine-propose":         "fc906638ab673cbc",
    "refine-propose-crop":    "93339a4107573ff5",
    "vision-selector":        "5243b1fa790d09fc",
    "vision-graph-tikz":      "ab2d1cf18d4a0c8d",
    "vision-chem-structure":  "84cd0c9477be17b3",
    "vision-mathpix-md":      "3df1872339bd7197",
    "vision-equation-ocr":    "a624658a0552a53c",
    "delegate-vision":        "de6554bbecc7bf9a",
    "delegate-bib":           "c3e405cad2c59a49",
    "delegate-lean":          "1143af5472b5eb5e",
    "gemma-system":           "91b59dd8483eb23c",
    "gemma-table":            "48442abfc8fc10d7",
    "lean-theorem":           "9f52ba1d32830b4f",
    "escalate":               "5d57ad9544f063ba",
    "llm-generic":            "a1992637fbf4ef79",
    "revise-region":          "0e9bed9ad3104312",
    "recover-figure":         "203c79ca4223a548",
    "datikz-summarise":       "e0a465920117e988",
}


@pytest.mark.parametrize("name,sha", sorted(MOVED.items()))
def test_the_moved_prompt_is_byte_identical_to_what_python_held(name, sha):
    body = prompts.load(name)
    assert hashlib.sha256(body.encode()).hexdigest().startswith(sha), name


def test_every_moved_prompt_is_reachable_by_name():
    have = set(prompts.names())
    assert set(MOVED) <= have, sorted(set(MOVED) - have)


def test_filenames_follow_the_convention():
    for d in prompts.search_dirs():
        if not d.is_dir():
            continue
        for p in d.glob("*"):
            if p.name.endswith(prompts.SUFFIX):
                assert prompts.FILENAME.match(p.name), p.name


def test_a_missing_prompt_raises_rather_than_falling_back():
    with pytest.raises(prompts.PromptMissing) as e:
        prompts.load("no-such-prompt-exists")
    # the error names where it looked, so the fix is obvious
    assert "docs/prompts" in str(e.value)


def test_the_body_is_what_is_below_the_first_separator():
    assert prompts.split_body("head\n---\nbody\n") == "body\n"
    assert prompts.split_body("head\n---\na\n---\nb\n") == "a\n---\nb\n"
    # no separator -> the whole file, which is how the task prompts work
    assert prompts.split_body("all of it\n") == "all of it\n"


def test_identity_is_the_filename_and_the_hash_of_the_body():
    ident = prompts.identity("refine-propose-crop")
    assert ident["prompt_file"].endswith("-refine-propose-crop-prompt.md")
    assert ident["prompt_sha256"] == hashlib.sha256(
        prompts.load("refine-propose-crop").encode()).hexdigest()


def test_the_hash_is_of_the_body_not_the_file(tmp_path, monkeypatch):
    """Editing the provenance header must not read as a changed prompt."""
    monkeypatch.setenv("PDFDRILL_PROMPTS", str(tmp_path))
    prompts._cache.clear()
    f = tmp_path / "2026-01-01-x-prompt.md"
    f.write_text("first note\n\n---\n\nBODY\n")
    one = prompts.identity("x")["prompt_sha256"]
    prompts._cache.clear()
    f.write_text("a completely different note\n\n---\n\nBODY\n")
    assert prompts.identity("x")["prompt_sha256"] == one
    prompts._cache.clear()
    f.write_text("first note\n\n---\n\nBODY CHANGED\n")
    prompts._cache.clear()
    assert prompts.identity("x")["prompt_sha256"] != one


def test_call_log_records_the_prompt_file_and_hash(tmp_path):
    from pdfdrill import callog
    rid = callog.open_run(tmp_path, "t466")
    callog.log_call(tmp_path, rid, prompt="P", system="S", reply="R",
                    prompt_name="refine-propose-crop")
    rec = [json.loads(l) for l in callog.path_for(tmp_path, rid).read_text()
           .splitlines()]
    call = [r for r in rec if r.get("kind") == "call"][0]
    assert call["prompt_name"] == "refine-propose-crop"
    assert call["prompt_sha256"] == prompts.identity(
        "refine-propose-crop")["prompt_sha256"]
    assert call["prompt"] == "P"          # the verbatim record is still there


def test_an_unknown_prompt_name_does_not_lose_the_paid_reply(tmp_path):
    from pdfdrill import callog
    rid = callog.open_run(tmp_path, "t466")
    callog.log_call(tmp_path, rid, prompt="P", system="S", reply="THE REPLY",
                    prompt_name="not-a-prompt")
    call = [json.loads(l) for l in callog.path_for(tmp_path, rid).read_text()
            .splitlines() if '"kind": "call"' in l][0]
    assert call["reply"] == "THE REPLY"
    assert call["prompt_sha256"] == ""
    assert "PromptMissing" in call["prompt_identity_error"]


def test_no_runtime_prompt_is_still_embedded_in_python():
    """A long string literal named *PROMPT* in src/ is the thing 466 removed."""
    import ast
    offenders = []
    for p in sorted((ROOT / "src" / "pdfdrill").rglob("*.py")):
        if p.name == "prompts.py":
            continue
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any("PROMPT" in n or "_SYSTEM" in n for n in names):
                continue
            if isinstance(node.value, ast.Constant) and \
                    isinstance(node.value.value, str) and \
                    len(node.value.value) > 120:
                offenders.append("%s:%d %s" % (p.name, node.lineno, names[0]))
            elif isinstance(node.value, ast.JoinedStr):
                offenders.append("%s:%d %s (f-string)" % (p.name, node.lineno,
                                                          names[0]))
    assert not offenders, offenders


def test_the_bundled_copy_matches_the_canonical_one():
    r = subprocess.run([sys.executable, "tools/promptsync.py", "check"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
