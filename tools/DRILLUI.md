# drillui — ask-the-document terminal

**There is exactly ONE canonical copy of each file, and it lives in `tools/`.**
If you find a `drillui_bridge.ts` / `drillui_term.html` anywhere else (e.g. an
old `~/Downloads/` drop), it is a stale duplicate — delete it and use the repo
copy. (Prerequisite: the Python deps must be installed once — `pip install -e .`
in the repo; otherwise the bridge's `python -m pdfdrill` subprocess fails with
e.g. `No module named 'pydantic'`.)

Three files, three distinct roles. They are **not** interchangeable; the
confusion comes from the shared `drillui_` prefix, so here is exactly what each
one is and how they connect.

```
 browser tab                     one Bun process                  one Python process
┌────────────────────┐  WebSocket ┌────────────────────┐  stdin/  ┌────────────────────┐
│ drillui_term.html  │◄──────────►│ drillui_bridge.ts  │◄────────►│ drillui_chat.py    │
│ (xterm.js UI)      │  /ws + HTTP│ (Bun: spawn + serve)│  stdout  │ (REPL: the brain)  │
└────────────────────┘            └────────────────────┘          └─────────┬──────────┘
                                                                             │ subprocess
                                                                             ▼
                                                                      pdfdrill (CLI)
```

- **`drillui_chat.py`** — the **brain** (Python). A REPL over ONE document: it
  asks `pdfdrill retrieve` for grounded context, sends the enriched prompt to an
  LLM (`claude -p`), and stores the Q&A back via `pdfdrill chatlog`. It also runs
  any pdfdrill subcommand on the open doc by name. **It never needs a browser**
  and works standalone in a terminal. It auto-locates `pdfdrill` from its own
  path (`../src`), so no `--src` is required inside the repo.
- **`drillui_bridge.ts`** — the **bridge** (Bun). A browser can't spawn a
  process, so the bridge spawns ONE `drillui_chat.py <doc>` per WebSocket
  connection and pipes stdin/stdout. It also serves `drillui_term.html`, serves
  the files pdfdrill writes (`/artifact`), and can open a file in the host
  browser (`/open`). **No business logic lives here** — it is plumbing.
- **`drillui_term.html`** — the **UI** (browser). An xterm.js terminal with
  bash-style line editing + history, a retrieval rail (cited unit ids), and an
  Outputs panel (links to reports). It owns the visible prompt.

## Run it (zero config; launch from anywhere)

```bash
bun tools/drillui_bridge.ts data/yourpaper.pdf      # then open http://localhost:8787/
bun tools/drillui_bridge.ts                         # OR start EMPTY, then `add` docs in the UI
cd tools && bun run drillui_bridge.ts               # also fine — launch location no longer matters
```

The bridge self-locates the repo root from its own path, so the artifacts root +
served files are correct no matter where you launch it (an earlier version used
the launch cwd, so running from `tools/` served the wrong folder).

The document is **optional** — start empty and bring documents in with `add`.
`add` is multi-document (a drillui function, not pdfdrill):

- `add <pdf|url|arxiv-id>` — one doc.
- `add a.pdf https://arxiv.org/abs/2501.06699 2412.00001` — several at once.
- `add @list.txt` — every path/URL/arXiv-id listed in a file (one per line, `#`
  comments and blank lines skipped) — for the hundreds-of-URLs case.

The first `add` becomes the context; each further `add` merges in. **With more
than one document loaded, a pdfdrill command runs on EVERY loaded document**
(e.g. `tiddlers` fans out over all of them, printing a `=== name ===` header per
doc); questions still retrieve across the whole combined set, and `bibtex` reads
the combined store. (Each doc is still acquired by pdfdrill from its URL/id —
drillui never fetches a PDF or LaTeX itself.)

That's all: the bridge finds `drillui_chat.py` as its sibling, `python3` runs
it, and `drillui_chat.py` finds `pdfdrill` in `../src`. Flags only if you need
them: `--port N`, `--model NAME`, `--k N`, `--no-store`, `--python BIN`,
`--chat PATH` (only if the .py is elsewhere), `--opener firefox|xdg-open` /
`--no-open`.

The document must already be drilled (`pdfdrill model <doc>`). If it isn't, the
REPL says so on connect and tells you to type `model` to build it.

## What happens to a line you type — the command model

The browser decides FIRST, then (only if not local) forwards to Python:

| You type | Handled by | Effect |
|---|---|---|
| `open <url\|file>` | **browser (local)** | opens a new window — a URL directly, or a pdfdrill output file via the bridge. **Never an LLM call.** |
| `lhelp` | **browser (local)** | lists the local commands |
| `^L` | **browser (local)** | clear screen |
| `status`, `size`, `model`, `report`, `mathpix`, `visionocr`, … | Python → pdfdrill | runs that pdfdrill subcommand **on the open doc** (filename auto-filled) |
| `quit` / `exit` / `q` | Python | quits the REPL |
| anything else | Python → LLM | a grounded **question** about the document |

So `open https://arxiv.org/pdf/2305.04710` opens the PDF in a window; it does
**not** go to the LLM. This is the fix for the earlier "open url called Claude".

## Importing tiddlers into TiddlyWiki — drag & drop (no file browser)

A `*.tiddlers.json` (or any tiddler-array JSON) in the **Outputs** panel is
**draggable straight into an open TiddlyWiki tab**: it shows `⇲ drag → TiddlyWiki`,
and on drop TiddlyWiki imports it via its native `text/vnd.tiddler` type — **no
file browser, no import menu** (the same mechanism TW uses to drag tiddlers
between wikis and to install plugins). drillui pre-fetches the JSON so the drag
carries the actual tiddler array; drop it onto the TiddlyWiki window and confirm
the import.

Each Outputs row also has **`save ⤓`** — it downloads the REAL file (valid JSON,
correct name) to your browser's download dir. Use it when you'd rather drag the
saved file in: clicking `open ↗` shows the browser's collapsible JSON *viewer*,
whose text can't be copied as valid JSON — `save ⤓` gives you the actual file.

Two equivalent paths if you prefer the OS:
- The artifacts live under `~/Downloads/<name>.pdf.drill/` (the config download
  dir, never `/tmp`), so you can also drag the `*.tiddlers.json` **file** from the
  file manager onto TiddlyWiki — same native import.
- The dumb TiddlyWiki *file-input* browser is avoidable entirely; never paste the
  `…/artifact?path=…` URL into it.

## Test it

```bash
bun tools/test_drillui_bridge.ts data/1906.02691.pdf
```

Spawns the real bridge against a drilled doc and checks: the page serves, the
`open`-is-local contract holds (promptLoop intercepts before forwarding),
`/artifact` serves under-root files and refuses traversal, `/open` is refused
when host-open is disabled, and a WebSocket round-trip runs a `status` command
on the doc and gets output back.
