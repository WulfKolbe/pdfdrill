# Running pdfdrill + drillui on CoCalc.ai

The CoCalc **standard image** does not ship several things pdfdrill and the
`drillui` web terminal depend on — `poppler-utils`, the LaTeX / `dvisvgm` SVG
toolchain, `bun`, and `uv`. On CoCalc you *do* have `pip install`, `sudo
apt-get`, and write access to `~/.local/bin` and `~/.bun`, which is everything
the setup needs.

The drillui page is reached through CoCalc's **reverse proxy** on a path like
`/<PROJECT_ID>/server/8787/`; drillui now derives its WebSocket + artifact URLs
from that page path, so it connects through the proxy automatically. Details below.

## 1. One-time setup

From the repo root:

```bash
bash cocalc-setup.sh
```

It runs four steps: the missing apt packages (`sudo apt-get install -y
poppler-utils dvisvgm texlive-latex-extra`), `bun` (into `~/.bun`), `uv`+`uvx`
(into `~/.local/bin`), then `bootstrap.sh` for the shared Python deps and the
remaining system packages (ghostscript, tesseract, libvips) — finishing with
`pdfdrill doctor`.

`bun` and `uv` are appended to `~/.bashrc`, so **open a fresh shell** (or
`source ~/.bashrc`) afterwards to get them on `PATH`. In the current shell you
can instead run:

```bash
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"
```

Verify:

```bash
bun --version
pdfdrill doctor        # or: PYTHONPATH=src python3 -m pdfdrill doctor
```

## 2. Launch the drillui web terminal

drillui self-locates `pdfdrill` from the repo, so no install is needed — run
the bridge from the repo root (it serves on port **8787**):

```bash
bun run tools/drillui_bridge.ts                 # start empty; `add <doc>` in the UI
bun run tools/drillui_bridge.ts data/paper.pdf  # or open with a document
```

Leave it running; it holds the WebSocket session for the whole chat.

## 3. Open it in the browser (CoCalc port forwarding)

CoCalc exposes a listening port at a proxied URL of the form:

```
https://<HOST>/<PROJECT_ID>/server/<PORT>/
```

- `<PORT>` is **8787** (drillui's default; change with `--port`).
- `<PROJECT_ID>` is your project id — `echo "$COCALC_PROJECT_ID"`.
- `<HOST>` is the `host-….cocalc.ai` compute host shown in your CoCalc browser
  URL.

So the drillui page is:

```
https://<HOST>/<PROJECT_ID>/server/8787/
```

Example (yours will differ):

```
https://host-dab25958-64df-4bea-803b-77319d7839f6-cocalc-prod.cocalc.ai/40721fd4-8da4-42b2-8319-1d714e6fd1ae/server/8787
```

## 4. Connecting — automatic now

drillui derives its WebSocket URL (and its artifact/viewer HTTP base) from the
**page's own path**, so behind CoCalc's proxy it connects to
`wss://<HOST>/<PROJECT_ID>/server/8787/ws` automatically — no manual step. Open the
page (§3) and the terminal banner should appear. The derivation works whether or
not CoCalc gives the page URL a trailing slash (`…/server/8787` **and**
`…/server/8787/` both resolve to the same `…/server/8787/ws`) — a no-trailing-slash
page URL used to drop the `8787` port segment; fixed 2026-07-12.

**Fallback** — if it still shows **"Bridge not reachable"** (e.g. an unusual proxy
layout), paste the WebSocket URL into the terminal's **Connect** box. It's the
drillui page's own URL with `https`→`wss` and `ws` appended after the trailing slash:

```
wss://<HOST>/<PROJECT_ID>/server/8787/ws
```

## Troubleshooting

- **`bun: command not found`** — new shell not opened yet:
  `export PATH="$HOME/.bun/bin:$PATH"`.
- **`uv: command not found`** — `export PATH="$HOME/.local/bin:$PATH"`.
- **Port 8787 already in use** — launch with `--port N` and use that port in
  both the page URL and the `wss://…/server/N/ws` string.
- **Missing system tool** (poppler / dvisvgm / ghostscript / tesseract) —
  re-run `pdfdrill doctor`; it prints the exact `apt-get` line to fix each.
- **Artifacts/viewer links 404 in the browser** — these are now derived through
  the proxy path (same fix as the WebSocket URL), so they should resolve. If a link
  still 404s, open the report/artifact from the `*.drill/` folder in the CoCalc file
  browser instead.
