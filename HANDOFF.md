# Retab HANDOFF

Sync document between Claude chats on different machines working on the retab
ecosystem. The next Claude reads this file first to pick up where the
previous Claude left off. Each session appends a dated entry at the top.

---

## 2026-04-23 (late) — L6 contour matching + L7 rolled chords

Advanced the emitter from L5 to **L6 + partial L7** (per the ladder in
`RETAB.md`).

### L6 additions (`lh_pattern`)

- New `cycle_type(from_deg, to_deg)` classifies the diatonic interval
  between consecutive chord roots as (interval_class, direction) where
  class ∈ {0: same, 1: 2nd, 2: 3rd, 3: 4th} and direction ∈ {up, down}.
- **Cadence-approach arpeggio direction** — was always ascending 1-3-5.
  Now descending 5-3-1 when the cadence chord is a falling-4th away
  (plagal IV→I, I→V, etc.). Ascending stays the default (covers V→I, ii→V
  and same-chord cadences).
- **Middle-bar anticipation** — middle bars used to be two identical
  half-bar blocks. Now, when `next_chord != current_chord` AND
  `num_groups ≥ 4`, the second half walks toward the next chord's root
  via a directional arpeggio. Short bars (≤2 beat groups) and
  same-chord middles fall back to two blocks.
- `build_abc` now pre-computes all bar degrees in a list so `lh_pattern`
  receives a `next_degree` lookahead argument.

### L7 partial — rolled chords on structural strikes

The low-bass ditto block (opening + cadence bar, beat 1) is now decorated
with `!arpeggio!` in the emitted ABC, which renders as the wavy-line roll
mark in abcm2ps. On harp that's a sweeping strum from root up — the
signature arrival sound. Single-line change: the `ditto_block` definition
prepends `!arpeggio!`.

### Still to come at L7

- Glissandos between phrases (over the diatonic collection, filling rests)
- Counter-melody in LH top voice when soprano sustains a long note
  (borrow the alto/tenor line)
- RH octave doubling on the final cadence melody note (climax)
- Bisbigliando on held tonic pedals

All 279 hymns still compile. SVGs regenerated into tablet assets; APK
rebuilt and installed.

---

## 2026-04-23 — Retab Hymnal shipped

Built and installed the **Retab Hymnal**: all 279 hymns from OpenHymnal
rendered as trefoil-LH + melody grand-staff scores, browsable on the Android
tablet via a new home-screen tile. Home screen is now four tiles:
**Retab** (100 drills) → **Retab Hymnal** (279 hymns) → **Reharm** (19 jazz
tiles, behind sub-page) → **Hymns** (292 original SATB hymns).

### Where the work lives

- **Emitter**: `retab/hymnal/retab_hymnal.py` — consumes one
  `HarpHymnal/data/hymns/<slug>.json` record, emits a grand-staff ABC file.
- **Bulk builder**: `retab/hymnal/build_hymnal.py` — iterates the full corpus,
  runs abcm2ps per hymn, post-processes SVGs with viewBox, writes
  `retab/hymns/<slug>.svg` into the tablet assets dir plus a
  `retab_hymns.js` index.
- **Tablet assets** (NOT in this repo; in the `HarpHymnal` workspace next door):
  - `HarpHymnal/tablet_app/app/src/main/assets/retab/hymns/*.svg` (279 files)
  - `HarpHymnal/tablet_app/app/src/main/assets/retab/retab_hymns.js`
  - `HarpHymnal/tablet_app/app/src/main/assets/index.html` (viewer + index UI)

### Emitter design — what's in it

Per bar, the emitter knows the melody (V1, pass-through) and the chord
({numeral, quality, inversion}). It generates an LH trefoil block-135 pattern
(V2) whose rhythm is picked by **phrase_role**, the same tactic the reharm
algorithms use (see `HarpHymnal/REHARM_TACTICS.md`). Phrase roles are
assigned positionally from `hymn.phrases[].ibars`:

| Role | LH pattern |
|---|---|
| opening | single triad block filling the bar |
| middle | two equal half-bar triad blocks |
| cadence_approach | arpeggio 1–3–5, 5th sustained |
| cadence | single triad block filling the bar |

**Range plan** (from the "exploit the 47-string capability" directive):

- **Octave 2** — LH triad for all keys. C2 is safe; the drumming range is
  C1–B1 only (not C1–C2 as earlier conversation guessed).
- **Octave 1** — low-bass ditto (root-only, struck *once* on beat 1) added
  on opening + cadence bars as a structural pedal anchor. Single strike, not
  rhythm, so C1–B1 strings read as arrivals not drumming.
- **Octave 4–5** — RH melody as-given.
- **Octave 5–6** — RESERVED for future final-cadence climax doubling (not
  yet implemented; see "open ideas" below).

**Important implementation notes** (non-obvious, future-you will trip on these):

1. **Duration unit detection** (`detect_duration_multiplier`) — hymn JSON
   `duration` values are in whatever unit the source ABC's `L:` was
   (quarter, eighth, half…). The emitter figures this out per-hymn by
   comparing the most common bar-sum to the meter's expected bar length in
   sixteenths. Don't assume duration is in quarter-notes.
2. **Safe durations** (`_SAFE_DURS` + `_safe_note_dur`) — abcm2ps can only
   notate certain integer sixteenth counts as a single (possibly dotted)
   note. Anything else (e.g. `18` for a 9/8 bar block) must be split into
   tied segments. Applied to both V1 melody and V2 LH.
3. **Compound meter** (`beat_group_sixteenths`) — 6/8, 9/8, 12/8 group
   eighths in threes (dotted-quarter beats). Getting this wrong produced
   "Note too much dotted" abcm2ps errors on ~3 hymns.
4. **Flexible bar widths** (`pack_lines` + `LINE_BUDGET=65`) — content-aware
   bar packing: bars with many tokens claim more of a line, sparse bars
   pack tighter. Replaces the earlier naïve "4 bars per line". 0.75 scale
   via `%%scale 0.75`.
5. **Chord annotation font switch** — uses abcm2ps inline `$1`/`$2`/`$0`
   escapes to render the Roman numeral in bold and the quality/inversion
   in italic, matching the HarpChords handout style. Requires
   `%%setfont-1 Times-Bold` and `%%setfont-2 Times-Italic` directives in
   the header.

### Tablet UI additions

`index.html` gained:
- `.tile.retabhymnal` CSS + new tile in the home grid.
- `#retabhymnal` section with **burgundy** (#7B2121) banner, search bar,
  A–Z collapsible letter-group index (mirrors the existing `#hymns`
  pattern), SVG pane, prev/next footer.
- `renderRetabHymnalIndex()`, `showRetabHymnalCard()`, etc.
- Titles are prefixed with a zero-padded 3-digit number (`001.`, `002.`, …)
  alphabetically by title, so the harpist and Claude can communicate by
  number ("play 042").

A second independent change this session (done by a parallel agent): the old
jazz/pool/substitution/approach/voicing tiles moved off the home screen into
a new **Reharm** sub-page (gold #C9A227 tile). Home screen is now
deliberately minimal.

### Build + install

```
cd /home/james.clements/projects/retab/hymnal
python3 build_hymnal.py          # → 279 SVGs + retab_hymns.js, ~30s
cd /home/james.clements/projects/HarpHymnal/tablet_app
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.harp.harphymnal.drills/.MainActivity
```

Takes maybe a minute end-to-end.

### Open ideas / likely next asks

- **Final-cadence RH climax** — double the melody an octave up on the last
  bar of the last phrase, using octaves 5–6. The range plan was drafted
  but not yet implemented.
- **Wider LH on tonic arrivals** — open voicing (root + 5 + 10) on
  mid-phrase tonic returns for a "grander" texture.
- **OpenHymnal hymn overlay** — user mentioned early in the session that the
  harphymnal pipeline already parses ABC and identifies chords; a future
  feature would overlay the retab treatment on top of the existing
  HarpHymnal SATB rendering so the harpist can toggle between views.
- **4 known quirky hymns** — 9/8 and 3/2 time sigs landed clean after the
  duration-detection + safe-dur fixes. No known remaining failures in the
  corpus, but if new hymns get added watch for: anacrusis bars with sum
  != meter, and exotic meters like 5/4.

### Related files in this repo (unchanged this session but relevant)

- `drills.abc` — master 100-drill catalog. Compile with
  `abcm2ps drills.abc -O drills.ps && ps2pdf drills.ps drills.pdf`.
- `handoutC.tex` — HarpChords handout (chord vocabulary + rainbow modes).
  Compile with `xelatex handoutC.tex`.
- `DRILLS.md` — quick-reference drill guide (6 style drills, shape/rhythm/
  fingering/modes/path columns).
- `STYLE.md` — church-appropriate subset of `GENRES.md`.

---
