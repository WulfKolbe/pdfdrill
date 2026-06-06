# pdfdrill — change request: version signal + CHANGELOG (so improvements are trackable)

> **Status: open.** Motivated by keeping the public site
> (wulfkolbe.github.io) in lock-step with the tool. There is currently **no
> version to track against.**

## Problem

`pyproject.toml` has been `version = "0.1.0"` across **90+ commits** — through
the entire continuity / segment / entities / qr / semantic / elements /
selftest / translate wave. Consequences:

- There is no `pdfdrill.__version__`, no `pdfdrill --version`, and no
  `pdfdrill version` command. A user (or the website, or a CI job) cannot ask
  "which pdfdrill am I running, and does it have `qr`?"
- "Keep the site in step with the tool" has no anchor: the only way to know what
  shipped is to read `git log`. The website's command catalogue drifted out of
  date silently because nothing surfaced "8 new commands since the site was
  written."
- No `CHANGELOG.md`: the substantial, user-visible capability jumps (math-only →
  scanned commercial mail) are invisible to anyone not reading commits.

## Proposed scope

1. **Single source of version.** Keep the number in `pyproject.toml` and expose
   it at runtime:

       # src/pdfdrill/__init__.py
       from importlib.metadata import version, PackageNotFoundError
       try:
           __version__ = version("pdfdrill")
       except PackageNotFoundError:        # running from source, not installed
           __version__ = "0.0.0+source"

2. **Surface it.** `pdfdrill --version` / `pdfdrill version` prints
   `pdfdrill <ver>`; include it in the `--help` banner header and in
   `pdfdrill doctor` output. (Routes naturally through `branding.APP_NAME` once
   [CR-branding-variable](CR-branding-variable.md) lands.)

3. **Bump on user-visible change.** Adopt semver-ish discipline: a new command
   or changed output shape bumps MINOR; a fix bumps PATCH. Start by bumping to a
   number that reflects reality (the tool is well past `0.1.0`).

4. **`CHANGELOG.md`** in [Keep a Changelog](https://keepachangelog.com) format,
   grouped Added / Changed / Fixed, each entry naming the command and commit.
   Backfill one consolidated entry for the work already shipped (continuity,
   segment, entities, qr, elements, semantic, selftest, translate, the AOK scan
   fix, the SVG/listing fix).

## Acceptance

- `pdfdrill --version` prints a non-`0.0.0` version; `import pdfdrill;
  pdfdrill.__version__` works when installed.
- `CHANGELOG.md` exists and its newest entry matches the current `pyproject`
  version.
- The `--help` / `doctor` banner shows the version.

## Priority

Low effort, high option-value — it's the prerequisite for *anything downstream*
(the website, release notes, bug reports) being able to say "as of vX.Y".
