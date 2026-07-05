#!/usr/bin/env python3
"""
drillui_chat — an "ask the document" proxy / mini LLM chatbot.

This is the external drillui frontend (a Headroom-style proxy): it NEVER imports
pdfdrill — it talks to it only as a subprocess, exactly like the rest of drillui.
For each user question it:

  1. asks pdfdrill to TRANSFORM the question into grounded context
     (`pdfdrill retrieve <doc> "<q>" --json` → the top-k relevant drilled units +
     a ready prompt that cites them by id — the question-transformation step);
  2. PROXIES that enriched prompt to an LLM using the same keyless fallback trick
     pdfdrill uses internally — a headless `claude -p ... --output-format json`;
  3. stores the Q&A back in pdfdrill's own structures
     (`pdfdrill chatlog <doc> --question … --answer … --units …` → a transcript
     line + the answer as a kitem in the semantic graph).

So the *knowledge* (retrieval + storage) lives in pdfdrill and is reused; only
the conversation loop + the LLM call live here. This is a temporary home for the
question transformation until it becomes a SKILL.

Usage:
    drillui_chat.py <doc> [-q "question"]      # one-shot, or a REPL with no -q
    drillui_chat.py <doc> --src src            # dev: sets PYTHONPATH=src
    drillui_chat.py <doc> --model claude-haiku-4-5-20251001 --k 10

Stdlib only.
"""
from __future__ import annotations

import argparse
import atexit
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path

try:                       # line editing + arrow-key history for input()
    import readline        # noqa: F401  (importing it is what hooks input())
except ImportError:        # pragma: no cover
    readline = None

# Words that quit the REPL — typed bare or with a leading ':'. Generous on
# purpose: quit/exit/stop/q/bye all work, so you never get stuck.
_QUIT = {"quit", "exit", "stop", "q", "bye", "qui", ":quit", ":exit", ":stop",
         ":q", ":bye"}

# pdfdrill commands that understand a COMBINED store (everything else needs a
# single PDF and would produce nonsense on the .docpack).
_COMBINED_OK = {"bibtex"}


# This script lives at <repo>/tools/drillui_chat.py, so pdfdrill is ALWAYS
# right here: <repo>/src/pdfdrill (import root) and <repo>/pdfdrill (the wrapper
# that exports PYTHONPATH=src for you). We locate it from our OWN path instead
# of depending on an install or a hand-passed --src — the source is never lost.
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _pdfdrill_cmd(args: argparse.Namespace) -> tuple[list[str], dict, str]:
    """Resolve how to invoke pdfdrill. Returns (argv_base, env, description).

    Order: explicit --pdfdrill override > explicit --src > the in-repo src tree
    (self-located from this file) > the in-repo ./pdfdrill wrapper > an installed
    `pdfdrill` console script on PATH. Raises a clear error only if NONE exist —
    which, from inside the repo, cannot happen.
    """
    import shutil
    env = dict(os.environ)
    # libpostal (built into /usr/local/lib) isn't on the default linker path;
    # mirror the ./pdfdrill wrapper so libpostal-using subcommands don't break.
    env["LD_LIBRARY_PATH"] = "/usr/local/lib" + os.pathsep + env.get("LD_LIBRARY_PATH", "")

    def _with_src(src: Path) -> tuple[list[str], dict, str]:
        e = dict(env)
        e["PYTHONPATH"] = str(src) + os.pathsep + e.get("PYTHONPATH", "")
        return [sys.executable, "-m", "pdfdrill"], e, f"python -m pdfdrill (PYTHONPATH={src})"

    if args.pdfdrill:                                  # explicit override
        return args.pdfdrill.split(), env, f"override: {args.pdfdrill}"
    if args.src:                                       # explicit --src DIR
        return _with_src(Path(args.src).resolve())

    src = _REPO_ROOT / "src"
    if (src / "pdfdrill" / "__init__.py").exists():    # the obvious answer
        return _with_src(src)

    wrapper = _REPO_ROOT / "pdfdrill"
    if wrapper.exists() and os.access(wrapper, os.X_OK):
        return [str(wrapper)], env, f"wrapper: {wrapper}"

    found = shutil.which("pdfdrill")
    if found:                                          # pip-installed console script
        return ["pdfdrill"], env, f"installed: {found}"

    raise SystemExit(
        f"error: could not locate pdfdrill. Looked for {src}/pdfdrill, "
        f"{wrapper}, and a `pdfdrill` on PATH. Pass --src <dir> or "
        f"--pdfdrill '<cmd>'.")


def _run(argv: list[str], env: dict, timeout: float = 180.0) -> str:
    p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(argv[:3])}… exited {p.returncode}: "
                           f"{(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout


def _extract_json(text: str) -> dict | None:
    """The single JSON object in pdfdrill's output (first '{' … last '}'),
    tolerant of leading prose / pretty-printing. None if there isn't one."""
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(text[i:j + 1])
    except json.JSONDecodeError:
        return None


def retrieve(base: list[str], env: dict, doc: str, q: str, k: int) -> dict:
    out = _run(base + ["retrieve", doc, q, "--k", str(k), "--json"], env)
    obj = _extract_json(out)
    if obj is None:
        # cmd_retrieve returns PROSE (no JSON) when the doc has no model, e.g.
        # "No model for X — run `pdfdrill model`/`markdown` first." Surface THAT,
        # not an opaque parse error.
        raise RuntimeError(out.strip() or "pdfdrill retrieve returned no JSON")
    return obj


def ask_llm(prompt: str, *, claude: str, model: str | None, timeout: float) -> str:
    cmd = [claude, "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"claude -p exited {p.returncode}: {p.stderr.strip()[:200]}")
    env = json.loads(p.stdout)
    if env.get("is_error"):
        raise RuntimeError(f"claude -p error: {env.get('result')}")
    return (env.get("result") or "").strip()


def chatlog(base: list[str], env: dict, doc: str, q: str, a: str,
            units: list[str], model: str) -> str:
    return _run(base + ["chatlog", doc, "--question", q, "--answer", a,
                        "--units", ",".join(units), "--model", model or "claude"], env)


def _save_history(rl, path) -> None:
    try:
        rl.write_history_file(path)
    except Exception:  # noqa: BLE001
        pass


def load_commands(base, env, timeout: float) -> dict:
    """{command_name: first_positional_type} from `pdfdrill skill --json`, so the
    REPL can run any pdfdrill subcommand by name and know whether to auto-insert
    the open doc. Empty dict if pdfdrill can't report them (bare-command routing
    then just falls back to treating input as a question; `!cmd` still works)."""
    try:
        out = _run(base + ["skill", "--json"], env, timeout=timeout)
    except Exception:  # noqa: BLE001
        return {}
    obj = _extract_json(out)
    cmds = (obj or {}).get("commands") or []
    table = {}
    for c in cmds:
        pos = c.get("positionals") or []
        table[c["name"]] = (pos[0].get("type") if pos else None)
    return table


def _command_argv(cmds: dict, doc: str, cmd: str, rest: list[str]) -> list[str]:
    """Build the pdfdrill argv for a subcommand, auto-inserting the OPEN doc as
    the first positional when the command takes one — so the user never repeats
    the filename. `pdf` positionals always get the doc; `markdown` gets it only
    when the doc is a .md; dir/no-positional commands get the user's args as-is."""
    ptype = cmds.get(cmd)
    if ptype == "pdf" or (cmd == "markdown" and doc.lower().endswith(".md")):
        return [cmd, doc] + rest
    return [cmd] + rest                       # doctor/skill/folder/… : no doc


# Heavy commands need FAR more than the 180s default: a 211-page manual's
# 600-DPI pyramid build, whole-doc OCR, MathPix uploads etc. run for many
# minutes — the old flat timeout KILLED them mid-build (partial tiles, no
# manifest, a dead viewer). Per-command floors, in seconds:
_HEAVY_TIMEOUT = {
    "pyramid": 3600, "ocr": 1800, "mathpix": 1800, "model": 900,
    "folder": 3600, "remath": 3600, "visionocr": 3600, "translate": 1800,
    "svg": 1800, "vision": 1800, "bibfetch": 900, "rasterize": 900,
    "elements": 900, "continuity": 1800, "enhance": 900, "inspect": 1800,
}


def run_command(base, env, cmds: dict, doc: str, line: str, timeout: float) -> str:
    """Run `<cmd> [args]` (with or without a leading '!') as a pdfdrill subcommand
    on the open doc. Heavy commands get their _HEAVY_TIMEOUT floor so a long
    pyramid/OCR build is never killed by the interactive default."""
    parts = line.lstrip("!").split()
    if not parts:
        return "usage: <pdfdrill-subcommand> [args]   e.g. status, mathpix, model"
    eff = max(timeout, _HEAVY_TIMEOUT.get(parts[0], 0))
    return _run(base + _command_argv(cmds, doc, parts[0], parts[1:]), env,
                timeout=eff)


def do_add(base, env, newdoc: str, docs: list, combined: str | None,
           timeout: float, store_dir: str = "") -> tuple[str, str | None]:
    """Add a document to the live chat context. `pdfdrill model` is IDEMPOTENT —
    a doc drilled once (cached PDF + <name>.drill model) is reused, not re-drilled
    — then re-merges ALL docs into one combined store. Returns (new retrieval
    target, combined-store path). On failure leaves the context unchanged."""
    # Expand a leading ~ and any $VARS: pdfdrill is a subprocess, so the shell
    # never saw this path — `~/Scans/x.pdf` is still a literal tilde here and
    # would not resolve. (URLs / arxiv ids contain neither ~ nor $, so untouched.)
    newdoc = os.path.expandvars(os.path.expanduser(newdoc))
    newdoc = _repair_local_doc(newdoc)                     # typo/case correction
    if newdoc in docs:
        print(f"  {newdoc} is already in the context ({len(docs)} doc(s)).")
        return (combined or (docs[0] if docs else None)), combined
    print(f"  adding {newdoc} … (reuses an existing drill; only builds if new)")
    docs.append(newdoc)
    # Ensure EVERY doc in the context has a MODEL (combine needs one). `model` is
    # idempotent — only the new/undrilled docs build. The launch doc may have had
    # only `md` (not a model), which is why combine used to skip it.
    drilled: list[str] = []
    for d in docs:
        try:
            _run(base + ["model", d], env, timeout=max(timeout, 600.0))
            drilled.append(d)
        except Exception as e:                            # noqa: BLE001
            print(f"  could not drill {d}: {e}", file=sys.stderr)
    if not drilled:
        docs.remove(newdoc)
        print("  context unchanged.", file=sys.stderr)
        return (combined or None), combined
    if len(drilled) == 1:                                 # one usable doc — no merge
        print(f"  context: {drilled[0]} (1 document) — ask away.")
        return drilled[0], None
    base_store = (Path(store_dir) / ".drillui_session.docpack") if store_dir \
        else Path(".drillui_session.docpack")
    out = combined or str(base_store)
    try:
        msg = _run(base + ["combine", *drilled, "--out", out, "--force"], env,
                   timeout=max(timeout, 300.0))
    except Exception as e:                                 # noqa: BLE001
        print(f"  combine failed: {e}", file=sys.stderr)
        return (combined or drilled[0]), combined
    print("  " + " ".join(msg.split()))
    print(f"  context spans {len(drilled)} document(s) — ask away.")
    return out, out


def _expand_add_spec(spec: str) -> list:
    """`add` arguments → a flat list of doc tokens.

    Filenames with BLANKS and special characters ("The Everything Kids Giant
    Book of Jokes, … (z-lib.org).pdf") are handled two ways:
      * quote the path shell-style (`add "…​.pdf"` / `add '…​.pdf'`) — tokens
        are split with shlex, so a quoted path is ONE token;
      * or paste it UNQUOTED: when the whole argument line names an existing
        file, it is taken as ONE path (a real filename beats tokenization).
    Otherwise space-separated tokens are taken literally; a `@file` token is
    expanded to the file's lines (one path/URL/arxiv-id per line; blank lines
    and `#` comments skipped). So `add a.pdf b.pdf @more.txt` adds a.pdf,
    b.pdf, and everything in more.txt."""
    import shlex
    # the whole line as one existing file wins (unquoted spaces, parens, …)
    whole = os.path.expanduser(spec.strip())
    if os.path.isfile(whole):
        return [spec.strip()]
    try:
        tokens = shlex.split(spec)
    except ValueError:                                   # unbalanced quote etc.
        tokens = spec.split()
    out: list = []
    for tok in tokens:
        if tok.startswith("@"):
            path = os.path.expanduser(tok[1:])
            try:
                for ln in Path(path).read_text(encoding="utf-8").splitlines():
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        out.append(ln)
            except Exception as e:                          # noqa: BLE001
                print(f"  could not read {path}: {e}", file=sys.stderr)
        else:
            out.append(tok)
    return out


def _suggest_path(path: str) -> str | None:
    """Repair a mistyped LOCAL path segment by segment: at each level, if the
    exact segment is absent, take a case-insensitive match (`DownLoads`→
    `Downloads`) else the closest fuzzy match (`Axe-Fx-II-0wners-Manual.pdf`→
    `…-Owners-Manual.pdf`, difflib cutoff 0.7). Returns the repaired path when it
    exists and differs from the input, else None (never invents a file). A URL /
    bare id has no separator to walk, so it yields None."""
    import difflib
    p = os.path.expandvars(os.path.expanduser(path))
    if os.path.exists(p) or p.startswith(("http://", "https://")):
        return None
    cur = os.sep if os.path.isabs(p) else "."
    segs = [s for s in p.split(os.sep) if s]
    for seg in segs:
        cand = os.path.join(cur, seg)
        if os.path.exists(cand):
            cur = cand
            continue
        try:
            entries = os.listdir(cur)
        except OSError:
            return None
        low = {e.lower(): e for e in entries}
        match = low.get(seg.lower())
        if match is None:
            close = difflib.get_close_matches(seg, entries, n=1, cutoff=0.7)
            match = close[0] if close else None
        if match is None:
            return None
        cur = os.path.join(cur, match)
    if os.path.exists(cur) and os.path.abspath(cur) != os.path.abspath(p):
        return cur
    return None


def _repair_local_doc(newdoc: str) -> str:
    """If `newdoc` is a missing local path with a close on-disk match, print the
    correction and return the repaired path; otherwise return it unchanged."""
    fixed = _suggest_path(newdoc)
    if fixed:
        print(f"  no file at {newdoc}\n  → using {fixed} (closest match).")
        return fixed
    return newdoc


def do_add_many(base, env, newdocs: list, docs: list, combined,
                timeout: float, store_dir: str = ""):
    """Add MANY documents in one pass: append the new ones, drill all (model is
    idempotent — only the undrilled build), combine ONCE. The list/`@file` form
    of `add`; avoids the per-doc re-combine an add-loop would cause."""
    newdocs = [_repair_local_doc(os.path.expandvars(os.path.expanduser(d)))
               if os.sep in d or d.endswith((".pdf", ".md")) else d
               for d in newdocs]
    fresh = [d for d in newdocs if d not in docs]
    if not fresh:
        print(f"  all {len(newdocs)} already in the context ({len(docs)} docs).")
        return (combined or (docs[0] if docs else None)), combined
    if len(fresh) == 1:                                     # one doc → the simple path
        return do_add(base, env, fresh[0], docs, combined, timeout, store_dir)
    print(f"  adding {len(fresh)} document(s) … (reuses existing drills; only new build)")
    docs.extend(fresh)
    drilled: list = []
    for d in docs:
        try:
            _run(base + ["model", d], env, timeout=max(timeout, 600.0))
            drilled.append(d)
        except Exception as e:                              # noqa: BLE001
            print(f"  could not drill {d}: {e}", file=sys.stderr)
    docs[:] = drilled                                       # drop undrillable inputs
    if not drilled:
        print("  context unchanged.", file=sys.stderr)
        return (combined or None), combined
    if len(drilled) == 1:
        print(f"  context: {drilled[0]} (1 document) — ask away.")
        return drilled[0], None
    base_store = (Path(store_dir) / ".drillui_session.docpack") if store_dir \
        else Path(".drillui_session.docpack")
    out = combined or str(base_store)
    try:
        msg = _run(base + ["combine", *drilled, "--out", out, "--force"], env,
                   timeout=max(timeout, 900.0))
        print("  " + " ".join(msg.split()))
    except Exception as e:                                  # noqa: BLE001
        print(f"  combine failed: {e}", file=sys.stderr)
        return (combined or drilled[0]), combined
    print(f"  context spans {len(drilled)} document(s) — commands fan out over all.")
    return out, out


def query_download_dir(base, env, timeout: float) -> str:
    """The pdfdrill download dir (config-driven, default ~/Downloads) — so the
    session combined store lives next to the drilled docs, not in a scratch cwd."""
    try:
        return _run(base + ["config", "--download-dir"], env, timeout=timeout).strip()
    except Exception:                                      # noqa: BLE001
        return str(Path.home() / "Downloads")


def doc_status(base, env, doc: str, timeout: float) -> str:
    try:
        return _run(base + ["status", doc], env, timeout=timeout).strip()
    except Exception as e:  # noqa: BLE001
        return f"(status unavailable: {e})"


def _repl_help(cmds: dict) -> str:
    n = len(cmds) or "?"
    return (
        "drillui_chat REPL — type a QUESTION about the open document and get a\n"
        "grounded answer. Or run any pdfdrill command on the doc by NAME (the\n"
        "filename is filled in for you — never repeat it):\n"
        "  status            size            mathpix         model\n"
        "  visionocr         mathcheck       tiddlers        report\n"
        "  artifacts (list every drill file as a clickable Outputs link)  …\n"
        f"  ({n} pdfdrill commands available; a leading '!' also forces command mode)\n"
        "Meta-commands:\n"
        "  add <pdf|url|id> [more…]   add one or many docs (space-separated)\n"
        "  add \"name with blanks.pdf\"  quote a path with spaces/parens — or paste it\n"
        "                            unquoted: an existing file wins over splitting\n"
        "  add @list.txt             add every path/URL/id listed in a file (one per line)\n"
        "  (with several docs loaded, a pdfdrill command runs on EVERY document)\n"
        "  help, :help, ?    show this help\n"
        "  commands          list every pdfdrill command name\n"
        "  quit / exit / q   quit the REPL (also stop, bye, or Ctrl-D)\n"
        "Rule: a known pdfdrill command name => command; anything else => question.\n"
        "A blank line is ignored. Arrow keys recall history (real terminal only).")


def one_turn(base, env, args, doc: str, q: str, history: str = "") -> str:
    info = retrieve(base, env, doc, q, args.k)
    units = [u["id"] for u in info.get("units", [])]
    prompt = info.get("prompt", q)
    if history:
        prompt = f"PRIOR CONVERSATION (for continuity):\n{history}\n\n" + prompt
    answer = ask_llm(prompt, claude=args.claude, model=args.model, timeout=args.timeout)
    print(f"\n\033[1m{answer}\033[0m\n")
    if units:
        print(f"  (grounded in: {', '.join(units)})")
    if not args.no_store:
        msg = chatlog(base, env, doc, q, answer, units, args.model or "")
        print(f"  {msg}")
    return answer


_EPILOG = """\
examples:
  # one-shot question (pdfdrill auto-located from this script's repo)
  tools/drillui_chat.py data/paper.pdf -q "why no single global metric?"

  # interactive REPL with rolling history
  tools/drillui_chat.py data/paper.pdf

  # cheaper/faster model, more retrieved context, don't persist the turn
  tools/drillui_chat.py data/paper.pdf --model claude-haiku-4-5-20251001 --k 12 --no-store

  # point at a different pdfdrill (only needed outside the repo)
  tools/drillui_chat.py paper.pdf --src /path/to/PDFDRILL/src
  tools/drillui_chat.py paper.pdf --pdfdrill "python -m pdfdrill"

The document must already be drilled (have a pdfdrill model): run
`pdfdrill model <doc>` (or `markdown <doc>.md`) first. This is the external
drillui frontend — it only talks to pdfdrill as a subprocess, never imports it.
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="drillui_chat.py",
        description="Ask-the-document proxy: pdfdrill retrieves grounded context, "
                    "an LLM answers, the Q&A is stored back as a pdfdrill kitem.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("doc", nargs="?",
                    help="a drilled PDF / .md (must have a pdfdrill model)")
    ap.add_argument("-q", "--question", help="one-shot question (omit for a REPL)")
    ap.add_argument("--k", type=int, default=8, help="retrieved units per question (default 8)")
    ap.add_argument("--model", help="claude model (default: whatever `claude` uses)")
    ap.add_argument("--claude", default="claude", help="claude CLI binary (default 'claude')")
    ap.add_argument("--src", help="dev: add this dir to PYTHONPATH (e.g. 'src'); "
                                  "normally auto-located from this script")
    ap.add_argument("--pdfdrill", help="override the pdfdrill invocation (space-separated)")
    ap.add_argument("--timeout", type=float, default=180.0, help="per-call timeout s (default 180)")
    ap.add_argument("--no-store", action="store_true", help="don't write the transcript/kitem")
    args = ap.parse_args()

    # A one-shot question needs a document; the interactive REPL does NOT — you
    # can start empty and bring documents in with `add` (the doc is optional now
    # that `add` exists).
    if args.question and args.doc is None:
        print("error: -q/--question needs a <doc> (or start the REPL with no "
              "args and use `add`).", file=sys.stderr)
        return 2

    base, env, how = _pdfdrill_cmd(args)

    if args.question:
        try:
            one_turn(base, env, args, args.doc, args.question)
            return 0
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            print(f"  (pdfdrill via {how})", file=sys.stderr)
            return 1

    interactive = sys.stdin.isatty()
    if readline and interactive:                       # persistent arrow-key history
        hist = Path.home() / ".drillui_chat_history"
        try:
            readline.read_history_file(hist)
        except Exception:                              # noqa: BLE001 (missing/locked)
            pass
        readline.set_history_length(1000)
        atexit.register(lambda: _save_history(readline, hist))

    cmds = load_commands(base, env, args.timeout)      # {name: first-positional-type}

    print(f"drillui_chat — {('asking ' + args.doc) if args.doc else 'empty context'}"
          f"\n  pdfdrill via {how}")
    if not interactive:
        print("  (stdin is not a TTY — arrow-key history/line-editing is "
              "unavailable; you're likely running through a pipe/bridge.)")
    if args.doc:
        # Startup precondition check: questions need a drilled MODEL. `retrieve`
        # itself is the signal — JSON when a model exists, "No model …" prose
        # otherwise. Probe once; if absent, name the RIGHT builder for this doc.
        try:
            retrieve(base, env, args.doc, "ping", 1)
        except Exception as e:                        # noqa: BLE001
            why = str(e).splitlines()[0] if str(e).strip() else "no model"
            builder = "markdown" if args.doc.lower().endswith(".md") else "model"
            print(f"  ⚠ not drilled yet ({why})")
            print(f"     questions need a model first — build one here by typing:  {builder}")
    else:
        print("  No document yet — `add <pdf|url|arxiv-id>` to bring one in.")
    print("  Type a question, a pdfdrill command (status, size, model, …), or "
          "`add <pdf|url|id>`.")
    print("  Quit: quit / exit / q (or Ctrl-D).  Help: :help")
    history = ""
    docs = [args.doc] if args.doc else []   # documents in the context
    target = args.doc                       # retrieval target (doc / combined store / None)
    combined = None                         # the combined-store path once >1 doc
    store_dir = query_download_dir(base, env, args.timeout)   # stable home for the session store
    while True:
        try:
            line = input("\n? ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:                                  # blank → ignore, don't quit
            continue
        if line.lower() in _QUIT:                     # quit/exit/stop/q/:q/… all work
            break
        if line in (":help", ":h", "help", "?"):
            print(_repl_help(cmds))
            continue
        if line in (":commands", ":cmds", "commands"):
            print("  ".join(sorted(cmds)) or "(command list unavailable)")
            continue
        # add <doc>: drill it and merge into the live context (multi-document).
        parts = line.split(None, 1)
        if parts[0].lstrip(":").lower() == "add":
            spec = parts[1].strip() if len(parts) > 1 else ""
            if not spec:
                print("  usage: add <pdf|url|arxiv-id> [more…]   OR   add @list.txt")
                continue
            newdocs = _expand_add_spec(spec)
            if not newdocs:
                print("  nothing to add.")
                continue
            target, combined = do_add_many(base, env, newdocs, docs, combined,
                                           args.timeout, store_dir)
            continue
        # Nothing in context yet → everything but `add`/meta needs a document.
        if target is None:
            print("  no document yet — `add <pdf|url|arxiv-id>` to bring one in.")
            continue
        # A pdfdrill command — forced with '!' or recognised by name — runs on the
        # CURRENT target. Everything else is a question.
        first = line.lstrip("!").split(maxsplit=1)[0] if line.lstrip("!") else ""
        is_cmd = line.startswith("!") or first in cmds
        # Typo / singular tolerance: a lone word that closely matches a command
        # (e.g. `tiddler` → `tiddlers`) runs the command instead of being sent to
        # the LLM as a question (which wastes a slow call and answers nothing).
        if not is_cmd and len(line.split()) == 1 and first:
            near = difflib.get_close_matches(first.lower(), list(cmds), n=1, cutoff=0.8)
            if near:
                print(f"  (no command `{first}` — running closest match `{near[0]}`)")
                line = first = near[0]
                is_cmd = True
        if is_cmd:
            # Multi-document: a pdfdrill command runs on EVERY loaded document
            # (fan-out). The combined store is a RETRIEVAL artifact, not a PDF, so
            # per-doc commands run on the docs themselves; only the combined-aware
            # `bibtex` runs on the store.
            combined_aware = combined is not None and first in _COMBINED_OK
            if len(docs) > 1 and not combined_aware:
                print(f"  running `{first}` on {len(docs)} documents …")
                for d in docs:
                    print(f"\n=== {os.path.basename(d)} ===")
                    try:
                        print(run_command(base, env, cmds, d, line, args.timeout))
                    except Exception as e:             # noqa: BLE001
                        print(f"  error: {e}", file=sys.stderr)
                continue
            # single document (or a combined-aware command on the store)
            on_combined = combined is not None and target == combined
            if on_combined and first not in _COMBINED_OK:
                print(f"  `{first}` runs on a SINGLE document; the context is a "
                      f"combined store. Ask a question (spans all), use `bibtex` "
                      f"(per-doc), or `add` fewer docs.")
                continue
            try:
                print(run_command(base, env, cmds, target, line, args.timeout))
            except Exception as e:                     # noqa: BLE001
                print(f"error: {e}", file=sys.stderr)
            continue
        try:
            a = one_turn(base, env, args, target, line, history)
            history = (history + f"\nQ: {line}\nA: {a[:500]}")[-2000:]
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
