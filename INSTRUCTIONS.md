# Release process: archived citations

Applies to any manuscript before it is released, submitted, or posted (Zenodo, journal, publisher).
Almost everything is scripted; the agent's job is to run the steps, read the output, and stop at the gates.

## Steps (run in the manuscript directory)

1. `waihona.py [--top-only] scan` — list every URL in `.tex` and `.bib` (commented-out URLs are ignored).
2. **Gate: approval.** `archive` makes archive.org crawl pages (Save Page Now). Show the user the
   `NEW` list and get a yes before step 3. Never run it against private, paywalled, or unpublished URLs.
3. `waihona.py archive` — for each URL, use the Wayback snapshot closest to the access date if within
   `--max-age` days (default 180); otherwise Save Page Now. Writes `waihona.lock.json` incrementally.
   Exit 1 if any URL failed. Failures are the user's to resolve (cite another source, drop the link,
   or archive by hand) — do not hide them.
4. `waihona.py apply` (dry run), then `apply --write` — adds `urldate`, `lastchecked`, `archiveurl`,
   `archivedate` to `.bib` entries; rewrites `\url{}`/`\href{}{}` in `.tex` to `\aurl[id]{}`/`\ahref[id]{}{}`;
   writes `waihona.def`. Idempotent. Review the git diff; the manuscript text is otherwise untouched.
5. Build the PDF (BibTeX or biber) and read the log for `waihona` warnings and undefined references.
6. `waihona.py check` — HEAD every snapshot; exit 1 on any dead or missing one. Do this last,
   on the final tree, and again if the manuscript sits more than a few weeks before release.
7. Commit `waihona.lock.json`, `waihona.def`, and the edited sources together; report counts
   (URLs, existing vs. saved, stale, failed) and what was not verified.

## What gets printed

House style (option 1 in [docs/CITATION-STYLES.md](docs/CITATION-STYLES.md)), one parenthetical, same inline and in the bibliography:

    https://example.org/page (accessed 13 November 2026; archived 18 October 2026)

`archived 18 October 2026` is the hyperlink to the snapshot (`web.archive.org/web/<timestamp>/<url>`).
**Dates are always `D Month YYYY`** ("13 November 2026"): never ISO, never US order, never abbreviated months.
On paper the reader sees dates but no usable archive link; see the other styles in the doc if print matters.

## Per-manuscript setup (once)

- `\usepackage{waihona}` (put `tex/` on `TEXINPUTS`, or copy `waihona.sty`).
- BibTeX: `\bibliographystyle{apalike-url-archive}` (a urlbst style; `bst/`; patch other urlbst
  styles the same way — see the diff against `apalike-url.bst`).
- biber: `\usepackage[datamodel=waihona,…]{biblatex}` then `\input{waihona-biblatex.tex}` (it composes the date itself, so no `urldate=` option is needed).

## Rules

- Do not edit `waihona.lock.json` or `waihona.def` by hand; rerun the script.
- `stale` means the snapshot is outside the age window and may not show what the author saw. Flag it.
- Papers under review get no edits: run this on the camera-ready/release copy.
- Not covered yet: DOIs/arXiv/ePrint links (stable; skipped only if you list them in `--skip`, not implemented),
  URLs built by macros, URLs in PDFs.
