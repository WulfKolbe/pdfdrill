"""The bridge must not serve a UI it cannot talk to, in silence.

Reported from a real session (2026-10-22): "I see the full UI, but I can not
enter anything" — no connection chip, and the REPL's banner and history both
present in the terminal. The protocol was working end to end (verified: the
bridge sends `hello` → `output` → `ready` and round-trips a command); the page
was a PRE-`#cmdline` copy of drillui_term.html, which drove xterm's own stdin.
There was no element to type into.

Three stale copies live on that machine, each next to its own bridge, and
`tools/DRILLUI.md` has said since August that there is "exactly ONE canonical
copy" — enforced by nothing.

What made it silent is the shape worth keeping a test for. The stale-tab guard
works by stamping `__DRILLUI_UI_VERSION__` into the served page and comparing it
in `hello`; the client's condition is

    msg.uiVersion && window.__DRILLUI_UI_VERSION && msg.uiVersion !== window…

so a page too OLD to contain the placeholder is never stamped, the condition is
false, and the guard says nothing. **The guard was blind exactly when the UI was
most stale** — a check that cannot fail for the worst case.

The bridge now checks the page it is about to serve against the markers this
protocol needs, names the file in its banner, and injects a plain-HTML notice
(no script, no xterm, no WebSocket needed to see it).
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "tools" / "drillui_bridge.ts"
UI = ROOT / "tools" / "drillui_term.html"


def _contract() -> list[str]:
    """The markers the bridge requires, read from the bridge itself.

    Read, not duplicated: a copy here would drift, and a drifted copy of a
    contract is worse than no copy — it passes while checking the wrong thing.
    """
    src = BRIDGE.read_text(encoding="utf-8")
    block = re.search(r"const UI_CONTRACT[^=]*=\s*\[(.*?)\n\];", src, re.S)
    assert block, "the bridge no longer declares UI_CONTRACT"
    return re.findall(r"marker:\s*[\"'](.+?)[\"']\s*,", block.group(1))


def test_the_bridge_declares_what_the_ui_must_carry():
    markers = _contract()
    assert len(markers) >= 3, f"UI_CONTRACT shrank to {markers!r}"
    assert "__DRILLUI_UI_VERSION__" in markers, (
        "the stale-tab stamp is not required, so a page that cannot be told it "
        "is out of date would be served without a word")
    assert any("cmdline" in m for m in markers), (
        "nothing requires the command line the editor reads — the exact element "
        "whose absence produced 'I can not enter anything'")


def test_the_canonical_ui_satisfies_it():
    """The other direction: the shipped page must pass its own bridge's check,
    or every launch would cry wolf."""
    ui = UI.read_text(encoding="utf-8")
    missing = [m for m in _contract() if m not in ui]
    assert not missing, (
        f"tools/drillui_term.html is missing {missing!r} — the bridge would "
        f"serve it with a red notice on every launch")


def test_no_other_copy_of_the_ui_is_reachable_from_the_repo():
    """DRILLUI.md's "exactly ONE canonical copy", as an assertion. A second copy
    inside the repo is the next stale UI someone launches."""
    copies = [p for p in ROOT.rglob("drillui_term.html")
              if ".git" not in p.parts and p != UI]
    assert not copies, (
        "a second drillui_term.html inside the repo: "
        + ", ".join(str(p.relative_to(ROOT)) for p in copies))


_NEEDS_BUN = pytest.mark.skipif(
    shutil.which("bun") is None
    and not (Path.home() / ".bun" / "bin" / "bun").is_file(),
    reason="the bridge is Bun; no bun on this machine")


def _serve(tmp_path, html: str, port: int):
    """Run the real bridge over `html` and return (page, launch banner)."""
    import time
    import urllib.request
    bun = shutil.which("bun") or str(Path.home() / ".bun" / "bin" / "bun")
    for f in ("drillui_bridge.ts", "drillui_net.ts", "drillui_chat.py"):
        shutil.copy(ROOT / "tools" / f, tmp_path / f)
    (tmp_path / "drillui_term.html").write_text(html, encoding="utf-8")
    proc = subprocess.Popen(
        [bun, "drillui_bridge.ts", "--port", str(port), "--no-open"],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    page = ""
    try:
        for _ in range(40):                       # up to ~8 s for Bun to listen
            time.sleep(0.2)
            try:
                page = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=2).read().decode()
                break
            except Exception:                     # noqa: BLE001
                if proc.poll() is not None:
                    break
    finally:
        proc.terminate()
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = "", ""
    return page, (err or "") + (out or "")


#: The minimal shape of every June copy: a terminal and no command line.
STALE_UI = ("<!doctype html><html><body><div id='terminal'></div>"
            "<span class='chip' id='conn'></span></body></html>")

#: Compliant, and deliberately SINGLE-quoted. The first version of the check
#: matched `id="conn"` as a literal substring and reported it missing from a
#: page that had `id='conn'` — a check that trips on quoting style sends
#: someone hunting for an element that is right there.
FRESH_UI = ("<!doctype html><html><head><script>"
            "window.__DRILLUI_UI_VERSION = '__DRILLUI_UI_VERSION__';</script>"
            "</head><body><div id='terminal'></div><span id='conn'></span>"
            "<input id='cmdline'></body></html>")


@_NEEDS_BUN
def test_a_compliant_ui_is_served_without_a_word(tmp_path):
    """The other half: a check that cries wolf gets ignored, and then the real
    mismatch is ignored with it."""
    page, banner = _serve(tmp_path, FRESH_UI, 8825)
    assert page, "the bridge never served the page"
    assert "NOT the UI this bridge speaks to" not in page, (
        "a COMPLIANT ui was served with a mismatch notice")
    assert "DOES NOT MATCH" not in banner, (
        "the launch banner cried wolf over a compliant ui:\n" + banner[-800:])


@_NEEDS_BUN
def test_a_stale_ui_gets_a_visible_notice_not_silence(tmp_path):
    """BEHAVIOUR, with the real bridge and a real stale page.

    The page used here is the minimal shape that reproduced the report: a
    document with a terminal div and NO `#cmdline`, the way every June copy
    looks. It must come back carrying the notice.
    """
    page, banner = _serve(tmp_path, STALE_UI, 8824)
    assert page, "the bridge never served the page"
    assert "NOT the UI this bridge speaks to" in page, (
        "a stale UI was served with no notice — the silent failure is back")
    assert "cmdline" in page, "the notice does not name the missing element"
    assert "DOES NOT MATCH THIS BRIDGE" in banner, (
        "the launch banner said nothing about the mismatch:\n" + banner[-800:])
    assert "id=\"conn\"" not in banner.split("missing")[-1].split("\n")[0], (
        "the banner reports `id=\"conn\"` missing from a page that has "
        "`id='conn'` — the check is matching the quoting, not the element")


# --------------------------------------------------------------------------- #
#  The case the served-page notice cannot reach: a tab left OPEN.
#
#  `no-store` stops HTTP caching and does nothing to a page already loaded —
#  it keeps running its old JS and reconnects happily, so it never sees a
#  server-side banner. The version guard cannot catch the worst version of
#  that either: a page old enough to lack the stamp compares `undefined` and
#  stays quiet.
#
#  So the current UI announces itself on connect, and the bridge treats SILENCE
#  as the signal. The warning goes out as terminal output, the one channel every
#  drillui vintage renders — the reporting session could read the REPL banner
#  and its own history perfectly well; it just had nothing to type into.
# --------------------------------------------------------------------------- #

_WS_PROBE = r"""
const mode = process.argv[2];
const ws = new WebSocket("ws://127.0.0.1:" + process.argv[3] + "/ws");
let warned = false;
ws.onopen = () => { if (mode === "identify")
  ws.send(JSON.stringify({ type: "client", uiVersion: "whatever", build: "x" })); };
ws.onmessage = (e) => {
  const m = JSON.parse(String(e.data));
  if (m.type === "output" && String(m.data).includes("OLD drillui")) warned = true;
};
setTimeout(() => { console.log(String(warned)); process.exit(0); }, 4200);
"""


def _tab_warned(tmp_path, mode: str, port: int) -> bool:
    import time
    bun = shutil.which("bun") or str(Path.home() / ".bun" / "bin" / "bun")
    for f in ("drillui_bridge.ts", "drillui_net.ts", "drillui_chat.py",
              "drillui_term.html"):
        shutil.copy(ROOT / "tools" / f, tmp_path / f)
    (tmp_path / "probe.ts").write_text(_WS_PROBE, encoding="utf-8")
    proc = subprocess.Popen(
        [bun, "drillui_bridge.ts", "--port", str(port), "--no-open"],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(1.5)
        r = subprocess.run([bun, "probe.ts", mode, str(port)], cwd=tmp_path,
                           capture_output=True, text=True, timeout=30)
        assert r.stdout.strip() in ("true", "false"), (
            f"the probe did not report: {r.stdout!r} {r.stderr[-300:]!r}")
        return r.stdout.strip() == "true"
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@_NEEDS_BUN
def test_a_tab_that_never_identifies_itself_is_warned_in_its_terminal(tmp_path):
    assert _tab_warned(tmp_path, "silent", 8841), (
        "a tab that never said what it was got no warning — a left-open stale "
        "tab is exactly the case the served-page notice cannot reach")


@_NEEDS_BUN
def test_a_tab_that_identifies_itself_is_left_alone(tmp_path):
    """Not merely 'it warns': it must not warn the current UI on every connect,
    or the warning becomes wallpaper."""
    assert not _tab_warned(tmp_path, "identify", 8842), (
        "a tab that identified itself was warned anyway")


@_NEEDS_BUN
def test_the_shipped_ui_identifies_itself():
    """And the page we ship must be the kind that speaks."""
    ui = UI.read_text(encoding="utf-8")
    assert 'type:"client"' in ui.replace(" ", ""), (
        "tools/drillui_term.html does not announce itself on connect, so the "
        "bridge would warn every current tab")
