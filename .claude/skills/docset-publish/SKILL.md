---
name: docset-publish
description: Use when the user wants to turn a pdfdrill drill result (a tiddlers.json, optionally with the source PDFs) into a standalone TiddlyWiki hosted on GitHub Pages. Produces a tarball in the Claude.ai sandbox; the user pushes to GitHub from their own machine. No credentials ever enter the sandbox.
---

# Publish a pdfdrill document set as a TiddlyWiki on GitHub Pages

**Golden rule — tar-only.** The sandbox authenticates to nothing. It BUILDS and
TARS; the user pushes from their own machine. Never run `gh auth`, never accept a
token into the chat, never `git push` from the sandbox.

## Claude.ai sandbox drive map
- `HOME` = `/home/claude`
- working dir = `/home/claude/<repo>/`
- uploads (the user's tiddlers.json + PDFs) land in `/mnt/user-data/uploads/`
- downloads are served from `/mnt/user-data/outputs/` — probe it with
  `ls /mnt/user-data/outputs 2>/dev/null`; if absent, write the tarball to
  `$HOME` and tell the user the path.

## Step 0 — ask
Ask the user for their **GitHub username** and a **repo name**. Never hardcode.

## Step A — build, in the sandbox (no credentials)
```bash
mkdir -p /home/claude/<repo> && cd /home/claude/<repo>
# scaffold: drop assets/tiddlywiki.info, assets/package.json here; write
#   .gitignore (node_modules/  $__StoryList.tid  .env  *.token  .git-credentials)
#   .nojekyll  (empty)
mkdir -p tiddlers files
python3 <assets>/unpack.py /mnt/user-data/uploads/<name>.tiddlers.json --out tiddlers
cp /mnt/user-data/uploads/*.pdf files/ 2>/dev/null || true
cp /mnt/user-data/uploads/*.tiddlers.json files/ 2>/dev/null || true
npm i tiddlywiki
npx tiddlywiki . --output . --build index          # -> ./index.html at repo ROOT
git init && git add -A && git commit -m "drill: <repo>"   # LOCAL commit only, no remote
tar czf /mnt/user-data/outputs/<repo>.tar.gz --exclude=node_modules -C .. <repo>
```
Report the tarball path and the Step-B commands. (When pdfdrill is installed in
the sandbox, `pdfdrill repoinit <repo> --username U` + `pdfdrill publish <repo>
<pdf>` replace the scaffold + unpack lines.)

## Step B — the user runs on their own machine (creds already local)
```bash
tar xzf <repo>.tar.gz && cd <repo>
gh repo create <repo> --public --source=. --remote=origin --push
gh api -X POST repos/<user>/<repo>/pages -f 'source[branch]=main' -f 'source[path]=/'
# later: git add -A && git commit -m "…" && git push
```
Live at `https://<user>.github.io/<repo>/`. (If the Pages API 404s, enable Pages
once in the repo's web Settings → Pages → deploy from branch, / root.)

## Step C — one-time hub
Create `<user>.github.io` with `assets/navigator.html` as its `index.html` (+
`.nojekyll`), push, enable Pages. Set `const username` to `<user>`. Visiting
`https://<user>.github.io/` then lists every repo with a root `index.html` and
links its Pages URL — so each doc-set repo can be an ordinary public repo.

## Anti-patterns
- Do NOT paste a token into the chat or run `gh auth` in the sandbox.
- Do NOT build into `output/` (it is gitignored and Pages won't serve it) — use
  `--output .` so `index.html` lands at the repo root.
- Do NOT commit `node_modules/` (gitignored; excluded from the tar).
