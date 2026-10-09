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

VOLUMES = [Path.home() / "Downloads" / f"{n}.pdf" for n in (
    "978-3-032-36023-6", "978-3-032-36033-5",
    "978-3-032-36039-7", "978-3-032-36042-7")]
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
