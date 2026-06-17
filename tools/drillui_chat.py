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


def _pdfdrill_cmd(args: argparse.Namespace) -> tuple[list[str], dict]:
    """The base argv + env for invoking pdfdrill as a subprocess. Prefers an
    installed `pdfdrill`; in a source checkout pass --src to run the module."""
    env = dict(os.environ)
    if args.src:
        env["PYTHONPATH"] = args.src + os.pathsep + env.get("PYTHONPATH", "")
        return [sys.executable, "-m", "pdfdrill"], env
    if args.pdfdrill:
        return args.pdfdrill.split(), env
    import shutil
    if shutil.which("pdfdrill"):
        return ["pdfdrill"], env
    return [sys.executable, "-m", "pdfdrill"], env


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


def main() -> int:
    ap = argparse.ArgumentParser(description="ask-the-document proxy (external drillui frontend)")
    ap.add_argument("doc", help="a drilled PDF / .md (must have a pdfdrill model)")
    ap.add_argument("-q", "--question", help="one-shot question (omit for a REPL)")
    ap.add_argument("--k", type=int, default=8, help="retrieved units per question")
    ap.add_argument("--model", help="claude model (default: whatever `claude` uses)")
    ap.add_argument("--claude", default="claude", help="claude CLI binary")
    ap.add_argument("--src", help="dev: add this dir to PYTHONPATH (e.g. 'src')")
    ap.add_argument("--pdfdrill", help="override the pdfdrill invocation (space-separated)")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--no-store", action="store_true", help="don't write the transcript/kitem")
    args = ap.parse_args()
    base, env = _pdfdrill_cmd(args)

    if args.question:
        try:
            one_turn(base, env, args, args.doc, args.question)
            return 0
        except Exception as e:
            print(f"error: {e}", file=sys.stderr); return 1

    print(f"drillui_chat — asking {args.doc}. Blank line or Ctrl-D to quit.")
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
