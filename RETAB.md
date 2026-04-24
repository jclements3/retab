# Retab — seven levels of SATB-to-harp tabulation

**Retab** (from *tabulation* — the historical term for arranging vocal
polyphony into keyboard notation, as in Renaissance keyboard tablatures) is
the counterpart to reharm. Where reharm changes the chords under a melody,
**retab changes the texture** — taking a four-part SATB hymn and rendering
it as an idiomatic composition for 47-string lever harp.

The axis of difficulty isn't "distance from the original harmony" — it's
**distance from the vocal texture toward idiomatic harp composition**.

## Level 1 — Close-score keyboard reduction

Take SATB as-is. Soprano + alto go in the RH, tenor + bass in the LH. Four
attacks per beat in a compact two-octave range. Sounds like a pianist
sight-reading a hymnal. No harp idiom yet — strings can't damp between
attacks, so on harp this turns to mud. Useful only as a starting point.

## Level 2 — Lead-sheet reduction (melody + chord)

Drop the inner voices. Keep the soprano as-is in the RH. In the LH, replace
the literal bass note with the chord symbol's root. Grand staff, two attacks
per bar in LH. Much cleaner than L1 on harp, but under-uses the instrument.

## Level 3 — Trefoil block-135

Replace the LH root with a diatonic **block 135** triad (root + 3rd + 5th,
all diatonic, all stacked) drawn from the trefoil vocabulary. Struck once
per beat. This is the baseline Retab Hymnal sound — sits comfortably in
octave 2, rings sympathetically, doesn't fight the melody.

## Level 4 — Phrase-role articulation

Stop striking the same block on every beat. Vary the rhythm by
**phrase role**:

| Phrase role      | Articulation                          |
|---               |---                                    |
| opening          | single block, full bar                |
| middle           | two half-bar blocks                   |
| cadence_approach | arpeggio 1–3–5, 5th sustained         |
| cadence          | single block, full bar                |

The tune starts *breathing* — arrivals feel different from motion.

## Level 5 — Structural low-bass anchors

Exploit the bottom of the 47-string range. On opening and cadence bars, add
the root an octave below the triad (octave 1) — struck once on beat 1, then
ring. This turns C1–B1 strings from "drumming range" into structural pedal
tones. Used sparsely; if every bar gets one, it becomes a pulse and kills
the effect.

## Level 6 — Trefoil-path contour matching

Look at the direction of harmonic motion from chord to chord and pick the
trefoil voicing that matches:

- Motion by **4ths clockwise** (I→IV, V→I — most common in hymns) →
  ascending arpeggio or rising open voicing
- Motion by **4ths counter-clockwise** (I→V, ii→vi) → descending figure
- Motion by **3rds** (I→iii, vi→I) → common-tone pivot; only the non-common
  notes move
- Motion by **2nds** (iii→IV, V→vi) → stepwise inner-voice motion, outer
  notes held

The LH now *responds* to the chord progression's shape instead of being a
static template. This is where a retab starts sounding composed.

## Level 7 — Full harp texture

All of the above plus genuine harp idiom:

- **Rolled chords** (⌇) on arrivals — the attack itself becomes expressive
- **Glissando** between phrases over the diatonic collection, filling rests
  and breath points
- **Counter-melody** in the LH's top voice when the soprano sustains a long
  note — borrow the tenor/alto line dropped in L2 and re-introduce it only
  where the melody rests
- **Octave doubling** of the melody in the RH on the final cadence (climax)
- **Bisbigliando** (two fingers alternating on the same string) for held
  tonic pedals
- **String damping** (⊕) explicitly marked only where consecutive stepwise
  notes would clash — the rest rings freely

At L7 the arrangement is no longer a reduction — it's an idiomatic harp
composition whose skeleton happens to be a hymn.

---

## Status of the Retab Hymnal

The `hymnal/retab_hymnal.py` emitter currently lands at **L6 (partial L7)**
for all 279 hymns in the OpenHymnal corpus:

- L3: block-135 trefoil always applied ✅
- L4: phrase-role articulation (opening/middle/cadence_approach/cadence) ✅
- L5: octave-1 low-bass ditto on opening + cadence bars ✅
- L6: contour matching ✅
  - Cadence-approach arpeggio direction matches motion to the cadence chord
    (ascending for rising-4th cadences V→I / ii→V; descending for
    falling-4th / plagal IV→I)
  - Middle-bar anticipation: when the next bar's chord differs AND there
    are ≥4 beat groups, the second half-bar walks toward the new chord's
    root via a directional arpeggio instead of repeating the block
- L7: ✅ (core moves in)
  - Rolled chords (`!arpeggio!`) on the low-bass opening + cadence strikes
    — C1–B1 arrivals read as a harp wash instead of a piano attack
  - Final-cadence RH octave doubling — the hymn's last bar is rendered as
    two-note chords (melody + octave above), climaxing into octaves 5–6
  - Counter-motion under sustained soprano — middle bars where the
    melody is one long held note get a running 1-3-5-3 LH arpeggio instead
    of the usual two-block pattern
  - Still to come: glissandos between phrases, bisbigliando on held tonic
    pedals (rare enough in the corpus to defer)
