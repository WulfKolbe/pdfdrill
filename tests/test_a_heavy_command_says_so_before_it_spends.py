r"""A command that costs minutes was indistinguishable from one that costs
nothing, and `drill` — the shallow entry point — ran one of them unasked.

The SKILL's first promise is "Always starts shallow (pdfinfo, TOC, abstract) and
escalates only when the question demands it", and its rule 2 and its "reach for
the cheapest sufficient tool" section say it twice more. All three are PROSE.
Measured 2026-10-29 against the manifest: of 168 commands, 11 declare `network`
(the money axis) and ONE declared `slow` (the time axis). So the planner could
order free-before-paid and had nothing at all to order cheap-before-heavy, and
`pdfdrill drill` spent 116.88 s of 120.73 s in a pass that placed nothing.

The field was already there. `slow:` is read by `planner._slow_note` and printed
by `--ensure` BEFORE the step runs — built for `profile`, whose 17m19s on a
470-page volume froze drillui with nothing on screen (899). Nothing populated it
for anything else, and nothing failed when a heavy command stayed silent. This
file is what fails.

THE MEASUREMENT BELOW IS THE EVIDENCE, and it is in the test rather than taken
at run time because taking it costs minutes. Cold, fresh copy of the PDF per
command (so the sidecar's "return instantly if the fact is already set" cannot
hide the price), installed entry point, 2016icpr.pdf — 6 pages, A4, born-digital:

    size            0.21 s      links       0.22 s      toc        0.23 s
    abstract        0.23 s      llmtext     0.93 s      rasterize  1.17 s
    report          3.10 s      md --ensure 3.18 s      inspect    3.69 s
    tables          4.50 s      fontid      9.66 s      glyphlines 19.33 s
    profile        21.98 s      geometry --layout       56.84 s
                                  (263.93 s before the imposition fix)

Extrapolating the per-page rate to a 470-page volume is what makes the three
newly-declared commands minutes rather than seconds, which is the bar `slow:`
was written to — `profile` is in it at 3.7 s/page here against the 2 s/page its
own note quotes, so the rate transfers.
"""
import inspect as _inspect
import re

import pytest

from pdfdrill import planner

#: command -> (seconds per page, what a 470-page volume costs, the document)
#: Everything at or above 1 s/page is minutes on a real volume, which is the
#: bar `slow:` exists for. Add a row when you add a pass; the gate below is
#: what makes the row compulsory.
MEASURED_PER_PAGE = {
    "geometry":   (9.47, "74 min", "2016icpr.pdf, --layout, 6 pp, 56.84 s"),
    "profile":    (3.66, "29 min", "2016icpr.pdf, 6 pp, 21.98 s"),
    "glyphlines": (3.22, "25 min", "2016icpr.pdf, 6 pp, 19.33 s"),
    "fontid":     (1.61, "13 min", "2016icpr.pdf, 6 pp, 9.66 s"),
    # below the bar, recorded so the next reader does not re-measure them
    "tables":     (0.75, "6 min",  "2016icpr.pdf, 6 pp, 4.50 s"),
    "inspect":    (0.62, "5 min",  "2016icpr.pdf, 6 pp, 3.69 s"),
    "report":     (0.52, "4 min",  "2016icpr.pdf, 6 pp, 3.10 s"),
    "llmtext":    (0.16, "75 s",   "2016icpr.pdf, 6 pp, 0.93 s"),
    "abstract":   (0.04, "18 s",   "2016icpr.pdf, 6 pp, 0.23 s"),
    "size":       (0.04, "16 s",   "2016icpr.pdf, 6 pp, 0.21 s"),
}

#: The bar, in seconds per page.
SLOW_AT = 1.0


def _manifest():
    return planner.load_manifest()


def _by_name():
    return {c["name"]: c for c in _manifest().get("commands", [])}


@pytest.mark.parametrize("name", sorted(
    n for n, (s, _v, _d) in MEASURED_PER_PAGE.items() if s >= SLOW_AT))
def test_a_command_measured_at_minutes_declares_its_cost(name):
    """THE CASE BUILT TO FAIL: before this, `geometry`, `glyphlines` and
    `fontid` were silent and `geometry` sat in a section called
    "Introspection (fast, no extraction)" at 9.5 s/page."""
    cmd = _by_name()[name]
    note = cmd.get("slow")
    assert note, (
        f"`{name}` costs {MEASURED_PER_PAGE[name][0]} s/page "
        f"({MEASURED_PER_PAGE[name][1]} on a 470-page volume) and the manifest "
        f"says nothing; declare it with `slow:`")
    assert re.search(r"\d", str(note)), (
        f"`{name}`'s cost note must carry a NUMBER — a vague 'this may take a "
        f"while' is what the prose in SKILL.md already said")
    assert planner._slow_note(name), (
        f"`{name}` declares a cost the planner cannot read back")


@pytest.mark.parametrize("name", sorted(
    n for n, (s, _v, _d) in MEASURED_PER_PAGE.items() if s < SLOW_AT))
def test_a_command_measured_in_a_second_is_not_marked_slow(name):
    """The other direction. A warning on every command is a warning on none,
    and `--ensure` prints this note before every step it inserts."""
    assert not _by_name()[name].get("slow"), (
        f"`{name}` is {MEASURED_PER_PAGE[name][0]} s/page — marking it slow "
        f"spends the reader's attention where there is nothing to spend it on")


def test_drill_runs_nothing_that_declares_a_cost():
    r"""THE ENFORCEMENT, and the reason the rest of this file is not decoration.
    `drill` is the one command the SKILL tells a reader to start with, so
    whatever `drill` runs IS the shallow tier. It called
    `cmd_geometry(pdf, layout=True)` — 44 s/page as measured then — which is how
    the promise and the behaviour came apart without anything failing.

    A step that costs minutes may still be REACHED from drill; it has to be
    named, the way a paid lane is named and not run."""
    from pdfdrill import cli
    src = _inspect.getsource(cli._do_drill)
    code = "".join(l for l in src.splitlines(True)
                   if not l.lstrip().startswith("#"))
    ran = set(re.findall(r"\bcmd_(\w+)\s*\(", code))
    by = _by_name()
    for name in sorted(ran):
        note = (by.get(name) or {}).get("slow")
        if not note:
            continue
        # A COST CAN LIVE ON A FLAG. `geometry` is 0.12 s/page as the pdftotext
        # fusion and 9.5 s/page with `--layout`: the same verb, 77x apart. The
        # manifest is per command, so a conditional cost must NAME its flag,
        # and drill is then held to not passing it.
        flags = re.findall(r"--[a-z][a-z-]*", str(note))
        assert flags, (
            f"`drill` runs `{name}`, which the manifest says costs minutes "
            f"unconditionally. Either it stops running it, or the cost note "
            f"names the flag that makes it expensive.")
        for f in flags:
            kw = f.lstrip("-").replace("-", "_")
            if f"{kw}=True" not in code.replace(" ", ""):
                continue                      # it does not ask for the cost
            # IT MAY ASK, HAVING MEASURED THAT IT WOULD CHANGE SOMETHING.
            # "Escalates only when the question demands it" is not "never
            # escalates": a scan whose text match cannot place its objects
            # needs this pass. What the original defect was is passing the
            # flag with nothing consulted — 116.88 s of a 120.73 s drill on a
            # document where the pass then reported "boxed 0 of 0". So the
            # flag is allowed only beside a measurement of need.
            assert "candidate" in code, (
                f"`drill` passes {f} to `{name}`, which the manifest prices "
                f"at minutes, without measuring whether it would change "
                f"anything. Ask first — see layoutgeom.candidate_count.")
    # and the one it stopped running is still named, so a reader can ask for it
    assert "geometry --layout" in src, (
        "the pass drill no longer runs must be named in its output")


def test_the_manifest_declares_a_cost_for_more_than_one_command():
    """The state this file was written in: one command out of 168 carried the
    field, so the axis existed and said nothing. A regression that empties it
    again must fail here rather than in a user's afternoon."""
    declared = {c["name"] for c in _manifest().get("commands", [])
                if c.get("slow")}
    assert len(declared) >= 4, declared
    assert "profile" in declared, "the original, and the shape to copy"


def test_every_declared_cost_states_a_per_page_RATE():
    r"""A total is not transferable and a rate is. `profile`'s original note
    got this right — "about 2 s/page, so 17 min on a 470-page volume" — and
    `planner._slow_rate` reads that convention back so `steps` can print the
    price beside the command. A note without a rate would make `steps` fall
    back to the word "minutes", which is what prose already said."""
    import re as _re
    for cmd in _manifest().get("commands", []):
        note = cmd.get("slow")
        if not note:
            continue
        assert _re.search(r"[\d.]+\s*s/page", str(note)), (
            f"`{cmd['name']}`'s cost note states no N s/page rate: {note!r}")
        assert "/page" in (planner._slow_rate(cmd["name"]) or ""), cmd["name"]


def test_the_price_is_on_screen_where_the_choice_is_made(tmp_path):
    r"""`pdfdrill steps inspect` offered `glyphlines` as the free alternative
    to the paid `mathpix` and said nothing about its cost — so an operator
    comparing them saw one axis. `--ensure` prints the note, but that is after
    the decision, while the time is being spent."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    msg = planner.describe("inspect", pdf)
    assert "glyphlines" in msg, msg
    assert "s/page" in msg, (
        "the free alternative's price is missing from the message that "
        "recommends it:\n" + msg)


def test_a_rate_that_only_applies_with_a_flag_names_the_flag():
    r"""`steps inspect` printed `geometry (9.5 s/page)` for a chain that runs
    `geometry` WITHOUT `--layout`, where it is 0.12 s/page — a price quoted
    for work the chain was not going to do. Overstating a cost drives an
    operator off a cheap step as surely as understating one drives them onto
    an expensive one."""
    rate = planner._slow_rate("geometry")
    assert rate == "9.5 s/page with --layout", rate
    # and an unconditional cost stays plain
    assert planner._slow_rate("glyphlines") == "3.2 s/page"
    assert planner._slow_rate("profile") == "2 s/page"
    assert planner._slow_rate("size") is None
