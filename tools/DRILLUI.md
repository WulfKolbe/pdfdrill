# drillui — ask-the-document terminal

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

## Run it (zero config, from the repo root)

```bash
bun tools/drillui_bridge.ts data/yourpaper.pdf      # then open http://localhost:8787/
```

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

## Test it

```bash
bun tools/test_drillui_bridge.ts data/1906.02691.pdf
```

Spawns the real bridge against a drilled doc and checks: the page serves, the
`open`-is-local contract holds (promptLoop intercepts before forwarding),
`/artifact` serves under-root files and refuses traversal, `/open` is refused
when host-open is disabled, and a WebSocket round-trip runs a `status` command
on the doc and gets output back.
