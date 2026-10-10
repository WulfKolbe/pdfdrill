"""898 — a volume is an archive, and its papers are its entries.

The real volumes (four Springer ICDAR 2026 parts, 401 MB) are not shipped, so
the tests that need one skip when they are absent, as `test_docmodel_six.py`
does for its corpus PDFs. The pure logic — the opener regex, the folio reader,
the selector, the page accounting — is held here without any PDF, because each
of those was wrong once in a way that produced a plausible answer.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pdfdrill import volume

#: 899 — A VOLUME MOVES. `doclock._autofolder` promotes a document into
#: `<dir>/<stem>/<stem>.pdf` the first time a write command touches it where a
#: second document sits beside it (854), and ~/Downloads holds all four parts.
#: So the first `pdfdrill profile` on a volume took it out of the one place
#: these fixtures looked, and every gate below — the member count against the
#: publisher's deposit, the folio check, the page accounting — would have
#: SKIPPED from then on, reporting green while checking nothing. Both layouts
#: are looked for, flat first.
_NAMES = ("978-3-032-36023-6", "978-3-032-36033-5",
          "978-3-032-36039-7", "978-3-032-36042-7")


def _volume(name: str) -> Path:
    """The volume as it lies today: flat in ~/Downloads, or in its own folder."""
    d = Path.home() / "Downloads"
    flat, folded = d / f"{name}.pdf", d / name / f"{name}.pdf"
    return folded if (folded.is_file() and not flat.is_file()) else flat


VOLUMES = [_volume(n) for n in _NAMES]
#: members per volume, as the publisher deposited them at Crossref
EXPECT = {"978-3-032-36023-6": 40, "978-3-032-36033-5": 41,
          "978-3-032-36039-7": 41, "978-3-032-36042-7": 26}
HAVE = [p for p in VOLUMES if p.is_file()]
needs_volume = pytest.mark.skipif(not HAVE, reason="no ICDAR 2026 volume here")


# --- the opener footer -----------------------------------------------------

def test_a_line_break_inside_the_doi_is_tolerated():
    """`_\\s*` is not decoration. A line-break artefact put a space between the
    underscore and the chapter number on 978-3-032-36039-7_28, and without the
    tolerance that volume reported 40 members where the publisher deposited
    41 — one member lost, silently, in a listing that looked complete."""
    broken = "https://doi.org/10.1007/978-3-032-36039-7_ 28"
    got = volume._OPENER.findall(broken)
    assert got == [("10.1007/978-3-032-36039-7_ 28", "978-3-032-36039-7", "28")]


def test_the_printed_range_is_read_from_the_same_footer():
    line = ("G. A. Fink et al. (Eds.): ICDAR 2026, LNCS 16974, "
            "pp. 469–485, 2027.")
    m = volume._RANGE.search(line)
    assert (int(m.group(1)), int(m.group(2))) == (469, 485)


def test_only_the_first_page_carrying_a_doi_opens_that_member():
    """A member's DOI appears again in sibling papers' reference lists. A bare
    DOI search found 71 members in a 40-member volume; the opener is the FIRST
    page that carries it."""
    pages = ["front matter",
             "https://doi.org/10.1007/x_1 pp. 3-19",
             "body",
             "cited: https://doi.org/10.1007/x_1 again",
             "https://doi.org/10.1007/x_2 pp. 20-37"]
    found = volume._openers(pages)
    assert found[("x", 1)][0] == 2
    assert found[("x", 2)][0] == 5


def test_the_volume_is_the_stem_that_opens_the_most_members():
    """A volume's pages name sibling volumes too. The volume is the one whose
    members open here."""
    found = {("mine", 1): (2, 1, 9, "d"), ("mine", 2): (10, 10, 19, "d"),
             ("other", 7): (5, 1, 9, "d")}
    assert volume._dominant_stem(found) == "mine"
    assert volume._dominant_stem({}) is None


# --- the folio reader ------------------------------------------------------

def test_the_folio_is_sought_in_the_first_three_lines():
    """A verso page puts the number first; a recto page puts the running-head
    title first and the number second. Reading only the first line found the
    folio on 26 of 40 members and looked like a 14-member mismatch."""
    assert volume.folio_of("72\nY. Xu et al.\nbody") == 72
    assert volume.folio_of("Spatially-Grounded Gaussian-Prior Attention\n19\n"
                           "30. Mahdavi, M.") == 19
    assert volume.folio_of("Document Forensics and Provenance") is None


# --- the selector ----------------------------------------------------------

def test_the_selector_is_a_regex_over_titles_and_refuses_a_bad_one():
    data = {"members": [{"title": "A Fast Table Recognizer"},
                        {"title": "Handwritten Mathematical Expressions"},
                        {"title": None}]}
    assert len(volume.select(data, "table")) == 1
    assert len(volume.select(data, "mathemat")) == 1
    assert volume.select(data, "zzz") == []
    with pytest.raises(volume.VolumeError):
        volume.select(data, "(unclosed")


def test_a_member_with_no_established_range_is_refused_not_guessed(tmp_path):
    """"A boundary no source establishes is absent, not guessed." A member
    whose opener carried no printed range has no length, and inventing one
    from the next member's first page is exactly the rule measured to
    over-count by the part-divider pages."""
    data = {"volume": {"identifier_stem": "x", "pdf_pages": 10}}
    member = {"member": 3, "title": "T", "pdf_first_page": 4,
              "pdf_last_page": None}
    with pytest.raises(volume.VolumeError) as e:
        volume.unpack(tmp_path / "v.pdf", data, member, tmp_path)
    assert "absent, not guessed" in str(e.value)


# --- the real volumes ------------------------------------------------------

@needs_volume
def test_every_member_the_publisher_deposited_is_found():
    for pdf in HAVE:
        data = volume.build(pdf)
        assert data["volume"]["members"] == EXPECT[pdf.stem], pdf.name
        assert data["volume"]["identifier_stem"] == pdf.stem


@needs_volume
def test_every_page_is_accounted_for():
    """front matter + pages inside members + pages inside none == the page
    count. This is the archive's own listing: an entry, or a directory."""
    for pdf in HAVE:
        data = volume.build(pdf)
        assert data["volume"]["accounted"] is True, pdf.name


@needs_volume
def test_the_printed_folio_confirms_every_computed_last_page():
    """The length comes from the opener footer; the check comes from the page.
    148 of 148 on the four volumes."""
    bad = []
    for pdf in HAVE:
        for m in volume.build(pdf)["members"]:
            if m["folio_agrees"] is not True:
                bad.append((pdf.stem, m["member"], m["folio_on_last_page"],
                            m["printed_last_page"]))
    assert bad == []


@needs_volume
def test_the_last_page_is_not_the_next_members_first_minus_one():
    """The trap this module exists to avoid. Springer prints a part divider
    before each topical section and strips its blank verso, so divider pages
    belong to no member. On volume I that rule over-counts 10 members."""
    pdf = next((p for p in HAVE if p.stem == "978-3-032-36023-6"), None)
    if pdf is None:
        pytest.skip("needs volume I, the one with part dividers")
    members = volume.build(pdf)["members"]
    over = [m["member"] for m, nxt in zip(members, members[1:])
            if m["pdf_last_page"] != nxt["pdf_first_page"] - 1]
    assert over, "volume I has part dividers; some member must end early"
    assert len(volume.build(pdf)["orphans"]) == 12


@needs_volume
def test_a_listing_round_trips(tmp_path, monkeypatch):
    pdf = HAVE[0]
    data = volume.build(pdf)
    monkeypatch.setattr(volume, "listing_path",
                        lambda _p: tmp_path / "v.members.json")
    volume.write_listing(pdf, data)
    again = volume.read_listing(pdf)
    assert again == json.loads(json.dumps(data))


@needs_volume
def test_one_member_becomes_its_own_document(tmp_path):
    pytest.importorskip("pikepdf")
    pdf = HAVE[0]
    data = volume.build(pdf)
    m = data["members"][0]
    rec = volume.unpack(pdf, data, m, tmp_path)
    out = Path(rec["pdf"])
    assert out.is_file()
    import pikepdf
    with pikepdf.open(out) as p:
        assert len(p.pages) == m["pdf_pages"]
        # the member must NOT inherit the volume's title: all 148 members of a
        # proceedings volume would otherwise carry one name, in a tool whose
        # titles become bibkeys.
        assert str(p.docinfo.get("/Title")) == m["title"]
        assert m["doi"] in str(p.docinfo.get("/Subject"))
    prov = json.loads((out.parent / "volume-provenance.json")
                      .read_text(encoding="utf-8"))
    assert prov["volume_pdf"] == str(pdf)
    assert prov["pdf_first_page"] == m["pdf_first_page"]


# --- the roll-up (899) -----------------------------------------------------
#: `members` says which works a volume holds, `profile` what is on each page.
#: The roll-up is their JOIN and the join key is the page NUMBER, so every
#: test here is about a frame: whose pages, counted against what denominator.

def _listing(*spans):
    """A listing of members at the given (member, first, last) PDF spans."""
    return {"volume": {"pdf_pages": 100, "members": len(spans)},
            "members": [{"member": n, "title": f"Paper {n}", "doi": None,
                         "pdf_first_page": f, "pdf_last_page": l,
                         "pdf_pages": (l - f + 1) if f and l else None}
                        for (n, f, l) in spans]}


def _profile(pages=100, **where):
    return {"pages": pages, "page_props": {},
            "where": {k: list(v) for k, v in where.items()}}


def test_a_property_outside_the_members_range_is_not_its_property():
    """The join is an intersection. A page carrying an equation two pages
    after the member ends belongs to the next member or to no one."""
    r = volume.rollup(_listing((1, 10, 19), (2, 20, 29)),
                      _profile(equation=[9, 10, 15, 21, 30]))
    m1, m2 = r["members"]
    assert m1["props"]["equation"]["pages"] == 2          # 10 and 15
    assert m2["props"]["equation"]["pages"] == 1          # 21 only
    assert r["outside_every_member"] == {"equation": 2}   # 9 and 30


def test_the_denominator_travels_with_every_count():
    """`12 pages carry an equation` is a different claim in a 17-page paper
    and in a 700-page volume, so the member's own span is stored beside the
    count and never left to the reader to reconstruct."""
    r = volume.rollup(_listing((1, 10, 26)), _profile(equation=[11, 12]))
    hit = r["members"][0]["props"]["equation"]
    assert (hit["pages"], hit["of"], hit["first"]) == (2, 17, 11)
    assert r["members"][0]["pages_total"] == 17


def test_a_member_without_an_established_range_gets_nothing_guessed():
    """898's rule, kept here: a boundary no source establishes is absent. A
    member whose last page is unknown cannot be profiled, and an empty
    property dict would claim it was profiled and found nothing."""
    r = volume.rollup(_listing((1, 10, None)), _profile(equation=[11]))
    m = r["members"][0]
    assert m["props"] is None
    assert "not established" in m["props_source"]
    #: and its pages are not quietly claimed as belonging to no member either
    assert r["outside_every_member"] == {"equation": 1}


def test_members_carrying_and_pages_carrying_are_different_numbers():
    """The shape that made the first trailer dishonest: on ICDAR 2026 part IV
    `equation` is on 19 of 26 members and only 40 of 470 pages, so reading
    `those members` reads 329 pages to reach 40. Both numbers are kept."""
    r = volume.rollup(_listing((1, 1, 10), (2, 11, 20), (3, 21, 30)),
                      _profile(equation=[5, 15]))
    b = r["by_property"]["equation"]
    assert b["pages_carrying"] == 2
    assert b["members"] == 2
    assert b["pages_in_those_members"] == 20
    assert b["pages_in_volume"] == 2


def test_decision_relevant_properties_come_first_and_none_is_dropped():
    got = volume._ordered({"coloured-fill", "equation", "zzz-new", "frame"})
    assert got[:3] == ["equation", "frame", "coloured-fill"]
    assert "zzz-new" in got


def test_an_absent_profile_names_the_command_that_makes_one(tmp_path):
    pdf = tmp_path / "v.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(volume.VolumeError) as e:
        volume.read_profile(pdf, 100)
    assert "pdfdrill profile" in str(e.value)


def test_a_profile_of_a_different_document_is_refused(tmp_path):
    """The page number is the key the roll-up joins on. A profile of 99 pages
    against a listing of 100 is not a near miss, it is another document — and
    the rows it would produce all look plausible."""
    pdf = tmp_path / "v.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    volume.profile_path(pdf).write_text(json.dumps(_profile(pages=99)))
    with pytest.raises(volume.VolumeError) as e:
        volume.read_profile(pdf, 100)
    assert "different document" in str(e.value)
    #: and it is readable when the counts agree
    volume.profile_path(pdf).write_text(json.dumps(_profile(pages=100)))
    assert volume.read_profile(pdf, 100)["pages"] == 100


def test_a_profile_older_than_the_document_is_never_silently_served(tmp_path):
    import os
    pdf = tmp_path / "v.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    prof = volume.profile_path(pdf)
    prof.write_text(json.dumps(_profile()))
    os.utime(prof, (1, 1))                      # the reading predates the PDF
    with pytest.raises(volume.VolumeError) as e:
        volume.read_profile(pdf, 100)
    assert "older than" in str(e.value)


def test_the_rollup_round_trips(tmp_path):
    pdf = tmp_path / "v.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    data = volume.rollup(_listing((1, 1, 10)), _profile(equation=[2]))
    volume.write_rollup(pdf, data)
    assert volume.read_rollup(pdf) == data


_IV = _volume("978-3-032-36042-7")
_has_iv_profile = pytest.mark.skipif(
    not (volume.profile_path(_IV).is_file()
         and volume.listing_path(_IV).is_file()),
    reason="no profiled ICDAR 2026 volume here (profile takes ~17 min)")


@_has_iv_profile
def test_on_a_real_volume_no_page_is_counted_twice_or_lost():
    """Every page a property was established on lands in exactly one member
    or in none: the members partition the body, so the counts must add up."""
    listing = volume.read_listing(_IV)
    prof = volume.read_profile(_IV, listing["volume"]["pdf_pages"])
    r = volume.rollup(listing, prof)
    for k, pages in prof["where"].items():
        inside = sum((m["props"] or {}).get(k, {}).get("pages", 0)
                     for m in r["members"])
        outside = r["outside_every_member"].get(k, 0)
        assert inside + outside == len(pages), k


@_has_iv_profile
def test_on_a_real_volume_every_count_is_within_its_members_own_span():
    listing = volume.read_listing(_IV)
    r = volume.rollup(listing, volume.read_profile(_IV))
    for m in r["members"]:
        for k, hit in (m["props"] or {}).items():
            assert hit["of"] == m["pages_total"], (m["member"], k)
            assert 0 < hit["pages"] <= hit["of"], (m["member"], k)
            assert m["pdf_first_page"] <= hit["first"] <= m["pdf_last_page"]


def test_a_pdf_holding_one_work_is_answered_not_formatted(tmp_path):
    """T-0004's contract names it: a PDF with one work. The first draft
    printed a table header with no rows, said "on every member, so it selects
    nothing" about every property (0 == 0), and advised `unpack --match` on a
    document with nothing to unpack."""
    from pdfdrill.commands import cmd_memberprofile
    pdf = tmp_path / "one-paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    volume.write_listing(pdf, {"volume": {"pdf_pages": 11, "members": 0},
                               "members": [], "orphans": []})
    volume.profile_path(pdf).write_text(json.dumps(
        {"pages": 11, "page_props": {"2": {"equation": "x"}},
         "where": {"equation": [2, 3]}}))
    out = cmd_memberprofile(pdf)
    assert "holds ONE work" in out
    assert "unpack" not in out
    assert "selects nothing" not in out


def test_the_time_a_prerequisite_costs_is_declared_not_guessed():
    """899 — `ensure` is silent on purpose, which is right for a fast step and
    a defect for a slow one: `profile` reads every glyph on every page and
    drillui appends `--ensure` to every command (896), so the only route to
    `memberprofile` was a 17-minute freeze with nothing on screen."""
    from pdfdrill import planner
    note = planner._slow_note("profile")
    assert note and "glyph" in note
    assert planner._slow_note("members") is None
