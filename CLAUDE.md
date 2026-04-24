# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`retab` is a small document-authoring workspace (not a code project, no build system, not a git repo). It contains two unrelated deliverables and the fonts used to render them.

- `handout.tex` — LaTeX source for the **HarpChords** reference handout: a printed one/two-pager documenting a chord-naming system for lever harp. It enumerates every strict-diatonic 2–4-finger voicing (span ≤ 10 strings) in C, cross-tabulated across the 7 diatonic modes (Ionian…Locrian). The document is a dense `longtable` of ~129 shapes \xD7 7 modes plus a grammar legend.
- `GENRES.md` — A flat reference list of music genres and sub-genres. Hierarchical bullet list, no code. `GENRES.md~` is an editor backup and should be ignored.
- `fonts/` — JuliaMono in every weight (TTF + WOFF2 in `fonts/webfonts/`) plus the upstream tarball `JuliaMono.tar.gz` and its `LICENSE`. These ship with the repo so the handout/web copies render identically anywhere.

## The HarpChords notation (handout.tex)

When editing the handout, these are the invariants the table and the grammar section must stay consistent on — they are easy to break silently:

- **Shape**: starting scale-degree + diatonic interval deltas (inclusive: `3` = up a 3rd). `t` is the ASCII stand-in for `\top` = 10. Span = (sum of intervals) − (fingers − 1).
- **Name grammar**: `<root><triad-qual?><quality?><additions…>_<omissions?>^<inversion?>`. Subscripts mark *low-octave* triad-pitch omissions; a matching upper-octave copy does **not** fill a low omission. This is the subtle rule most edits get wrong.
- **Absolute pitch**: every name specifies exactly which strings are played; pitch classes are never collapsed across octaves. All 903 names are globally unique — if you add or rename rows, re-check uniqueness.
- Row ordering in the main `longtable` is `(finger-count, span, pattern lex)`.
- Qualities: `s2` sus2, `s4` sus4, `q` quartal triad, `q7` quartal 7, `h7` half-dim 7 (Locrian only), `+8` triad + octave-doubled root.

## Build

No Makefile. The handout uses `\usepackage{fontspec}` and `\setmonofont`, so it must be compiled with **XeLaTeX** or **LuaLaTeX**, not pdfLaTeX:

```
xelatex handout.tex
```

The current `\setmonofont{DejaVu Sans Mono}` relies on a system font; the bundled JuliaMono is not currently wired into `handout.tex` — swapping the monofont to JuliaMono is a one-line change if desired.
