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
import json
import os
import subprocess
import sys
from pathlib import Path


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


def retrieve(base: list[str], env: dict, doc: str, q: str, k: int) -> dict:
    out = _run(base + ["retrieve", doc, q, "--k", str(k), "--json"], env)
    # cmd_retrieve --json prints exactly one JSON object (last non-empty line).
    line = [ln for ln in out.splitlines() if ln.strip().startswith("{")][-1]
    return json.loads(line)


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

    # No args at all → show help rather than an argparse 'doc required' stub.
    if args.doc is None:
        ap.print_help()
        return 0

    base, env, how = _pdfdrill_cmd(args)

    if args.question:
        try:
            one_turn(base, env, args, args.doc, args.question)
            return 0
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            print(f"  (pdfdrill via {how})", file=sys.stderr)
            return 1

    print(f"drillui_chat — asking {args.doc} (pdfdrill via {how}). "
          f"Blank line or Ctrl-D to quit.")
    history = ""
    while True:
        try:
            q = input("\n? ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not q:
            break
        try:
            a = one_turn(base, env, args, args.doc, q, history)
            history = (history + f"\nQ: {q}\nA: {a[:500]}")[-2000:]
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
