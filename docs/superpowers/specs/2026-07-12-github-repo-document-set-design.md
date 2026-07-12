# Publishing a drilled document set as a TiddlyWiki on GitHub Pages

**Date:** 2026-07-12
**Status:** Design approved (brainstorming complete); ready for implementation plan.
**Author:** wkolbe + Claude

## 1. Problem

A pdfdrill "document set" (one or more drilled PDFs, each a bibkey-prefixed set of
TiddlyWiki tiddlers) needs a durable, browsable home. The concrete goal: the
**Claude.ai chatbot**, working inside its sandbox, turns a drill result into a
single-file TiddlyWiki the user can open (a) in the chatbot's preview window and
(b) at a `github.io` URL — the *same* wiki in both places — and can keep the raw
PDFs alongside it. The chatbot needs a **SKILL** that spells out, step by step:
the sandbox drive layout, how the folder is organised, how the standalone
`index.html` is built, and how the result reaches the user's GitHub — **without
any credential ever entering the sandbox**.

This design is grounded in a real, working artifact the user produced on
Claude.ai (`~/Downloads/tw-server.tar.gz`), which validated the sandbox paths,
the Node build, and the tiddler on-disk format. See §11 (Evidence).

## 2. Goals / non-goals

**Goals**
- A canonical repo layout that is simultaneously a TiddlyWiki source folder, a
  raw-PDF archive, and a github.io-servable site.
- A standalone `index.html` built by the **standard Node TiddlyWiki build**,
  served from the repo root by GitHub Pages, identical in the chatbot preview.
- The chatbot produces a **tarball** of the whole result (the default artifact);
  pushing to GitHub is done **by the user on their own machine**.
- **Zero credentials in the sandbox / transcript.**
- The GitHub **username is asked**, never hardcoded.
- A one-time **navigator hub** on `<user>.github.io` that auto-discovers every
  doc-set repo, so doc-set repos can be *ordinary* public repos.

**Non-goals**
- No token handling, `gh auth`, or `git push` inside the Claude.ai sandbox.
- No native re-implementation of the TiddlyWiki build (the standard Node build is
  proven and canonical — see Decision D2).
- No Git LFS / external asset store (PDFs are committed as ordinary files).
- No live multi-user server (the optional `--listen` mode is documented, not
  required).

## 3. Key decisions (with rationale)

| # | Decision | Rationale / evidence |
|---|---|---|
| D1 | **Single-file TW5 → committed `index.html`** | Renders standalone on github.io AND in the chatbot preview; no server. |
| D2 | **Standard Node build** (`npx tiddlywiki . --output . --build index`) | Proven on Claude.ai (tw-server: `tiddlywiki@^5.4.1`, 6.1 MB standalone output). A native injector would only imitate it and must bundle katex+markdown itself. |
| D3 | **Commit everything** (PDFs + tiddlers + index.html) | The repo *is* the download (`git clone` / GitHub "Download ZIP"); matches the `~/raw` mental model. |
| D4 | **`index.html` at repo root + `.nojekyll`** | GitHub Pages "deploy from branch, / (root)"; no Jekyll processing. |
| D5 | **Navigator hub + normal repos** | Doc-set repos need no special name; a single page on `<user>.github.io` lists every repo with a root `index.html` and links its Pages URL. |
| D6 | **Tar by default; commit is opt-in** | Every drill result is a downloadable tarball; publishing is a separate, user-initiated act. |
| D7 | **Tar-only — never push from the sandbox** | The sandbox authenticates to nothing; the user pushes from their own machine where creds already live. Eliminates the token-in-transcript risk entirely. |
| D8 | **Ask the GitHub username** | Persisted in `pdfdrill-repo.json`; feeds the navigator `username` and the Pages URL. |

## 4. Topology

Two repo kinds:

```
<user>.github.io/            ← the HUB (one-time)
  index.html                 ← navigator: scans the user's repos, lists those
  .nojekyll                     with a root index.html, links each Pages URL

<any-doc-set-repo>/          ← one per document SET (ordinary public repo)
  index.html                 ← built standalone TW5 (root, committed)  → https://<user>.github.io/<repo>/
  .nojekyll
  tiddlywiki.info            ← build config (katex + markdown [+ tiddlyweb + filesystem for --listen])
  package.json               ← { dependencies: { tiddlywiki: "^5.4.1" } }
  .gitignore                 ← node_modules/  $__StoryList.tid  .env  *.token  .git-credentials
  pdfdrill-repo.json         ← { username, title, files_dir, tiddlers_dir, docs:[bibkey…] }
  README.md
  tiddlers/
    <bibkey>/<title>.md + <title>.md.meta   ← per-tiddler pairs (tiddlers_to_md format)
  files/
    <name>.pdf …             ← raw PDFs (the ~/raw archive)
    <name>.tiddlers.json …   ← the source tiddler exports (provenance)
```

Node build output goes to the repo root (`--output .`), NOT the default
`output/` (which the tw-server example left `.gitignore`d — the one thing that
example got wrong for github.io).

## 5. Claude.ai sandbox environment map

Verified from the tw-server unpack.log (10 560 writes under the working dir, 2
reads from uploads):

| Path | Role |
|---|---|
| `/home/claude` | HOME |
| `/home/claude/<repo>/` | working dir (the repo being built) |
| `/mnt/user-data/uploads/` | where user-uploaded files land (`*.tiddlers.json`, PDFs) |
| `/mnt/user-data/outputs/` | **download dir** — files written here are offered to the user (to confirm on first run; §10) |

Node + npm are present in the sandbox (`npm i tiddlywiki` + `npx tiddlywiki`
both ran). `gh` is **not needed** in the sandbox under D7.

## 6. Components

### 6.1 `pdfdrill repo init <dir> [--username U] [--title T]` (new command)
Scaffold the doc-set repo layout, idempotent. Writes `tiddlywiki.info`,
`package.json`, `.gitignore`, `.nojekyll`, `README.md`, `pdfdrill-repo.json`
(username/title/dir names), and empty `tiddlers/` + `files/`. Pure filesystem;
no network, no Node. **Single source of truth for the templates:** they are the
SKILL's `assets/*` (§6.4), bundled into pdfdrill as package-data by the existing
`tools/skillsync.py bundle` mechanism — `repo init` reads them from there, so the
scaffold and the SKILL never drift.

### 6.2 `pdfdrill publish <dir> [<pdf>…]` (new command)
For each drilled document in the set: export its tiddlers via the existing
`tools/tiddlers_to_md.export_tiddlers` into `tiddlers/<bibkey>/`, copy its PDF (and
`<bibkey>.tiddlers.json`) into `files/`, and append the bibkey to
`pdfdrill-repo.json.docs`. Writes/refreshes a **`Documents` landing tiddler**
(a Markdown list linking each document's root tiddler) and sets
`$:/DefaultTiddlers` to it. **Does not run Node** — building `index.html` is a
separate step (§6.3), so pdfdrill stays offline and Node-free. Idempotent.

### 6.3 The build step (Node, run by the SKILL/sandbox — not pdfdrill)
```bash
npm i tiddlywiki
npx tiddlywiki . --output . --build index      # -> ./index.html at repo root
```

### 6.4 The SKILL (`.claude/skills/docset-publish/`) (new)
The chatbot-facing instructions + template assets. **Works from an uploaded
`*.tiddlers.json` (+ optional PDFs) even when pdfdrill is not installed in the
sandbox** (the proven tw-server path), and notes the `pdfdrill repo init/publish`
shortcuts when pdfdrill *is* present. Contents:
- `SKILL.md` — the step-by-step flow (§7), the sandbox path map (§5), the
  tar-only / no-credential rule (D7), and the user-machine push instructions.
- `assets/tiddlywiki.info`, `assets/package.json`, `assets/gitignore`,
  `assets/navigator.html` — the templates (username/title parameterised).
- `assets/unpack.py` — a stdlib unpack script (tiddlers.json → `tiddlers/*.md` +
  `*.md.meta`, logging full paths to `unpack.log`) for the no-pdfdrill path,
  byte-compatible with `tiddlers_to_md`.

### 6.5 The navigator hub (`assets/navigator.html`)
A static page for `<user>.github.io/index.html`. Lists the user's public repos
that contain a root `index.html` (GitHub contents API, optional PAT for the
5000/h rate limit) and links each repo + its Pages URL. `username` and `rootPath`
are the two knobs; `username` is filled from `pdfdrill-repo.json`.
*Known limitation:* it finds repos that *have* a root `index.html`, but a Pages
link only resolves once Pages is enabled on that repo (§7 step B). *Optional
upgrade (documented, not in v1):* query the Pages API
`/repos/{owner}/{repo}/pages` instead of contents, to list only repos whose Pages
are live and show last-deploy status.

## 7. End-to-end data flow

**A — In the Claude.ai sandbox (no credentials):**
1. Ask the user's **GitHub username** + desired **repo name**.
2. Scaffold `<repo>/` (via `pdfdrill repo init`, or the SKILL's template drop +
   `unpack.py` when pdfdrill is absent).
3. Unpack uploaded `*.tiddlers.json` → `tiddlers/*.md(.meta)`; copy uploaded PDFs
   → `files/`.
4. `npm i tiddlywiki && npx tiddlywiki . --output . --build index` → root
   `index.html`.
5. `git init && git add -A && git commit -m "drill: <repo>"` — **local commit
   only, no remote, no push.**
6. `tar czf /mnt/user-data/outputs/<repo>.tar.gz --exclude=node_modules -C .. <repo>`.
7. Report the download path + the exact B-commands.

The tarball carries `index.html`, `tiddlers/`, `files/`, config, and the `.git`
history; `node_modules/` is excluded (regenerated only if the user rebuilds —
unnecessary, since `index.html` is prebuilt).

**B — On the user's machine (creds already local):**
```bash
tar xzf <repo>.tar.gz && cd <repo>
gh repo create <repo> --public --source=. --remote=origin --push          # first time
gh api -X POST repos/<user>/<repo>/pages -f 'source[branch]=main' -f 'source[path]=/'
# later updates: git add -A && git commit -m "…" && git push
```
→ live at `https://<user>.github.io/<repo>/`; appears in the hub on next scan.

**C — One-time hub:** create `<user>.github.io` with `assets/navigator.html` as
its `index.html` (+ `.nojekyll`), push, enable Pages.

## 8. `pdfdrill-repo.json` schema
```json
{
  "username": "<github-user>",
  "title": "<human title of the set>",
  "files_dir": "files",
  "tiddlers_dir": "tiddlers",
  "docs": ["<bibkey1>", "<bibkey2>"]
}
```
`files_dir`/`tiddlers_dir` give us our own indirection over the folder names
regardless of TiddlyWiki's expectations; defaults `files`/`tiddlers`.

## 9. Security posture
- The sandbox authenticates to nothing; no token, no `gh auth`, no push (D7).
- The only artifact leaving the sandbox is a tarball the user inspects before
  pushing.
- `.gitignore` blocks `.env`, `*.token`, `.git-credentials`, `$__StoryList.tid`,
  `node_modules/`.
- On the user's machine, `gh`'s credential helper handles auth, so the token is
  never embedded in a remote URL or committed.

## 10. Open items to confirm on Claude.ai (not blockers)
- **O1** `/mnt/user-data/outputs/` is the download dir (parallel to
  `uploads/`). The SKILL should `ls`-probe it and fall back to `$HOME` if absent.
- **O2** `gh api …/pages` Pages-enable call occasionally 404s on a token lacking
  `pages` write → fall back to enabling Pages once in the repo web Settings
  (this is a *user-machine* step, so low risk).

## 11. Evidence (the tw-server artifact)
`~/Downloads/tw-server.tar.gz` — a Claude.ai run that unpacked a
`main_tiddlers.json` (5191 tiddlers) to `tiddlers/*.md(.meta)`, built a 6.1 MB
standalone `index.html` via `tiddlywiki.info` (plugins: katex, markdown,
tiddlyweb, filesystem; build `index` = `--render $:/core/save/all index.html
text/plain`), and committed. Confirms: the sandbox paths (§5), Node availability,
the standard build (D2), and that the `.md/.md.meta` layout is exactly what
`tiddlers_to_md.py` emits. It did *not* cover the GitHub leg (this design adds it
as a user-machine step) and left `index.html` in the `.gitignore`d `output/`
(this design builds to root instead, D4).

## 12. Implementation order (for the plan)
1. `pdfdrill repo init` + template assets (package-data) + tests.
2. `pdfdrill publish` (reuse `tiddlers_to_md.export_tiddlers`) + Documents landing
   tiddler + `pdfdrill-repo.json` + tests.
3. The SKILL folder: `SKILL.md`, `assets/*` (tiddlywiki.info, package.json,
   gitignore, navigator.html, unpack.py), the path map, tar-only flow.
4. Wire into `commands.yaml` + `tools/skillsync.py` (2 new commands → 109).
5. Doc: README section + AGENTS/QUICKSTART note; CoCalc note (the public
   playground already documented separately).

## 13. Testing strategy
- `repo init`: scaffolds every file; idempotent; respects `--username/--title`.
- `publish`: exports N docs into `tiddlers/<bibkey>/`, copies PDFs, updates
  `docs[]`, writes the landing tiddler; idempotent; graceful when a doc lacks a
  built model.
- `unpack.py`: round-trips a tiddlers.json to `.md/.md.meta` byte-identically to
  `tiddlers_to_md`.
- Skill-sync drift gate stays green (manifest ↔ HANDLERS).
- Manual/real: run flow A on Claude.ai from an uploaded tiddlers.json → tarball →
  flow B locally → live github.io page listed by the hub.
