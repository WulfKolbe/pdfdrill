# Handover — state of play

Written for a session with no history here (any provider). Facts are measured,
with the command that measured them. If a path has moved, trust the repository
over this file.

Last verified 2026-08-16: repo @ `555d656` on `eqblobs-and-gzip-tex`, pushed to
`origin` (github.com/WulfKolbe/pdfdrill — verified with `git ls-remote`; `main`
and `master` sit at `1812e3f`). Working tree clean.

    PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider
    -> 2048 passed, 0 failed, 0 skipped (measured 2026-08-16; the 8 old
       test_resume_sh failures were tests pinning the pre-edit resume.sh
       contract — rewritten to pin the user's hardcoded one-liner)

**A skipped test is not a pass.** The old five-session skip story is in §4.

**2026-08-16 session note (damage control + reset prep):** the user reported
work landing under `/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL` instead of
GitHub. Inspected BEFORE deleting: those dirs held NO git repo and NO commits
(only empty session scratchpads + one task log); every branch was already on
GitHub at the local HEAD. The /tmp dirs and `/tmp/drillui-session.log` were
then removed. Lesson kept as a rule: **verify `git ls-remote origin` after any
push claim; never let commits exist only in a scratch worktree.** CLAUDE.md was
compacted the same day (was 3271 lines loaded into every session ≈ the user's
"75% of input tokens"); the full historical text is preserved verbatim at
`docs/CLAUDE-FULL.md`.

---

## 1. Working rules that were learned by defect

Each of these cost real time or real data in this project.

1. **Measure the premise before building on it.** The mathgold gold set moved
   from 87 equations to 21,230 (different prop) on measurement; T1 had no
   producer at all.
2. **State the population beside every number.** 21,240 vs 59 for "the mathgold
   population" were both right and measured different things (structure vs
   structure+placement). See `docs/mathgold-population.txt`.
3. **A guarantee in a docstring is not a guarantee.** Run a branch-mutation
   sweep (each `if` forced True/False); outcomes: killed / survived /
   incompetent / equivalent.
4. **Run mutation sweeps with `PYTHONDONTWRITEBYTECODE=1`.** A same-length `cp`
   restore matches the stale `.pyc` by size AND mtime; a test failed against
   correct source and a working fix was nearly reverted. `git diff --stat`
   after every write, too.
5. **Never return a plausible default for an unknown.** Raise or return an
   explicit unresolved marker (`mathgold.slt.Unresolved`) — never a sentinel
   string (`"UNKNOWN" == "UNKNOWN"`). **Re-learned the hard way 2026-08-21:**
   `parse_latex_slt` collapses `\begin{aligned}` to ONE node labelled
   `UNRESOLVED_aligned`, so two unrelated multi-line equations produced
   byte-identical signatures and `slt_edit_distance` returned 0 without
   comparing contents. 662 of 1,488 corpus rows (44.5%) called "structurally
   identical" were this, and it moved a measured noise floor from 7 to 22 —
   a number handed to another session that would have hidden real findings.
   `crossref.formula_signature` now returns None for a degenerate signature;
   a signature that cannot distinguish two expressions must never reach a
   comparison. Writing the rule down does not inoculate you against it.
6. **Presence is not adequacy.** Four bugs shaped as "a fact/file/output/twin
   exists"; each needed a detector that reads the actual store.
7. **Verify the written file, not the object in memory.** Two "in-memory right,
   file wrong" defects passed 1745 tests. Persisting commands should assert via
   `tests/test_model_write_roundtrip.py::roundtrip` (a meta-test pins how many
   do).
8. **Absence has to be read out of the file, not inferred from one empty key.**
   (Commit `1892313`: "lines 0" was reported as "rules never leave inkdrill"
   while the just-generated file held all four rules under
   `page["ink"]["rules"]`.)
9. **Do not ask what a command can answer.** Reversible → do it and record it.
   Preference that changes what gets built → ask.
10. **When deciding without the user:** take the reversible option and record
    the decision, the rejected alternative, and what would change your mind.
11. **A masked success reads exactly like a masked failure.** A summary
    regex that missed singular 'Output written (1 page)' reported a good
    compile as '0 pages' (2026-08-19); the inkdrill session was bitten twice
    by exit-code-masking pipes. Any success/failure summarizer must be tested
    on BOTH a real success and a real failure — a parser that can only see
    one of them sees neither.
12. **An unexplained delta is a FINDING, not an observation.** A generator
    change grew the corpus 941 -> 1,080 pages (+15%) with identical equation
    counts; both sessions filed it as "benign, indices shifted" instead of
    asking why 15% and not 1%. It was a real defect (a `\penalty0` at the
    start of a `p{}` cell is TAKEN, giving every backslash-initial cell an
    empty first line). Ask the magnitude question: a number nobody can derive
    is a bug nobody has found yet.
13. **Verify layout cost, not only correctness.** `f7d5568` was accepted on
    "equations render + probe passes" and shipped a +38% page regression.
    Generator acceptance now measures page count before/after on a fixed
    document alongside the column probe. A cost you never measured is a cost
    your consumer measures for you.

14. **Re-measure a symptom against the CURRENT artifact before diagnosing
    it.** A "117 rows vs 23 equations" symptom was diagnosed by both sessions
    — mechanism proposed, code read, fix designed — before anyone re-ran it;
    the number came from a build three regenerations old and the symptom no
    longer existed (the same document now reads 19 rows vs 23). In a pipeline
    that regenerates, an observation is evidence about the artifact it was
    taken from, not about today's. Diagnosing stale evidence produces
    confident, wrong fixes.
15. **A prediction about CONTENT is not a prediction about PIXELS.** I
    predicted "0 differing Rendered cells" from the fact that the emitted
    LaTeX is identical for a migrated row. Falsified: 34 differed, because 6
    rows had reflowed one page earlier and therefore rasterised at a
    different sub-pixel offset. The content claim was right and the cell
    claim was wrong, and they are not the same claim. State which layer a
    prediction is about, or it cannot be scored.
16. **An unchanged input column is a free control — keep one.** The consumer's
    diff showed 6 SCAN cells differing, and the scan column is an untouched
    JPEG that no migration of mine can reach. That is what separated "the ink
    changed" from "the row moved"; without it both hypotheses fit the 34
    Rendered cells equally. Nobody designed it as a control — it was there
    because the report happens to carry the source beside the derivative.
17. **A pattern verified on a sample that lacks the disambiguating case cannot
    fail.** Three identifier regexes broke this way in two days, each correct
    on the case it was written against: 056's missed `~\eqnum{...}` (23 rows
    misparsed); 058's `\ident\{[^}]*\}` truncated at the brace of
    `\allowbreak{}`, which `breakable_ident` inserts after every dot, and
    bucketed all 93 demoted rows as "other" — it looked right only on
    `1511.08771`, the one document whose identifiers carry no dot-break; the
    consumer's first parser read ZERO identifiers when `\allowbreak{}` first
    appeared inside the braces. This is the fixture rule the project already
    runs on, applied to instruments: a sample that does not contain the class
    the pattern discriminates against cannot detect a pattern that ignores it.
    Two defences, both cheap: match to a stable anchor rather than a brace
    class (the consumer's `[^&\n]*?EQ\d+` passes `\allowbreak{}` and
    `\eqnum{}` through untouched), and check the residue bucket — 93 rows in
    "other" is a broken pattern announcing itself.
18. **Two subtractions of equal size are not a chain.** Reconciling my 93
    demoted rows against the consumer's 72 and 51: the three Heim books total
    21 rows and `1511.08771` alone totals 21, so `93-21=72` and `72-21=51`
    are both true for unrelated reasons and neither implies the other. Their
    route never included the Heim books, so it was clean; only my
    cross-check contained the coincidence. Arithmetic that lands on the
    other side's number is not corroboration — the populations have to match
    term by term. Same shape as the `(page,row)` key: a consistent-looking
    result produced by two mechanisms nobody had separated.

19. **Write the number down before you write the sentence.** Six reports in
    the 650-670 run carried a central claim that did not survive a reviewer
    opening the artefact, and the shape never varied: a plausible sentence
    written from expectation, then evidence gathered that did not actually
    test it. 650's evidence run used an unchanged model, so it could not
    have failed. 653 said ~1,296 documents failed for a harmless reason
    when 1,191 carried real defect counts. 665 claimed exhaustive font
    verification without testing the five alphabets the change moved. 661
    verified "the production path" and had verified the retired one. 669
    said all 31 refined objects were Equations while a live Formula was
    already exercising the path and PROPS.md said both types. 670 presented
    git statistics under a heading asserting they were measured, over a
    range it had not measured, off by sevenfold. The controller did it
    twice too. The fix is not more care; it is order — measure, paste the
    number, then write the prose around it. And when a measurement is
    offered as proof, ask what result would have refuted it: 650's could
    not fail, and that was visible before it ran.

20. **`git worktree` does not isolate imports in this repo.** `pip install
    -e .` pins an absolute `sys.path` entry to the main checkout, so a
    worktree runs the main tree's modules unless `PYTHONPATH=<worktree>/src`
    is set explicitly. A reviewer hit this while checking whether three test
    failures belonged to a concurrent session: the first worktree run
    reproduced the other session's failure and looked like a real
    regression. This is exactly how a live defect hides behind a "verified
    in isolation" claim. Set PYTHONPATH, and say you did.

21. **One implementer at a time, and the controller is not exempt.**
    Dispatching a second writing agent while the first still held the tree
    cost a near-miss (one session's uncommitted work briefly vanished),
    three test failures that needed attributing rather than fixing, and two
    agents hand-crafting `git apply --cached` patches to stage only their
    own hunks of a shared file. Nothing was lost, and only because both
    agents noticed. Read-only reviewers may overlap freely; writers may not.

22. **A check that names what it looks at is not a check that asks whether
    it is looking at the right things.** Every instance below was, on its
    own terms, a CORRECT answer to the question it posed — the defect was
    always in the question never asked, not in the arithmetic once it was.
    This is the most repeated defect shape in this codebase's recent
    history, and a rule number was overdue:

    - `inkreport.fresh_ink` (670, before its fix) asked four — later five
      — content questions about a stored ink measurement (model hash,
      formula rule, page bound, `why`) and correctly answered every one.
      None asked whether the CODE that built the report is the code that
      would build it now: 463 (a profile change dropping a section) and
      625 (a stray `\\` that put every Scan image on a second line) both
      passed all four/five questions while the report's GEOMETRY had
      changed underneath them. Fixed by `report_tex.geometry_signature`,
      a sixth question over the AST of the functions that actually decide
      report layout.
    - `report_tex.render_crops` (671, before its fix) asked "does a file
      named `<title>.jpg`, over 500 bytes, exist" and answered correctly —
      such a file did exist. It never asked whether that file was cut from
      the region the row NOW points at. A 2026-09-03 change to how host
      lines are joined moved 159 rows' regions out from under their
      already-rendered crops across six documents, and the cache kept
      serving the old picture, correctly, by its own question. Fixed by
      keying the cache on `(page, region)` instead of on the filename
      (`CROP_GEOMETRY_FILE`).
    - `docops.projectors.tiddlywiki.tiddler_integrity`'s `UNREFERENCED_KINDS`
      asks, correctly, "does any transclusion reference this tiddler" for
      the eight kinds it names (Formula, Equation, Footnote, Sidenote,
      Table, Diagram, Picture, Reference). It never asks whether the
      title scheme has grown since that list was written: the checked-in
      conservation ratchet (`docops/conserve.py`, `conserve_baseline.json`)
      currently carries eight further VIOLATION-class kinds — Algorithm,
      AlgorithmStep, Citation, CodeListing, Link, List, Proof, Theorem —
      that `UNREFERENCED_KINDS` cannot see AT ALL, not a false negative
      but a blind spot. `out/656.txt` caught it directly: two documents
      `tiddler_integrity` reported as "80 unreferenced" / "40
      unreferenced" — clean-looking, correctly computed summaries — sit
      beside a `conserve --gate` count of 84 and 81 VIOLATION-class
      unreachable objects on the SAME two documents, most of which
      `tiddler_integrity` never mentions because its allow-list of kinds
      never grew to match what the model can now contain.
    - `reports.gate.crop_gate` (667, before its fix) asked "does the
      displayed crop match the one measured" and, correctly, found no
      mismatch on a row nothing had measured yet — there was nothing to
      compare. It answered `ok=True`, INDISTINGUISHABLE from a row that
      was checked and passed, because it never asked "is there anything
      here for me to look at". Fixed by `gate.GateStatus.verified`: armed
      (asked and passed/refused) is now a fact a caller can read, not a
      claim buried in `ok` alone.
    - `reports.gate.PUBLISHED_FILES` — the fixed tuple of five filenames
      `tools/publishcheck.py`'s site-diff and `commands._status_budget_notes`'s
      over-budget audit both iterate — asks, for each name IN the tuple,
      "does this match / fit its budget". Neither ever asks "is this the
      complete list of files this document actually publishes now": a
      new evidence kind added to the pipeline without a matching entry
      here is invisible to both checks, not flagged as unpublished or
      over budget but simply never looked at. Not yet fixed, and unlike
      the four instances above this one has no incident on record in
      this repo's own history to cite — named here on the strength of
      the same exposed shape, so the next person who adds a sixth
      published file has a reason to update this tuple in the same
      commit rather than finding out from a silent gap later.

    The general form: a check that is provably correct about the
    population it inspects can still be silently wrong about the
    program, because nobody re-asked whether that population is still
    the whole one. Writing the check's own population down beside it
    (rule 2) does not fix this by itself — every instance above HAD a
    named population; the missing step is periodically asking whether
    something now exists outside it.

23. **An offset recorded before a rewrite is applied after it.** 676 needed
    to hide the math on some of a paragraph's lines from a later pass that
    scans the whole joined string. The first version recorded each line's
    `(start, end)` range in the joined text and told the pass to skip those
    ranges. Between the two, `_substitute_footnotes` and
    `_substitute_inline_pictures` rewrite the string — `\({ }^{1}\)`
    becomes `<sup>1</sup>`, an `\includegraphics` URL becomes a
    transclusion — so every recorded range is stale by a delta nobody
    computed, and the skip lands somewhere else. It does not crash and it
    does not look wrong in a diff.

    The fix is not to recompute the offsets; it is to stop using offsets.
    A MARK IN THE TEXT travels with the text through any number of
    rewrites: the delimiters get a private U+0000 between the backslash
    and the bracket, the scanning pass cannot match them, and one literal
    `.replace()` at the end restores the source exactly. The general form:
    when a decision made at stage A must hold at stage C and stage B may
    rewrite the subject, carry the decision IN the subject, not in
    coordinates over it. A test that the private mark never reaches the
    output is mandatory — a leaked sentinel is invisible in a diff and
    visible to the reader.

24. **Two readers of one record must read the same FIELD, and "we both read
    the line" is not that.** MathPix gives every line both `text` and
    `text_display`. `FormulaProcessor` builds from `text_display or text`;
    `inlinectx.load_spans` re-scanned `text` alone. For most lines the two
    agree, so the divergence is invisible in every sample that does not
    contain the disambiguating case — and the case exists: a `diagram` or
    `chart` line carries `text == ""` and all of its content in
    `text_display`. Every span on such a line was therefore invisible to
    the scan, so the object the model had built from it could never find
    its host line, and 27 published rows silently lost a page, a
    confidence, a region and a crop.

    This is rule 22's shape one level down: both readers correctly answered
    "is this value on this line", neither asked "are we looking at the same
    characters". When two modules key a join on content, the field that
    content comes from is part of the key — write it in both docstrings, or
    give them one function to call.

25. **A command that forgets DERIVED state must not be able to reach the
    INPUT.** `drill --full` wiped the sidecar with `rmtree(sc.blob_dir)`,
    correct in the legacy layout (`<name>.pdf.drill/` is a folder of its own)
    and fatal in the self-contained one (`<stem>/<stem>.pdf` — every document
    in the library), where `blob_dir` IS the folder holding the document. It
    deleted the document, exited 0, and the only sign was a mid-output
    "Model-lane read failed: File not found". Found by an auditing session, not
    by the suite, because every test used the legacy layout. Two rules fall out:
    a destructive helper takes the thing it must PRESERVE as an argument and
    checks afterwards that it is still there (`_wipe_derived(blob_dir, pdf)`
    raises rather than carrying on), and when a layout can place a derived
    directory and an irreplaceable input at the same path, no test that
    exercises one layout covers the other. A licensed or personalised copy has
    no second download.

26. **A transitive pin can uninstall a patch, and the install still looks
    clean.** `bootstrap.sh`, `pip install -e .` and the CoCalc imageserver
    install each removed the patched pdfminer fork. Nothing in pdfdrill asked
    for that — our own pin is `pdfminer.six>=20221105`. pdfPLUMBER pins
    `pdfminer.six==<release>` EXACTLY; pip resolves that pin, the fork's
    setuptools-scm version (`20260108.dev6+ga18de2a9c`) is not equal to the
    release, and stock pdfminer is installed over the patch. `import pdfminer`
    then still works and `LTChar.glyphname` is simply gone, which is why it
    survived three sessions and cost a session once already. Measured in two
    throwaway venvs: the scm-versioned wheel is REPLACED by `pip install
    pdfplumber`; a wheel versioned `20260107+glyphid.g<sha>` is KEPT, because a
    PEP 440 local segment satisfies `==20260107`. So version a patched build as
    the release its consumers pin plus a local segment, read that release from
    the consumer's metadata rather than hardcoding it, and have the installer
    report whether the build will survive the next pip run — verifying the
    FEATURE is not enough to know it will still be there tomorrow.

27. **Do not explain a marker by quoting it.** The SKILL's attestation token is
    found by the `PREFLIGHT-TOKEN:END` marker above it. Documenting that in a
    SKILL table row put the literal marker in the file twice, so
    `grep -B1 <marker>` returned the table row — the doc broke the thing it
    documented. Describe the marker ("the last line that is not an HTML
    comment"), and assert the count: `test_preflight_token_is_findable.py`
    fails if either marker appears more than once.

28. **A lane the install cannot run must be NAMED, not run.** The lane contract
    names the lane that WOULD read a document; whether this install can run it
    is a second question, carried in `cost`. `drill` dispatched on
    `dec.lane == "geometry"` and never read `dec.cost`, so a `cost="none"`
    decision — "this is the lane and it cannot run here" — ran anyway: measured
    on hilbert1902 in a numpy-free venv, ten page renders (8.58 MB) written,
    death inside the ink, exit 0. Rendering for a reading that cannot happen is
    the same defect class as buying one that was not asked for. Name it exactly
    as a paid lane is named, and refuse BEFORE the rasterizer, not after
    (`tests/test_no_lane_means_no_work.py`).

29. **A summary may only summarise what was measured.** `doctor` printed
    `[n/a] the FREE geometry lane … NO free reading for a scan at all` and then,
    four lines later, "All system tools present — every route is available". The
    list behind that sentence holds APT PACKAGES; the lanes turn on NumPy, the
    detector and the keys, none of them a system tool. The reader believes the
    last line. A closing claim that reaches wider than the thing it was computed
    from is a false report however true each line above it is.

30. **A count printed beside a file must be a count OF that file.** The
    inspector's headline said "133 elements" over a payload holding 142 records,
    for a tree with 132 rows — three populations, because the count was
    recomputed from the model instead of taken from the list the page ships
    (Document in one, Pages in the other). Count the thing you serialised, once.

31. **A check answers for the thing that will do the work.** `--check` on the
    pdfminer fork verified two interpreters and exited 0 if EITHER had it. A
    machine with a good pdf2mmd venv and stock pdfminer in the active
    interpreter therefore passed, `bootstrap.sh` skipped the build on that exit
    code, and the install ended with no `LTChar.glyphname` — silently. Report
    every candidate; take the verdict from the one that will actually import it.

32. **A provenance field may not claim a step that did not run.** Every line of
    a geometry-only lines.json carried `geometry: "ink-yolo"`, including on the
    untyped half of the lane where no detector runs at all. `geometry` is read
    to decide whether a box can be trusted as an object's extent or is only the
    ink under a row, so `ink-yolo` where nothing looked makes the weaker half of
    a lane indistinguishable from the stronger one. `text` because the detector
    said so and `text` because nothing asked are different claims.

33. **An installer installs what it names, and nothing else.** The fork script
    added pillow, scipy and pytest in all three modes. `bootstrap.sh` calls it
    for ONE thing — `LTChar.glyphname` — and the user's active environment got
    tens of megabytes of unrelated toolchain, unasked and unannounced. The venv
    mode keeps them (that venv exists for pdf2mmd and nothing else imports from
    it); the modes that write into somebody else's environment need a flag.

34. **Never key a cache on `id()`.** CPython hands a freed object's address to
    the next one, so a module-level dict keyed by `id(x)` answers a NEW object
    with an OLD object's value. `column_of` memoised a page's column bounds that
    way: 400 freshly built PageNodes occupied **14 addresses**, and alternating
    two page geometries, the SAME geometry got `mark_display_continuations` = 1
    or 0 by turns — **258 flips in 400 calls**, decided by the allocator. It
    reached us as ONE "order-dependent" test failure in a base-install run,
    which is the cheapest symptom it has; in a long-lived process (drillui, a
    corpus pass) it silently mis-columns pages instead, and the column decides
    whether an equation is a display or inline prose. A per-object memo belongs
    ON the object, where it dies with it. A dict keyed by `id()` built and
    dropped inside one call is fine — the objects are alive for its whole life;
    the swept repo has several of those and `_COLS_CACHE` was the only
    module-level one (`tests/test_column_cache_is_not_keyed_on_an_address.py`).

35. **Check the request before the toolchain.** `volume.unpack` probed for
    pikepdf before validating its arguments, so a member with no established
    page range was refused on a base install with *"unpacking a member needs
    pikepdf"* — advice that would not have helped and sends the caller to fix
    the wrong thing. The range check needs nothing and is about what they asked;
    the dependency check is about this machine. Cheapest, most specific refusal
    first.

36. **A guard that cannot fail for the worst case is not a guard.** drillui's
    stale-tab check stamped a content hash into the page and compared it on
    connect: `msg.uiVersion && window.__DRILLUI_UI_VERSION && …`. A page too OLD
    to carry the stamp made the second term `undefined`, so the check passed in
    silence — blind precisely for the stalest UI there is. Reported as "I see
    the full UI, but I can not enter anything": a pre-`#cmdline` copy, no
    element to type into, while the REPL's banner and the user's own history
    rendered perfectly. *Ask whether the absent case is distinguishable from the
    healthy one;* here silence had to become the signal (the UI announces
    itself, and the bridge warns when nothing arrives) and the warning had to go
    out on the one channel every vintage renders.

37. **A tool does not write state into a directory it was merely invoked from.**
    The preflight marker lived in `cfg.download_dir()`, which falls back to
    `~/Downloads` and then to `Path.cwd()`. On a box with no `~/Downloads` — a
    fresh container, which is where a stranger meets pdfdrill — the attestation
    was written into whatever directory the command ran from; an audit found it
    deposited in an unrelated git repo's tree, and the gate then re-blocked one
    directory later for no visible reason. Two defects in one fallback: the
    stray write, and a scope that depended on where you stood. Four docs said
    "per working directory" and the real behaviour was "per download folder",
    which is normally one shared place — so the docs were accidentally right
    only on the broken machine. The marker is per-USER state now
    (`$XDG_STATE_HOME/pdfdrill`), the old path is still READ so nobody is
    re-blocked, and the docs say what it is: once per machine, 24 h.

38. **An INFERRED location is not permission to reorganise it — and a move the
    user did not ask for must be reported.** Rule 37's fallback again, one step
    worse: `sources.adopt_into_doc_folder` files a loose PDF in the LIBRARY ROOT
    into `<stem>/`, and its own docstring drew the boundary — "anywhere else —
    someone's Downloads folder, a working directory — nothing is ever moved".
    False on a fresh machine, because the root it compares against is
    `library_root()` → `download_dir()` → `Path.cwd()`: with no `~/Downloads`
    and no config the user's working directory WAS the library root, so
    `pdfdrill size paper.pdf` — the cheapest read-only probe — filed their input
    into a new folder without a word. Adoption now requires a DECLARED root, and
    when it moves something the CLI says what went where, before the result,
    because the move changed the meaning of the argument the result is about.
    *A guard whose subject comes from a fallback chain is only as specific as
    the weakest link in that chain* — and whatever a tool silently relocates,
    the user's next command still carries the old path.

39. **A projection inherits its source document's licence.** Everything this
    repo writes — `*.md`, `*.tiddlers.json`, `*.lines.json`, `*.docmodel.json` —
    is the document re-encoded, so a rule that admits an extension admits the
    rights of every document that extension exists for. `!**/*.md` in the
    library's `.gitignore` committed the personalised ISO 32000-2 sponsored
    copy's full text: counted and never quoted, the owner's surname 1,020 times
    and "single user" 1,023 times, once per page of a 1,020-page standard. The
    PDF had been excluded for months and was never in doubt. What let the
    markdown through was the justification "34,260 files and only 0.24 GB, the
    cheapest thing in this tree" — a statement about SIZE, used to settle a
    question about RIGHTS. *Cheap to store says nothing about free to hold.*
    Ask what an extension is a projection OF, per document, before admitting it.

40. **Verify an exclusion with `git check-ignore --no-index`; the plain form
    answers for files it has already excused.** Plain `git check-ignore <path>`
    reports a TRACKED file as not-ignored whatever the rules say. In the library
    1,197 PDFs had been committed before a deny-all `/**` root was written, and
    gitignore never evicts a tracked file — so those kept working while every
    PDF added since was refused in silence: 2,655 source documents, 23.44 GB,
    including the Heim books the owner then drove to another machine to work on
    and could not find. Three batteries of check-ignore probes ran that day and
    all three were right and blind, because *a battery only tests paths someone
    thought of, and this one also excluded the paths that would have failed.* A
    check that cannot fail for a whole category is not a check for that
    category — rule 36 again, for exclusions instead of guards.

41. **A docstring that describes behaviour nobody implemented is worse than no
    docstring: it retires the question.** `_inspect_pages_dir` said "reusing any
    already present" and "Never raises". It reused nothing and it raised.
    `rasterize` calls `_require_gs()` as its first act, so the function asked
    Ghostscript for permission BEFORE it looked at the directory it maintains: on
    a machine without gs the RuntimeError fired first, `except RuntimeError`
    returned None, and every render on disk was discarded. A ser7 clone produced
    a 7,272,092-byte `BH1org.inspect.html` instead of 56,137,806 — the complete
    element tree over 319 BLANK pages — while 319 correct `p{N}.png` sat in the
    folder it had just given up on. The same blindness ran the other way with gs
    present: every call re-rendered all 319 pages, 481 MB of PNG and 32 s of gs,
    over byte-identical renders. It survived a month and an auditing session
    because the sentence had already answered the question anyone would have
    asked. *Write down what the code does, or write nothing; a claim in a
    docstring is tested by nothing and believed by everyone.*
    And its other half, rule 36 once more: an inspector whose every page is
    blank is a FAILED build, not a quieter one. `prepare_pages` substitutes an
    empty `src` per page it cannot find and counted nothing, so 40 rendered
    pages of 319 read exactly like 319 of 319; `inspect` now counts the images
    it shipped and exits 3 when there are none, because *a caller should not
    have to parse prose to learn it got nothing.*

42. **A guard keyed on OUR bookkeeping cannot protect what SOMEONE ELSE wrote.**
    `cmd_md` carried a guard whose comment said "A GENUINE MathPix markdown
    still wins" — `if sc.get_layer("md")["source"] == "mathpix": return None`.
    The MathPix download writes `evidence.mathpix_files` and never touches the
    md layer, so on the documents that mattered the layer read `'model'`,
    `'latex'` or `None`, the guard never fired, and `_md_from_latex_source` and
    `_md_from_model` — both of which write `<stem>.md`, the same path the
    download owns — replaced the file. Measured over the library: of 1,329
    documents holding a bought MathPix md, **41 no longer have it** (28 to
    `MarkdownProjector`, 7 to the latex/llm-compact routes, 6 to `translate`
    before 815 gave the bi-layer its own name). bh2's 922,111-byte download is
    on no disk and in no commit. Of the 1,285 still intact the layer protected
    **54**; the other 1,231 were one `pdfdrill md` away. *Ask the record that
    the other writer actually writes* — and where two producers share one
    filename, *ask the file*: our markdown writers sign their output with a
    YAML `generator:` line or the bi-layer's `seg source` divs, MathPix signs
    nothing, and absence of our signature is the only honest test of
    authorship. Size is not: `fetch_mathpix` reports "cached" when the md
    merely EXISTS (only `.lines.json` gets a content check), so a later run
    re-stamps the recorded byte count — 93 documents hold a MathPix md whose
    size differs from the record and 4 hold a projection whose size matches it
    exactly.
    And the same defect had a second face, in the same function: the command's
    own summary said "Prefers a genuine MathPix .md, then the model, then the
    text layer" while the code tried latex first, the model second and MathPix
    third. *An order stated in prose and inverted in code is not a preference,
    it is a bug with documentation.*

43. **"The same format as X" needs X measured, not remembered.** Asked to make
    `pdfdrill md` emit MathPix's Markdown, the obvious reading was the dialect
    of the export in hand: `\(…\)`, `\[…\]`, `\section*{}`,
    `\begin{tabular}`, `\footnotetext{}`. Counting 600 intact downloads in
    the library said otherwise — `$…$` 100%, a `$$` fence on its own line 84%,
    `#`/`##` headings 91%/99%, pipe tables 70%, `\section*` 1%, `tabular` 0%,
    `\tag{}` once in the whole sample — because the dialect is chosen by the
    REQUEST: `mathpix_client.CONVERSION_OPTIONS` asks for `["$","$"]`, and the
    hand export that prompted the question came from the UI, whose defaults
    differ. So MathPix has no single markdown format, and the one worth matching
    is the one pdfdrill buys. The projector differed from it in four places, not
    one, and already agreed on everything else. *A format is a measurement over
    the artifacts you hold, and the delimiters now live in one place
    (`markdown.MATH_INLINE`) with a test holding them equal to the purchase, so
    the projection cannot drift from what the wire asks for.*
    **And one format per provider was still one too few.** The delimiter change
    taught the widget path `$…$`, and the first acceptance run still carried 28
    `\(` — because the model is built from `lines.json`, and THAT format
    delimits inline math `\(…\)` whatever the md options say (80 occurrences
    and zero `$` in the reading checked). Prose on a DocObject therefore arrives
    in the UI dialect and has to be re-delimited on the way out, which no amount
    of reading the projector would have shown: *the format of the input is not
    the format of the output, even from one provider, and only the artifact says
    which is which.*

44. **A signature in the output cannot survive a change to the output format.**
    `_md_is_ours` decided authorship by reading the YAML `generator:` line at the
    top of a projection — correct until the projector was asked to match
    MathPix, which writes no front matter. The header went, the signature went
    with it, and the very next acceptance run served a pdfdrill projection back
    as "Markdown from MathPix": 816's defect, reintroduced by the fix for 787's,
    in the same hour and caught only because the acceptance run reads the output
    and not the exit code. The repair is not a cleverer signature but a different
    place to keep it — `_write_md` now records the sha256 of every markdown it
    writes, so the file at `<stem>.md` is ours if and only if it is still what we
    put there, whatever shape that is. *Identity belongs in the record, not in
    the artifact: a mark inside the content is hostage to every decision about
    the content.* The content signature stays as the fallback for sidecars
    written before the digest, because every projection older than this one does
    still carry its header.

---

## 2. Environment facts that are not obvious

**Preflight.** Build/extract commands are blocked until `pdfdrill preflight
--ack <TOKEN>`, once per machine for 24 h — the marker is per-user state
(`$XDG_STATE_HOME/pdfdrill`, else `~/.local/state/pdfdrill`). It used to live in
`download_dir()`, which falls back to the CWD, so on a box with no `~/Downloads`
it was written into whatever directory the command ran from and the attestation
did not hold one directory later. Automation sets `PDFDRILL_NO_PREFLIGHT=1`.

**LgEval — invoked, never vendored.**

    repo    gitlab.com/dprl/lgeval        (github.com/DPRL/LgEval is 404)
    commit  9831a3c                       (HEAD c94f6dd imports lgeval.msg_debug,
                                           which the repository does not ship)
    path    ~/.local/share/lgeval         (must be importable AS `lgeval`)
    invoke  source tools/lgeval_env.sh; lgeval_score out.lg gold.lg

The github.com/michaelyin mirror is Python 2 and will not run.

**Spell / hyphenation dictionaries.** `/usr/share/hunspell` is English only.
German `de_DE.aff/.dic` + `hyph_de_DE.dic` exist ONLY inside the flatpak
KDE runtime. `spylls` is NOT installed. Measured: `dictionary_status()` →
de:'dic' en:'enchant'; the `dic` floor has no affix/compound rules, so German
joins via the soft heuristic (`DehyphResult.reason` says which).
`HUNSPELL_DICT_DIR` → flatpak path + `pip install spylls` would light up the
affix path; neither is done.

**`resume.sh`** is now the user's own one-liner: it resumes the HARDCODED
session id `ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da` with
`--dangerously-skip-permissions`. This pin is deliberate (user edit,
2026-08-16, after a `--continue` loop trapped them). When that session dies,
the id must be edited by hand — `claude --resume` (no id) lists sessions to
pick from. `.last-session-id` is gitignored.

---

## 3. Open work

### T4 deliverable 3 — the floor (unstarted; the unblocking item)

Deliverables 1-2 done: `src/mathgold/slt.py` parses author LaTeX into a Symbol
Layout Tree and round-trips `.lg` (3000 uniform samples, seed 0: 99.8% parsed,
lossless round-trip; 64% single-expression).

The floor takes pdfminer characters+positions, applies the crudest relation
rules (baseline overlap ⇒ Right; raised+smaller ⇒ Sup), emits `.lg`, scores
against gold with LgEval. **Population is settled: 59 equations over 2
documents** (kolbe2018hubbard 54, 2510.11170v2 5) — `provenance == "tex"` AND
region+page. The 21,230 source-built equations have zero geometry and cannot
feed a positional floor. Report as anecdotal at n=59; report BOTH rows
(single-expression subset, full set with environments as `Unresolved`); never
split `align` into rows to enlarge the denominator.

### T2 — table rule weights: DONE through commit `1812e3f`

The mechanism landed across `4499468..1812e3f` (inkdrill phases 1–4):
- `page["ink"]["rules"]` contract gap closed (`ink_coverage.page_rules`,
  `include_rules=True`, `ink_tables.attach_rules` — a MathPix table rectangle
  claims ownerless booktabs rules). Phase 1 reproduces the plan exactly
  (2409.18839 p8: 35 missed components, 33 of them rules).
- Ranking is **by ORDER, never absolute width** (quantisation error does not
  shrink with dpi: +24.2/+5.4/+12.9/+5.4 % at 400/600/800/1200). Inflation
  guard +25%. `rank_rules` takes the file's declared `render_dpi`, reports
  margin_pt AND margin_px, warns under 2 px; if classification matters, render
  rules at **800 dpi** even when everything else runs 400.
- Validated on real paper 2409.18839 p9 at 400 and 800 dpi.
Tests: `tests/test_ink_rules.py` (15). Remaining: nothing blocking; a
hand-made `ink.rules[]` is no longer needed (inkdrill emits them).
Gotcha kept: `table_lines` takes a region **id**, not a `Region` — pass
`regs[0].id`.

### bh2 (2nd Heim book) report + the vision/inkdrill loop (2026-08-17)

`~/pdfdrill-library/bh2/`: MathPix gave md + tex.zip + lines.json (400pp,
12,266 lines). `tools/make_report_tex.py` generates the LaTeX formula report
(report.tex/pdf: A3 landscape, boxed, pixel-exact scan crops via `--px2mm`,
columns Identifier|Page|Source|Rendered|Image). **The tex.zip's `images/` are
exactly the regions MathPix could NOT OCR** — for bh2 exactly ONE (p400,
1078×1019px), consistent across zip/md/model (`bh2_DIA_0001`, empty
latex_code). `--texzip <dir>` feeds them into the report's "Unrecovered image
regions" section locally (no CDN). The reconstruction route for such regions
is **`pdfdrill vision`** (the GPT-4o large-prompt command; keyless → delegates
to the running agent), and an LLM's returned LaTeX can now be **verified
against the real ink with inkdrill** (compile the LaTeX, compare ink) — the
loop is noted but not yet automated.

### BH3FR is the FORMULA REGISTER — the cross-book identity anchor (2026-08-18)

`~/pdfdrill-library/BH3FR/` (149pp, 324 numbered equations + 217 inline
formulas, MathPix'd) is a REGISTER: per the user, every formula of BH1org and
bh2 should be findable in it, and it is to serve as the SOURCE OF SYNONYMS AND
ACRONYMS for all the Heim books. That makes it the natural anchor for
cross-book formula identity. BUILT as P10 `pdfdrill crossref` (2026-08-18):
ONE index over (bibkey, kind, id, signature, evidence); formula signatures are
the SLT .lg form (mathgold.slt — canonicalizes latex spelling), opaque to the
index; ranking = exact match else line-Jaccard. Store
~/pdfdrill-library/crossref.json holds 13,433 signatures (4 books, 99.86%
parse rate). MEASURED: 70% of bh2's and 62% of BH1org's display equations
resolve into the register (228/136 exact); the unmatched remainder is the OCR-
divergence QC list (crossref-map-bh2-BH3FR.txt). Synonym/acronym extraction
FROM the register is the open follow-up.

### P13 corpus — 50 arXiv docs on MathPix geometry (2026-08-18, complete)

All 50 P13 documents (list: ~/pdfdrill-library/P13-final-reports.txt) hold
genuine MathPix lines.json (paid batch, 24 min, 0 API failures; old
pdfminer/tesseract geometry preserved as *.lines.pdfminer.bak.json), rebuilt
models (model --force; the mathpix route), and content-verified report.pdf
files with pixel-exact equation crops — the inkdrill input set. Outlier
1511.08771 (379K objects, 91,450 inline formulas, 13,754 unrecovered regions)
needed its own long-cap pipeline; 809-page report, 1 residual error.

Two defects this batch taught, now fixed with tests: (1) MUTATING commands
(eqnums) lack the stale-guard and re-save a stale model with a fresh mtime —
batches must run `model --force` first; the general stale-guard for mutating
commands is an OPEN follow-up. (2) A batch freshness check on MTIMES called
the broken outputs fresh — 29 impostors; verification must read CONTENT
(cdn equations in the model + crops on disk). Rule 6 applies to batches.

### bh2 defect roll-up — two instruments, DISTINCT defect classes (2026-08-19)

Keep these separate in any roll-up; conflating them hides the fix route:
- **Will not compile alone** (P14 `standalone`, this session): bh2_EQ0147
  (stray \end{itemize}), bh2_EQ0167 (\left/\right nesting),
  BH1org_OCR_EQ0021 (bad math environment delimiter) — malformed LaTeX;
  fix = re-OCR/escalate the region. Corpus renders: bh2 340/342,
  BH1org 238/239, BH3FR 323/323 (the register compiles CLEAN alone),
  WDorg4 78/78 — PNGs in <blob_dir>/standalone/.
- **No conversion at all** (inkdrill compare, peer session): bh2_EQ0082,
  bh2_EQ0123 — MathPix produced no LaTeX; fix = vision route.
- **Wrong conversion** (inkdrill compare, peer session): bh2_EQ0105,
  bh2_EQ0131, bh2_EQ0273 — compiles fine, renders the WRONG math; only
  ink-vs-render comparison catches these (the class the P11 SLT distance
  cannot see when the register also lacks the formula).
Cross-session source: inkdrill-0d, 2026-08-19. The inkdrill harness writes
per-doc `report.compare.tsv` into each library folder when its run completes.

**Cross-session verification contract (2026-08-19, mutual):** regenerated
reports are never handed to the inkdrill session without a local pass of THEIR
probe first (reproduce it from ~/inkdrill: pngio.auto_mask +
__main__._table_cells, expect 5 columns on the equations pages); they never
report a generator defect without first ruling out instrument fault.

**Probe at >= 200 dpi.** inkdrill measured (2026-08-20, 0802.3344) that a scan
crop sits ~0.9mm below its rule at EVERY dpi — the "touching" seen in a viewer
is downsampling — but below 200 dpi cells stop being holes topologically (3
merge at 72/96, 1 at 150, none at 200+). Measured consequence for OUR probe:
the COLUMN-COUNT check is dpi-insensitive (bh2/BH3FR/WDorg4/BH1org all give an
identical lattice at 96/150/200/300, because median-span filling repairs a
fragmented slot), so past acceptance verdicts at r150 stand — but per-CELL
measurements below 200 dpi report merges that do not exist at working
resolution. Run acceptance at 300.
This ended a three-round ping-pong whose three real mechanisms are in commit
bdbd5a2 (overfull padding reserve, mixed-section pages, version-suffixed
identifiers overprinting the Page column).

### trailing_punct — the separation, and the ORDER it must be done in (2026-08-20)

**Design (user).** The TiddlyWiki arrangement is the model: the character
lives in the `text` field and the `<$latex>` widget holds only mathematics.
`trailing_punct` in the docmodel is that same separation made portable — the
math object's `latex` holds mathematics only, the swept-up sentence mark moves
to `trailing_punct`, and **the compare function sees NEITHER side's copy**
(not the LaTeX side's, not the ink/scan side's): pure math is compared to pure
math.

**Scale (out/024.txt).** 2,113 objects carry a genuine top-level trailing mark
— 39.8% of all display equations, against 0.15% of inline formulas. So this is
not a rounding-error cleanup; it touches two of every five display equations.

**MIGRATION PROTOCOL (agreed with inkdrill, 2026-08-20).** 025 is
implemented (`pdfdrill trailingpunct`, commit 14cb02d) and NO library
document has been mutated. Agreed sequence, resumable after a reset:

    1. inkdrill's in-flight compare exits, distribution reported
    2. pdfdrill migrates the FOUR BOOKS only (59 marks: bh2 17+2,
       BH1org_OCR 24+1, BH3FR 5+0, WDorg4 6+4) + re-project + regenerate
    3. inkdrill verifies per-cell component counts UNCHANGED on bh2
    4. only then the 49-document corpus (2,054 marks)

Step 3 is the gate: the report sets the mark AFTER the math box
(`\FitMath{$...$},`) precisely so the ink of both columns is unchanged,
which lets the consumer attribute any delta to the migration rather than
to a layout change. If the books show a per-cell delta, STOP.

**COMPLETE (2026-08-20, commit a0ff8a9).** 2,113 marks separated — 59 in the
books, 2,054 across the 49 corpus documents — exactly the dry-run prediction.
Corpus 942 pages against the 941/942 baseline. Consumer verified per-cell
parity on bh2: 10,432 of 10,434 cells identical, the 2 explained (colons in a
LaTeX-source column the compare never reads).

MEASURED CAVEAT — "no layout cost" is true at page-count level and NOT at
row-placement level. On 0902.0431 (673 marks) 6 of 4,386 rows sit one page
EARLIER after the migration (all delta -1; zero rows appear or disappear on
either side; bh2's 19 marks shifted nothing). Removing the mark from inside
the math box makes a cell marginally shorter, so a row that sat just past a
page boundary now fits before it. Harmless for ink comparison — a row is the
same row, one page earlier — but any PAGE-INDEXED artifact built against a
pre-migration report is off by one for those rows.

**VERIFIED END TO END (2026-08-20).** Consumer re-ran the 50-document
compare against the migrated corpus: 4,335 rows over 49 of 49 documents,
IDENTICAL row and document counts to pre-migration. Class movement, on a
4,335-row population: clean +4, noise -8, weak +1, stable +5, component -2,
findings 1,095 -> 1,099 (25.4%). Largest class delta 0.4%; the component
channel their findings are ranked on moved 2 rows of 283. The 20 rows that
changed class are the reflow residue already characterised — rows that moved
a page rasterise marginally differently and nudge across a noise boundary —
not an ink effect. Evidence: the pre/post pair of compare runs, plus the
per-cell A/Bs on bh2 (10,432/10,434 identical) and 0902.0431 (8,796 cells,
0 one-sided, 51 differing, none above the component noise ceiling).
Their findings file: results/compare-P13-arxiv-reports-<stamp>.tsv.

**Atomicity is not required** — `normalize_latex` drops a trailing mark, so
a separated value and an unseparated one compare EQUAL. A reset mid-migration
cannot produce a divergence storm; the corpus may sit half-migrated
indefinitely without harm.

**ORDER, and why it is not negotiable.** 028 runs BEFORE anything is stripped;
025 (the LaTeX-side move) waits for it. Strip the LaTeX side while the ink side
still carries the character and the two sides disagree on ~2,113 equations for
that whole run — the compare output is then not "mostly right", it is
UNUSABLE, and unusable in a way that looks like a real finding storm. Nothing
strips until 028 is confirmed complete.

### Retraction task — at U0, contract table written, U1 not started

`pdfdrill model --force` drops derived layers without retracting facts/evidence
(objects 301→261, Reference 40→0, while `BIBLIOGRAPHY_BUILT` survives and
`status` reports nothing). Recoverable (`pdfdrill bibliography` restores) — a
bookkeeping bug, not data loss. A parallel session landed `bc76c36`; reconcile
before redoing.

---

## 4. Known skips — none

`tests/test_layer_detect.py` skipped for five sessions because its 1706.03762
fixtures lived only in a scratchpad path containing a session id. Committed,
gzipped, at `tests/fixtures/layer_detect/` (103+25 KB; the "~15 MB" estimate
that kept them out was never measured). A scratchpad copy still wins when
present via `PDFDRILL_LAYER_FIXTURES`; verified the suite passes with that
variable pointing at a nonexistent path. To regenerate: build 1706.03762, run
geometry/bibliography/expandmath/svg/tiddlers, copy `model_BEFORE.json`;
`model --force`; copy `model_AFTER.json` (must keep 65 objects with a region).

## 5. Assumptions still unverified

- German compounds untested WITH spylls (not installed): the floor was shown to
  fail; spylls was not shown to succeed.
- Whether `docops/mutators/dehyphenate.py` consults hyphenation PATTERNS at
  all, or only the lexicon, was not checked.
- Nothing has touched the **tesseract or pdfminer routes**, where the user says
  the errors originate.
- `spellqc.classify` is `(speller, left, right)`; a language string in third
  position raises a confusing `AttributeError`. Not fixed.
- 20 raw model writes were converted to atomic `save_model` (silent
  `default=str` coercion → raised exception); 0 existing repr fossils found,
  but no test exercises every command's write path.

## 19. A measurement writes its script and its result beside the document

**Learned by 525, after the same complaint four times.** Nothing runs in a
scratchpad except intermediates that can be recreated on demand. Every
measurement writes `script.py` and its data into `<document>/out/<NNN>/` in
the library, and the report NAMES those paths.

`pdfdrill.taskout` does it: `save_script`, `save_json`, `save_text`,
`paths`, `report_lines`. A corpus-wide scan has no single document and
writes to `~/pdfdrill-library/out/<NNN>/`.

**Why the library and not the repo.** The repo is public; the library is
deny-by-default git — its `.gitignore` opens with `/*`, so nothing under
`<document>/out/` can be committed by accident. Measurements quote
copyrighted text, reports about them do not.

**447 established this for LLM calls** — every prompt and reply kept beside
the document — and it was never generalised. The audit of the twenty tasks
before this rule:

| | tasks | |
|---|---|---|
| A committed script | 6 | 500 503 507 509 511 517 |
| B scratchpad script only | 5 | 505 513 516 518 521 |
| C no script anywhere | 9 | 502 506 510 514 515 519 520 522 523 |

**One of twenty committed a data file** (507). **None wrote anything into
the library.** 53 files sat in a session-local `/tmp` scratchpad that no
later session can read.

The consequence is not tidiness. 522 found `latex_similarity` scored one
pair 0.857 in one argument order and 0.005 in the other; every score in
every `compare.html` was computed the broken way, and nothing in the
artefact said so. When the evidence lives in a scratchpad, a wrong number
cannot be traced back to the code that produced it — the report is prose
and the prose is all there is.

## 20. Every run ends with a list of absolute paths a person can open

**Learned by 543.** Rule 19 put `script.py` and the data beside the document,
which makes a run RE-RUNNABLE. Neither is inspectable. A person opens a PDF,
an HTML page, an image or a log.

So every task also writes `<library>/out/<NNN>/INSPECT.txt`: **one absolute
path per line and nothing else**, and prints the same list with a one-line
reason per path. The reasons stay out of the file because drillui's scanner
reads it; they go in the printed block and in `out/NNN.txt`.

`taskout.inspect_list(target, task, [(path, reason), ...])` and
`taskout.inspect_report(result)`.

**What goes in:** artefacts built or changed (report.pdf, B.pdf, *.html);
images the run produced or that a finding rests on (crops, renders, page
rasters); the compile log where a build failed; the input a finding was read
from when it is not obvious.

**What stays out:** the script, the JSON, intermediates deleted on completion
— everything only a machine reads.

**A PATH IN THAT FILE IS A PROMISE.** 408 established that presenting an
unreachable path is only half of reachable. Every path is checked for
existence and non-zero size before it is written; one that fails is NOT
written, and the report says which and why. A list that quietly holds a dead
path is worse than a short list.

**Known limit, named rather than worked around:** roughly half this library's
folder names contain spaces. Such a path is correct in a line-based file and
drillui's scanner, which splits on whitespace, cannot open it. `inspect_list`
returns them under `whitespace` and the printed block counts them. The fix is
in the scanner, not in the file.

## 2026-10-02 — the failure shape of the day: a claim no instrument could contradict

Eleven fixes landed (836-863). Not one of the five worst errors was caught by a
test, a gate or a corpus scan. All five were caught by a person or a peer opening
the actual artefact.

1. **`0.625`** — I predicted the value of a field (`scale`) from the quantity I had
   just computed myself. Two quantities share that name: the page factor (1.6,
   mine) and the published crop's own factor (0.71-0.73, inkdrill's). The number
   was plausible, the band was plausible, and nothing in the file disambiguates
   them. Settled by inkdrill drawing six marks on a page and LOOKING at them.

2. **`54%`** — correcting someone else's denominator, I built a wrong one by
   reading the largest suppression class (7,454) as the whole suppressed set
   (11,788). Understated the instrument 2.7x: the true figure is 83% of pointable
   rows, not 31%. The five classes are exclusive and sum exactly to the measured
   count — checking that identity would have caught it, and I did not.

3. **"0 .tex files contain a localhost crop URL"** — from `grep -rl` in
   pdfdrill-library. `grep` here is **ugrep**, which honours `.gitignore`, and that
   library's is DENY-BY-DEFAULT. The real count was 78. Worse, the blindness is
   SELECTIVE: `evidence-formula.tex` is searched and `<doc>.tex` is not, under the
   same command in the same directory — uniform blindness announces itself, a
   plausible non-zero answer never does. **Use `find … -exec grep` in that tree.**

4. **A plausible absence** — inkdrill read `counts.not_measured` (a summary by
   reason), saw no ids, and concluded the per-id mapping was missing. It was at the
   top level of the same file, in all 39 mark sets, 237 rows.

5. **A plausible AGREEMENT, the one worth remembering.** I had printed both fields
   side by side and built 858 against the per-id mapping. When inkdrill said the
   field was missing I replied "my reader takes `{id: reason}` already" — the
   disproof — and agreed anyway, treating the current form as a future one. We
   planned a 39-file re-emission around a defect that did not exist. A peer states
   a cause, it fits a real symptom, and agreeing costs nothing in the moment.
   Their own check read the same field they misread, so it "would have gone on
   agreeing forever": **a check written from the same misreading as the conclusion
   is not a second opinion.**

The through-line: every one produced a number or a conclusion that was internally
consistent and externally wrong. The defences that worked were an independent
implementation (two golds found one defect each), an identity that must close
(`rows + not_measured == evidence_rows`), and a human opening the file. The
defences that failed were every test and scan written by the same person who held
the misconception.

## 2026-10-03 — a proxy measured nothing, and a threshold narrowed every ink figure ever reported

865 split the equation number out of a display equation's region and reported
two numbers upward. Both were wrong, in opposite directions, and neither was
caught by anything in this repo.

**The miss rate (mine).** I counted my false negatives as "display rows whose
region is still ~full column (>1300 px)" and got 246, which made my split rate
45%. 1,300 was a round number chosen while looking at one document, and
"region is wide" is a PROXY for "region contains a number" with no measurement
behind it. inkdrill measured the ink: of those 246, **42** have an interior
gap ≥ 190 px and the median gap in the set is **30 px** — most are long
equations that legitimately span the column. The real candidate set is **91**,
and the split rate is 202 of ~293, **69%**.

The rule: *a proxy for a property is not a measurement of it, and the fact
that a proxy is conservative does not make it safe.* An understated success
rate is the same class of error as an overstated one — I committed 45% and
reported it upward, and a reader would have concluded the fix barely worked.

I had also generalised 62% from sigma26-075, my best document, to the corpus.
The first number was from one document, the second from a proxy; neither was
from the thing being counted.

**The ceiling that made the threshold honest.** The 202 correctly split rows
are a LABELLED population, and they bound the answer: after a number is
removed, an interior gap never exceeds **188 px** on this corpus. That turns
"pick a floor" into "sit above a measured ceiling, inside the 250–300 valley",
with the sensitivity stated (≥190 → 91 rows, ≥250 → 70, ≥300 → 64). A
threshold derived from a labelled population and published with its
sensitivity is a choice a reader can disagree with. One picked while looking
at the data it will classify is the failure both sessions were caught by twice
in one week.

**The grey ink (shared).** `vendor/blobcc.py:339` is
`binarize(gray, threshold=128)` and `eqblobs.py:316` calls it with no
override. A 217-grey arrow — 10,768 px of visible content in one sampled
region — scores **0 ink**. So every ink figure either session has reported,
including coverage percentages in the high nineties, is about **dark ink
only**. Nothing measured is wrong; everything measured is narrower than it
sounded. The 3% gutter cut re-centred last week was fitted to dark ink, so a
document with a grey column rule was never a case it could see.

The rule: *name the instrument's blind spot in the same message as the results
that rest on it,* not when someone asks. inkdrill did this unprompted, in the
message reporting the figures the limitation applies to. That is the standard.

**And then bounded, 2026-10-03 (inkdrill out/690), so "effect unknown" does not
get carried indefinitely.** The question was narrowed first, which is what made
it answerable: a grey rule *inside* a real gutter is harmless — the detector
wants a blank column run and grey reads as blank, so the rule makes the gutter
cleaner. The risk is the opposite, a FALSE gutter: a band blank at 128 and not
blank in fact. Over 248 pages, one per document, of the 1,436 with renders:
**79 pages (32%) carry mid-grey; 7 (2.8%) have a wide blank-at-128 run holding
mid-grey; and in 0 of those 7 is the band greyer than its own page** (ratios
0.02–1.23 — band density against page density). A ratio near 1 is grey *paper*,
which is what a scan is; six of the seven are scans. Nothing is drawn in any
band, so the threshold-128 gutter cut was never at risk on this corpus.

What it does **not** say, stated because the bound is only as good as its
scope: one page per *document*, so it bounds the rate at which documents carry
the problem, not pages; it says nothing about grey *outside* gutters, which is
common (the 32% is real, and 865's grey arrow lives in it, still invisible to
every ink measurement); and a publisher using grey column rules as house style
would change the answer completely — none is in this corpus.

**The measurement's own first answer was wrong, and that is the transferable
part.** The first pass reported 100% of pages carrying mid-grey. It used
`magick -resize 25%`, which INTERPOLATES: every glyph edge becomes a grey pixel
that was never on the page. `-sample 25%` is nearest-neighbour and invents
nothing — 32%. A measurement pipeline that anti-aliases a rendering produced
with `-dTextAlphaBits=1` is measuring its own resampler. *Check that the
instrument did not create the quantity being measured,* especially when the
first result is a round 100%.

**And a classification error a measurement cannot fix.** sigma26-081 EQ0429 is
listed as a display *equation* with `latex: "\varnothing [1, n]"`. It is a
diagram: `∅ ⟵[grey ruler]⟶ [1,n]`. The LaTeX compiles and describes neither
the arrow nor the structure, so it reads as a poor reading of an equation
rather than a correct reading of the wrong kind of object — the shape that had
`code` called "dropped entirely" when 97.5% of it was recovered. `[1,n]` is
also textbook number geometry (115 px, 8 px off the right edge, behind a
1,864 px gap), so the ink alone would have manufactured a number from a
diagram. The gap is NECESSARY AND NOT SUFFICIENT: ink finds the separation,
`project_mmd.equation_number`'s parenthesis-at-the-margin test confirms the
content. Neither instrument is safe alone.

## 2026-10-05 — resilience hides the defect it survives

A corpus pass over 2,242 documents reported **zero failures**, against 47 on
the previous pass. Three reader fixes had landed and they held. The number was
true and it was the wrong number to read.

Five documents also reported a PARTIAL READ, and two of those said
`TypeError: cannot use a string pattern on a bytes-like object` — the error
876 had just fixed. They did not fail. They **completed**, with a truncated
reading, because 876 had also taught the page loop to keep what it had read
rather than lose a document to one bad page.

So the resilience worked exactly as designed and, in the same stroke, moved a
live defect out of the column anyone was watching. *A pass that cannot fail
cannot report a failure.* **Watch the partial-read count, not the failure
count** — and when a run reports zero of something it used to report 47 of,
read the other columns before believing it.

**The defect itself is the second half of the lesson.** 876 normalised a bytes
glyph name where names enter `docmodel_six`. 872 (R2) had already put
`glyphname_reliable` inside `LTChar.__init__` — *earlier*, while the name is
still what the font program said. So the fix and the new door were written in
the same week, by the same hand, three commits apart, and each was correct in
its own layer:

    872   LTChar.__init__  -> glyphname_reliable(self.glyphname, …)   [pdfminer]
    876   docmodel_six     -> decode bytes at the GlyphNode           [too late]

*Fixing a type at the point of USE does not fix it; fix it at the point it
becomes a value.* 878 decodes where the name becomes an attribute, so no
consumer has to know — the same rule the glyph-identity fork follows for
everything else it exposes.

**And a diagnostic that was missing because nothing had needed it yet.** The
partial-read record held the message and not the traceback, so locating the
frame in a 1,200-page book meant twenty minutes of re-provoking the failure
before the question could be asked. `LAST_READ_TRACEBACK` now keeps it. A
recorded reason that cannot be acted on is a half-recorded reason.
