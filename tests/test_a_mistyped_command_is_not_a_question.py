r"""A misspelled verb with arguments is a typo, not a question for an LLM.

OWNER, 2026-11-12, after typing `inpsect --pages 20-60` on the open document:
"please explain what I am doing wrong and why pdfdrill never works as expected?"

WHAT HAPPENED. The REPL's typo guard was gated on `len(line.split()) == 1`:

    inpsect                 -> "no command `inpsect`. Did you mean: inspect?"
    inpsect --pages 20-60   -> sent to the LLM as a QUESTION

The LLM path is `claude -p`, a subprocess with its own tools, so it did not
answer "that is not a command". It went looking, read the SIBLING sidecar
`BH2.compressed.drill.json`, reported the long original filename recorded there
as absent from disk, stated a page count the document does not have, and the
whole thing was stored as a knowledge item grounded in 0 cited units. The
document it called missing was `BH2/BH2.pdf`, 170 MB, 400 pages, in the folder
the answer names.

THE SIGNAL WAS NEVER THE WORD COUNT. It is whether the line reads as an
INVOCATION: `--pages` is a flag, and prose does not carry flags. A single dash
is not enough ("why -3 dB?" is a real question), which is why `looks_invoked`
requires `--`.

WHY A PURE FUNCTION. This decision lived inside `main()`'s input loop, where no
test could reach it without a document, a model and an LLM — which is exactly
how the fall-through branch survived. `classify_line` is total and pure, so
every shape is checkable here in milliseconds.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import drillui_chat as DC                                  # noqa: E402


#: A stand-in for `load_commands`: the real list is 125 typed commands read from
#: `pdfdrill commands --json`. These are the ones the cases below need.
CMDS = {c: {} for c in (
    "inspect", "status", "model", "md", "mathpix", "tiddlers", "toc", "size",
    "dests", "doctor", "bibtex", "bibfetch", "bibliography", "abstract")}


def _kind(line):
    kind, resolved, _notes = DC.classify_line(CMDS, line)
    return kind, resolved


def test_the_owners_line_runs_inspect():
    """The reported case, end to end through the decision."""
    assert _kind("inpsect --pages 20-60") == ("command", "inspect --pages 20-60")


def test_a_mistyped_verb_with_flags_never_reaches_the_llm():
    """Whatever the resolution, the one forbidden outcome is 'question'."""
    for line in ("inpsect --pages 20-60", "modle --force", "statsu --html",
                 "zzzz --force"):
        kind, _ = _kind(line)
        assert kind != "question", f"{line!r} was sent to the LLM"


def test_a_verb_that_matches_nothing_is_rejected_with_suggestions():
    kind, _ = _kind("zzzz --force")
    assert kind == "reject"
    _k, _l, notes = DC.classify_line(CMDS, "zzzz --force")
    assert "no command `zzzz`" in notes[0]


def test_an_ambiguous_prefix_with_flags_lists_the_candidates():
    """`bib --force` used to fall through to the LLM for the same reason a
    typo did; only the lone word `bib` was ever answered."""
    kind, _ = _kind("bib --force")
    assert kind == "reject"
    _k, _l, notes = DC.classify_line(CMDS, "bib --force")
    assert "ambiguous" in notes[0] and "bibtex" in notes[0]


def test_an_unambiguous_prefix_still_resolves_with_its_arguments():
    assert _kind("insp --pages 20-60") == ("command", "inspect --pages 20-60")
    assert _kind("tidd") == ("command", "tiddlers")


def test_a_real_command_is_untouched():
    assert _kind("inspect --pages 20-60") == ("command", "inspect --pages 20-60")
    assert _kind("status") == ("command", "status")


def test_prose_is_still_a_question():
    """The regression that would matter most: the chat must keep working."""
    for line in ("what does the abstract say about the metron?",
                 "why is there no single global metric?",
                 "summarise chapter 3"):
        assert _kind(line)[0] == "question", line


def test_a_single_dash_in_prose_is_not_a_flag():
    """"why -3 dB?" is a question. Requiring `--` is what keeps it one — with a
    one-dash rule, `why` would be fuzzy-matched against the command list and
    the question rejected."""
    kind, _ = _kind("why -3 dB at the cutoff?")
    assert kind == "question"


def test_a_hyphenated_word_is_not_a_flag():
    assert _kind("is this state-of-the-art?")[0] == "question"


def test_the_question_mark_prefix_still_forces_the_llm():
    """The escape hatch: a one-word question, or a question that happens to
    start with something command-shaped."""
    assert _kind("?inspect") == ("question", "inspect")
    assert _kind("?md --pages 2") == ("question", "md --pages 2")


def test_a_bang_still_forces_a_command():
    assert _kind("!inspect --pages 20-60")[0] == "command"


def test_a_bare_question_mark_is_rejected_with_its_usage():
    kind, _, notes = DC.classify_line(CMDS, "?")
    assert kind == "reject" and "usage: ?<question>" in notes[0]


def test_a_lone_typo_is_still_corrected_as_before():
    """The behaviour that already worked must not change."""
    assert _kind("tiddler") == ("command", "tiddlers")
    assert _kind("inpsect") == ("command", "inspect")


def test_an_empty_line_is_not_a_command():
    assert _kind("")[0] == "question"


def test_looks_invoked_only_counts_a_flag_after_the_verb():
    """`--help` as the FIRST token is not a verb at all; the flag that makes a
    line an invocation is one in its argument list."""
    assert DC.looks_invoked("inspect --pages 20-60") is True
    assert DC.looks_invoked("inspect 20-60") is False
    assert DC.looks_invoked("--pages") is False


# ── sound, when letters fail ────────────────────────────────────────────────
#
# OWNER, 2026-11-12: "I have seen my typo and without the typ it worked fine,
# a phonem search would by helpful for users like me."
#
# `difflib` compares LETTERS. It catches a transposition (`inpsect`) and a
# dropped letter, and misses a different spelling of the same sound —
# `inspekt`, `doktor`, `phonts`, `mathpiks` — which is exactly what a
# German-speaking reader types for an English command name.

PAID = frozenset({"mathpix", "translate", "gemmaocr"})
CMDS_PAID = {**CMDS, "translate": {}, "gemmaocr": {}}


#: MEASURED, 2026-11-12, over German-style respellings of all 170 commands
#: (c→k, f→ph, x→ks, z→ts, y→i, v→f, qu→kv, th→t, ck→k, sh→sch, -y→-ie,
#: -tion→-tsion): 139 variants, of which `difflib` at cutoff 0.8 already
#: resolved 113, the phonetic rung resolved 18 more, 0 were resolved WRONGLY,
#: and 8 fall to neither and get the "did you mean" list.
#:
#: The split is not arbitrary. A one-for-one substitution (`inspekt`,
#: `doktor`) stays above 0.8 and difflib has always handled it. A respelling
#: that changes the LENGTH — f→ph, x→ks, z→ts — drops to 0.727-0.769 and was
#: unreachable: `phonts`, `lateks`, `bibteks`, `conphig`, `skan`.
DIFFLIB_ALREADY = (("inspekt", "inspect"), ("doktor", "doctor"))
PHONETICS_ONLY = (("phonts", "fonts"), ("lateks", "latex"),
                  ("bibteks", "bibtex"), ("conphig", "config"),
                  ("skan", "scan"), ("okr", "ocr"))


def test_the_phonetic_cases_are_the_ones_letters_miss():
    """The premise of the rung, asserted rather than assumed: if difflib were
    already resolving these, the tests below would pass with the phonetic code
    deleted and prove nothing."""
    import difflib
    for word, cmd in PHONETICS_ONLY:
        assert not difflib.get_close_matches(word, [cmd], n=1, cutoff=0.8), \
            f"{word} is within difflib's reach after all"
    for word, cmd in DIFFLIB_ALREADY:
        assert difflib.get_close_matches(word, [cmd], n=1, cutoff=0.8) == [cmd]


def test_a_german_spelling_runs_the_command_it_sounds_like():
    for word, cmd in PHONETICS_ONLY + DIFFLIB_ALREADY:
        cmds = {**CMDS, cmd: {}}
        kind, resolved, _ = DC.classify_line(cmds, f"{word} --force")
        assert (kind, resolved) == ("command", f"{cmd} --force"), word


def test_ph_and_f_are_the_same_sound():
    assert DC.phonetic_key("phonts") == DC.phonetic_key("fonts")


def test_a_respelling_is_never_resolved_to_the_wrong_command():
    """`sitse` is `size` spelled the German way, and the key drops vowels, so
    it collides with `status` — both reduce to `sts`. Requiring the first two
    SOUNDS to agree ("si" vs "st") removes that one wrong hit of 20; the word
    is then rejected with suggestions, which is the right answer for a command
    nobody can identify."""
    assert DC.phonetic_key("sitse") == DC.phonetic_key("status")
    assert DC.phonetic_matches(CMDS, "sitse") == []
    assert _kind("sitse --force")[0] == "reject"


def test_the_key_does_not_collide_model_with_mathpix():
    """Soundex would: M340 for both. A free local build and a paid API call
    must never share a key — that collision is a bill, not a correction."""
    assert DC.phonetic_key("model") != DC.phonetic_key("mathpix")


def test_a_guess_never_spends_money():
    """`mathpicks` sounds exactly like `mathpix`, which is a paid conversion.
    The hit is reported; running it stays the reader's own act."""
    kind, _, notes = DC.classify_line(CMDS_PAID, "mathpicks", PAID)
    assert kind == "reject"
    assert "COSTS MONEY" in notes[0] and "mathpix" in notes[0]


def test_a_free_command_is_still_run_from_its_sound():
    kind, resolved, _ = DC.classify_line(CMDS_PAID, "inspekt --pages 2", PAID)
    assert (kind, resolved) == ("command", "inspect --pages 2")


def test_an_ambiguous_sound_lists_the_candidates(monkeypatch):
    """Two commands that sound alike must not be chosen between by guess.

    STUBBED, and the reason is worth stating: no two of the 170 commands sound
    alike today, and any word close enough in SOUND to two commands is also
    close enough in LETTERS that `difflib` answers first — so this branch
    cannot be reached with a real command list. It is the guard for the day a
    pair like `fonts`/`phonts` both exist, and a stub is the only way to hold
    it to its behaviour now."""
    monkeypatch.setattr(DC, "phonetic_matches", lambda cmds, w: ["alpha", "beta"])
    kind, _, notes = DC.classify_line({"alpha": {}, "beta": {}}, "zzzzzzzz --force")
    assert kind == "reject", notes
    assert "sounds like" in notes[0] and "alpha" in notes[0] and "beta" in notes[0]


def test_a_one_consonant_key_is_not_a_match():
    """MEASURED: `size` reduces to `s`, and so does `zzzz`. A key that short is
    noise — `zzzz --force` must still be rejected as an unknown command, not
    run as `size`."""
    assert DC.phonetic_key("size") == DC.phonetic_key("zzzz")
    assert DC.phonetic_matches(CMDS, "zzzz") == []
    kind, _, notes = DC.classify_line(CMDS, "zzzz --force")
    assert kind == "reject" and "no command `zzzz`" in notes[0]


def test_prose_is_not_phonetically_matched_into_a_command():
    """The phonetic rung runs only where a command was already expected: a lone
    word or a flagged line. A sentence stays a question whatever it sounds
    like."""
    assert _kind("what does the modell say about mass?")[0] == "question"


def test_an_empty_or_punctuation_word_has_no_key():
    assert DC.phonetic_key("") == ""
    assert DC.phonetic_key("---") == ""
    assert DC.phonetic_matches(CMDS, "---") == []
