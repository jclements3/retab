#!/usr/bin/env python3
"""Retab Hymnal -- apply trefoil LH patterns + RH melody to HarpHymnal hymns.

Reads HarpHymnal's per-bar JSON (data/hymns/<slug>.json) and emits a grand-staff
ABC file. V1 = melody (as given). V2 = diatonic block-135 trefoil pattern,
rhythm chosen by phrase_role (same guide used by reharm/tactics.json):

    opening          whole-note block 135       (settle the phrase)
    middle           half-note block 135, twice (walk)
    cadence_approach arpeggio 1-3-5 quarters    (lift into cadence)
    cadence          whole-note block 135 root  (resolve)

The emitter is level-parameterised (RETAB.md, seven levels):

    L1  SATB close-score keyboard reduction (block chords, four per beat)
    L2  lead-sheet (melody + root, two attacks/bar)
    L3  trefoil block-135 triads (no piano stomp)
    L4  L3 + phrase-role articulation
    L5  L4 + structural low-bass anchors (C1-B1)
    L6  L5 + trefoil-path contour matching
    L7  L6 + full harp texture (rolled chords, octave melody,
        counter-melody, bisbigliando)

Compile with:  abcm2ps <out.abc> -O <name> -g    (per-tune SVG)
"""

from __future__ import annotations
import copy
import json
import re
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Diatonic scale utilities

LETTERS = ["C", "D", "E", "F", "G", "A", "B"]

# Major-key key signature: number of sharps/flats in order.
KEY_SIG = {
    "C":  ([], []),
    "G":  (["F"], []),
    "D":  (["F", "C"], []),
    "A":  (["F", "C", "G"], []),
    "E":  (["F", "C", "G", "D"], []),
    "B":  (["F", "C", "G", "D", "A"], []),
    "F#": (["F", "C", "G", "D", "A", "E"], []),
    "F":  ([], ["B"]),
    "Bb": ([], ["B", "E"]),
    "Eb": ([], ["B", "E", "A"]),
    "Ab": ([], ["B", "E", "A", "D"]),
    "Db": ([], ["B", "E", "A", "D", "G"]),
    "Gb": ([], ["B", "E", "A", "D", "G", "C"]),
}

ROMAN_TO_DEGREE = {
    "I": 0, "ii": 1, "iii": 2, "IV": 3, "V": 4, "vi": 5, "vii": 6,
    "i": 0, "II": 1, "III": 2, "iv": 3, "v": 4, "VI": 5, "VII": 6,
    # minor-key Aeolian mapped through Ionian-relative (i→vi etc.) by caller
}

# Aeolian → Ionian relative translation (from REHARM_TACTICS.md)
AEOLIAN_TO_IONIAN = {
    "i": "vi",
    "ii": "vii", "ii°": "vii",
    "III": "I",
    "iv": "ii",
    "v": "iii", "V": "iii",
    "VI": "IV", "bVI": "IV",
    "VII": "V", "bVII": "V",
}


def parse_roman(numeral: str) -> int:
    """Return 0..6 scale-degree of a roman numeral (I=0, ii=1, …, vii=6)."""
    if numeral is None:
        return 0
    # Strip leading flats/sharps
    n = numeral.lstrip("b♭#♯")
    # Strip quality tails
    n = re.split(r"[°ø+\-0-9]", n)[0]
    return ROMAN_TO_DEGREE.get(n, 0)


def relative_major(key_root: str, mode: str) -> str:
    """Return the relative-major key root for an Aeolian/minor key."""
    if mode in ("major", "ionian"):
        return key_root
    # minor/aeolian: relative major = minor-tonic + minor-3rd up
    # A minor → C major, E minor → G major, etc.
    idx = LETTERS.index(key_root[0])
    rel_letter = LETTERS[(idx + 2) % 7]
    # Accidentals on rel major for flat/sharp minor keys (informative; we keep
    # the ABC K: header as the relative-major label so the staff shows the
    # right key signature).
    overrides = {"A": "C", "E": "G", "B": "D", "D": "F", "G": "Bb", "C": "Eb",
                 "F": "Ab", "Bb": "Db", "Eb": "Gb"}
    return overrides.get(key_root, rel_letter)


# -----------------------------------------------------------------------------
# ABC pitch rendering

def scale_degree_to_abc(degree: int, key_root: str, abs_octave: int) -> str:
    """Render a diatonic scale-degree as ABC text at a specific absolute octave.

    `abs_octave` is scientific-pitch octave (C4 = middle C).
    """
    # Letter at this degree above the tonic.
    tonic_idx = LETTERS.index(key_root[0])
    letter = LETTERS[(tonic_idx + degree) % 7]
    # Determine actual scientific octave: advance octave as we wrap past B.
    # The scale-degree rise from tonic may cross the octave boundary once.
    # Here 'abs_octave' is the octave of the TONIC that degree 0 sits in.
    new_letter_idx = (tonic_idx + degree) % 7
    oct_add = (tonic_idx + degree) // 7
    real_oct = abs_octave + oct_add

    # ABC: uppercase = octave 4, lowercase = octave 5.
    # Adjust: C4 = "C", C5 = "c", C3 = "C,", C2 = "C,,", C6 = "c'", C7 = "c''".
    if real_oct >= 5:
        s = letter.lower()
        s += "'" * (real_oct - 5)
    else:
        s = letter.upper()
        s += "," * (4 - real_oct)
    return s


# -----------------------------------------------------------------------------
# Duration units — the JSON `duration` field is what music21 reported for the
# source ABC's default note length (L:1/4 → quarters, L:1/8 → eighths, etc.).
# We detect the hymn's unit from the most common bar-sum and normalise to ABC
# L:1/16 sixteenths.

def detect_duration_multiplier(hymn: dict) -> int:
    """Return sixteenths-per-duration-unit for this hymn."""
    from collections import Counter
    beats = hymn["meter"]["beats"]
    unit = hymn["meter"]["unit"]
    expected_16ths = beats * 16 // unit  # 3/4 → 12, 9/8 → 18, 6/8 → 12, 3/2 → 24
    sums = []
    for b in hymn["bars"]:
        s = sum(e["duration"] for e in b["melody"])
        if s > 0:
            sums.append(s)
    if not sums:
        return 4  # default: quarter-note
    typical = Counter(sums).most_common(1)[0][0]
    mult = expected_16ths / typical
    # Round to nearest small integer if close (mult should be 2, 4, 8, or similar).
    for candidate in (1, 2, 4, 8, 16):
        if abs(mult - candidate) < 0.1:
            return candidate
    return max(1, int(round(mult)))


# -----------------------------------------------------------------------------
# Melody rendering (V1) — pass through from hymn JSON

def pitch_to_abc(pitch: dict) -> str:
    """{letter, accidental, octave} → ABC token (letter+accidentals+octmark)."""
    letter = pitch["letter"]
    acc = pitch.get("accidental")
    octv = pitch["octave"]
    prefix = {"sharp": "^", "flat": "_", "natural": "="}.get(acc, "")
    if octv >= 5:
        s = letter.lower() + "'" * (octv - 5)
    else:
        s = letter.upper() + "," * (4 - octv)
    return prefix + s


def _safe_note_dur(token: str, n: int) -> str:
    """Emit `token` for n sixteenths, splitting+tying if unrepresentable."""
    if n <= 0:
        return ""
    if n in _SAFE_DURS:
        return token if n == 1 else f"{token}{n}"
    for cand in sorted(_SAFE_DURS, reverse=True):
        if cand < n:
            return f"{token}{cand}-{_safe_note_dur(token, n - cand)}"
    return f"{token}{n}"


def chord_label(chord: dict | None) -> str:
    """Format {numeral, quality, inversion} as a Roman-numeral annotation.

    Uses abcm2ps inline font switching: $1 = Times-Bold (numeral),
    $2 = Times-Italic (quality + superscript inversion).
    """
    if not chord:
        return ""
    num = chord.get("numeral") or ""
    if not num:
        return ""
    q = chord.get("quality")
    inv = chord.get("inversion")
    q_map = {
        "M7": "Δ⁷",
        "maj7": "Δ⁷",
        "7": "⁷",
        "m7": "m⁷",
        "dim7": "°⁷",
        "half_dim7": "ø⁷",
        "dim": "°",
        "aug": "+",
    }
    suffix = q_map.get(q, q or "")
    if inv is not None and inv != 0 and inv != "0":
        sup_map = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
        suffix += str(inv).translate(sup_map)
    # Bold numeral, italic quality/inversion. $0 returns to the default font
    # so any following characters (there usually aren't any) aren't affected.
    if suffix:
        return f"$1{num}$2{suffix}$0"
    return f"$1{num}$0"


def _pitch_doubled(pitch: dict) -> str:
    """Return a two-note ABC chord: the pitch plus its octave doubling."""
    lo = pitch_to_abc(pitch)
    hi = pitch_to_abc({**pitch, "octave": pitch["octave"] + 1})
    return f"[{lo}{hi}]"


def render_melody_bar(bar: dict, mult: int, octave_double: bool = False) -> str:
    """Emit melody bar; prepend chord annotation (if any) to the first event.

    When `octave_double` is True (the hymn's final cadence bar), each melody
    note is struck as a two-note chord with an octave above — RH climax into
    the harp's upper register (octaves 5–6).
    """
    toks = []
    label = chord_label(bar.get("chord"))
    annotation = f'"^{label}"' if label else ""
    first = True
    for ev in bar["melody"]:
        n = int(round(ev["duration"] * mult))
        if ev["kind"] == "rest":
            tok = _safe_note_dur("z", n)
        else:
            note_tok = _pitch_doubled(ev["pitch"]) if octave_double \
                       else pitch_to_abc(ev["pitch"])
            tok = _safe_note_dur(note_tok, n)
        if first and annotation and tok:
            tok = annotation + tok
            first = False
        elif tok:
            first = False
        toks.append(tok)
    return " ".join(t for t in toks if t)


def _bar_has_long_hold(bar: dict, threshold: float) -> bool:
    """True if any single note consumes ≥ `threshold` fraction of the bar."""
    events = bar.get("melody") or []
    total = sum(ev["duration"] for ev in events)
    if total <= 0:
        return False
    longest = max(
        (ev["duration"] for ev in events if ev.get("kind") == "note"),
        default=0,
    )
    return longest / total >= threshold


def is_sustained_melody(bar: dict) -> bool:
    """True if this bar is dominated by a single long note (≥ 50% of bar).

    Signals an L7 opportunity: the LH can move more actively (arpeggio) while
    the melody rests.
    """
    events = bar.get("melody") or []
    if not events:
        return False
    total = sum(ev["duration"] for ev in events)
    if total <= 0:
        return False
    longest = max(
        (ev["duration"] for ev in events if ev.get("kind") == "note"),
        default=0,
    )
    return longest / total >= 0.5


def bar_length_sixteenths(bar: dict, mult: int) -> int:
    """Exact length of this bar's melody in sixteenths."""
    total = sum(ev["duration"] for ev in bar["melody"])
    return int(round(total * mult))


# -----------------------------------------------------------------------------
# LH trefoil pattern (V2)

# LH root at octave 2 for all keys. C2 sits just above the drumming range
# (which, per the harpist, spans C1–B1). Low-bass ditto at octave 1 is added
# only on structural anchors (opening + cadence) so C1–B1 strings sound as
# deep pedal tones rather than drumming.
LH_TRIAD_OCTAVE = 2
LH_DITTO_OCTAVE = 1


# Durations representable as a single ABC note/chord (0-2 augmentation dots).
# e.g. 4=quarter, 6=dotted-quarter, 7=double-dotted-quarter, 8=half, 12=dotted-half.
_SAFE_DURS = {1, 2, 3, 4, 6, 7, 8, 12, 14, 16, 24, 28, 32}


_safe_chord = _safe_note_dur  # same algorithm for chords and single notes


def beat_group_sixteenths(beats: int, unit: int) -> int:
    """Sixteenths per musical beat-group. Compound meters group eighths in 3s."""
    if unit == 8 and beats % 3 == 0 and beats >= 6:
        return 6  # compound: dotted-quarter
    if unit <= 0:
        return 4
    return max(1, 16 // unit)  # simple: one denominator note


# -----------------------------------------------------------------------------
# L6 — trefoil-path contour matching.
#
# Classify motion between two chord-roots (diatonic scale degrees 0..6) as
# (interval_class, direction) where interval_class is:
#   0  same chord
#   1  motion by a 2nd (stepwise)
#   2  motion by a 3rd (common-tone pivot territory)
#   3  motion by a 4th (the most common — V→I, ii→V, IV→I)
# …and direction is 'up' or 'down' from the current chord to the target.

def cycle_type(from_deg: int | None, to_deg: int | None) -> tuple[int, str | None]:
    if from_deg is None or to_deg is None:
        return (0, None)
    up = (to_deg - from_deg) % 7
    down = (from_deg - to_deg) % 7
    if up == 0:
        return (0, None)
    if up <= down:
        return (up if up <= 3 else 7 - up, "up")
    return (down if down <= 3 else 7 - down, "down")


def lh_pattern(degree: int, key_root: str, phrase_role: str,
               total_sixteenths: int, beats: int, unit: int,
               next_degree: int | None = None,
               melody_sustained: bool = False,
               level: int = 7) -> str:
    """Emit bass-clef trefoil pattern filling exactly `total_sixteenths`.

    The `level` parameter gates features top-down:
      - L3: block-135 triad, "no piano stomp" walking; role ignored.
      - L4: phrase-role articulation (opening/middle/cadence_approach/cadence).
      - L5: + low-bass octave ditto on opening + cadence (bare block).
      - L6: + trefoil-path contour matching (direction-aware arpeggios,
        3rd-motion common-tone pivot).
      - L7: + rolled (!arpeggio!) ditto, counter-melody under sustained
        soprano.

    L1 and L2 bypass this function entirely (see `lh_satb_block` and
    `lh_leadsheet`).
    """
    if total_sixteenths <= 0:
        return ""

    r = scale_degree_to_abc(degree, key_root, LH_TRIAD_OCTAVE)
    t = scale_degree_to_abc(degree + 2, key_root, LH_TRIAD_OCTAVE)
    f = scale_degree_to_abc(degree + 4, key_root, LH_TRIAD_OCTAVE)
    block = f"[{r}{t}{f}]"

    # L5: low-bass ditto on opening + cadence, struck once at beat 1 an
    # octave below the triad. L7: that same ditto is rolled (!arpeggio!)
    # for the idiomatic harp wash on arrivals; at L5-L6 it's a bare block.
    ditto_block = None
    if level >= 5 and phrase_role in ("opening", "cadence"):
        ditto = scale_degree_to_abc(degree, key_root, LH_DITTO_OCTAVE)
        roll = "!arpeggio!" if level >= 7 else ""
        ditto_block = f"{roll}[{ditto}{r}{t}{f}]"

    beat_16 = beat_group_sixteenths(beats, unit)
    if beat_16 > 0 and total_sixteenths % beat_16 == 0:
        num_groups = total_sixteenths // beat_16
    else:
        num_groups = 0

    # L3 baseline: ignore phrase role entirely. Every bar gets the same
    # "no piano stomp" walk recipe -- single strike if the bar is one
    # beat group, otherwise a walking arpeggio through chord tones.
    if level < 4:
        if num_groups >= 2:
            cycle = [r, t, f, t]
            cells = [cycle[i % 4] for i in range(num_groups)]
            return " ".join(_safe_chord(c, beat_16) for c in cells)
        return _safe_chord(block, total_sixteenths)

    # -------------------------------------------------------------------
    # Harp idiom rule: never re-strike the same triad on consecutive beats.
    # Either (a) strike once and let ring, or (b) walk through different
    # chord tones so each beat hits a fresh string -- by the end of the bar
    # all three strings are ringing together anyway.
    # -------------------------------------------------------------------

    # OPENING + CADENCE: single strike filling the whole bar (with the L5
    # low-bass ditto rolled up through the triad). Let it ring.
    if phrase_role in ("opening", "cadence"):
        return _safe_chord(ditto_block or block, total_sixteenths)

    # L6+: contour-matched cadence approach (direction keyed on motion to
    # cadence chord). L4-L5 fall through to the default ascending 1-3-5.
    if phrase_role == "cadence_approach" and num_groups >= 3:
        tail_dur = (num_groups - 2) * beat_16
        direction = None
        if level >= 6:
            _, direction = cycle_type(degree, next_degree)
        if direction == "down":
            return (
                _safe_chord(f, beat_16) + " " +
                _safe_chord(t, beat_16) + " " +
                _safe_chord(r, tail_dur)
            )
        return (
            _safe_chord(r, beat_16) + " " +
            _safe_chord(t, beat_16) + " " +
            _safe_chord(f, tail_dur)
        )

    # MIDDLE -- all cases walk through chord tones instead of stomping.
    if phrase_role == "middle" and num_groups >= 2:
        ic, direction = (0, None)
        if level >= 6:
            ic, direction = cycle_type(degree, next_degree)

        # L7: sustained melody -> running 1-3-5-3 arpeggio (motion under a
        # held soprano).
        if level >= 7 and melody_sustained and num_groups >= 4:
            arp = [r, t, f, t]
            cells = [arp[i % 4] for i in range(num_groups)]
            return " ".join(_safe_chord(c, beat_16) for c in cells)

        # Static chord (no motion) -- walking arpeggio across the bar.
        # Pattern depends on bar length:
        #   2 groups: R T     (each note rings the other half, both sound)
        #   3 groups: R T F   (triad walk)
        #   4+ groups: R T F T R T F T ... (cycle)
        if ic == 0:
            if num_groups == 2:
                return _safe_chord(r, beat_16) + " " + _safe_chord(t, beat_16)
            if num_groups == 3:
                return " ".join(_safe_chord(n, beat_16) for n in (r, t, f))
            cycle = [r, t, f, t]
            cells = [cycle[i % 4] for i in range(num_groups)]
            return " ".join(_safe_chord(c, beat_16) for c in cells)

        # L6+: chord change coming -- strike block on beat 1 (let ring half
        # bar) then anticipate the next chord with a directional arpeggio.
        if num_groups >= 4 and num_groups % 2 == 0:
            half = (num_groups // 2) * beat_16
            a_dur = beat_16
            b_dur = half - beat_16
            if ic == 2:
                if direction == "up":
                    anticip = _safe_chord(t, a_dur) + " " + _safe_chord(f, b_dur)
                else:
                    anticip = _safe_chord(r, a_dur) + " " + _safe_chord(t, b_dur)
            else:
                if direction == "down":
                    anticip = _safe_chord(f, a_dur) + " " + _safe_chord(t, b_dur)
                else:
                    anticip = _safe_chord(t, a_dur) + " " + _safe_chord(f, b_dur)
            return _safe_chord(block, half) + " " + anticip

        # Short bar with a chord change -- walking arpeggio, ending on the
        # note closest to the next chord's root.
        if num_groups == 2:
            second = f if direction == "up" else r
            return _safe_chord(r, beat_16) + " " + _safe_chord(second, beat_16)
        if num_groups == 3:
            return " ".join(_safe_chord(n, beat_16) for n in (r, t, f))

    # Fallback: single strike, let ring.
    return _safe_chord(ditto_block or block, total_sixteenths)


# -----------------------------------------------------------------------------
# Phrase role assignment

def assign_phrase_roles(n_bars: int, phrases: list) -> list:
    """Return a list of phrase_role strings, one per bar (1-indexed input)."""
    roles = ["middle"] * n_bars
    for ph in phrases:
        ibars = ph["ibars"]
        if not ibars:
            continue
        roles[ibars[0] - 1] = "opening"
        roles[ibars[-1] - 1] = "cadence"
        if len(ibars) >= 3:
            roles[ibars[-2] - 1] = "cadence_approach"
    return roles


# -----------------------------------------------------------------------------
# Level passes -- each returns a copy of the hymn tagged with `_level`, which
# `build_abc` reads to feature-gate the renderer. Retab's level ladder is
# about *texture* (vs. reharm's *harmony*), so the passes mostly flip feature
# switches rather than rewriting the hymn dict itself -- the heavy lifting is
# inside `lh_pattern`, `render_melody_bar`, and `build_abc`, gated by the
# level. The one exception is L1, which bypasses the trefoil pipeline entirely
# in favour of an SATB-style block-chord reduction.

def _tag_level(hymn: dict, level: int) -> dict:
    out = copy.deepcopy(hymn)
    out["_retab_level"] = level
    return out


def apply_level_1(hymn: dict) -> dict:
    """L1 -- SATB close-score keyboard reduction.

    Soprano on V1 (melody as given). V2 plays a synthesised alto+tenor+bass
    block chord on every melody attack -- four attacks per beat when the
    melody subdivides, so the texture is dense and piano-ish. No trefoil,
    no phrase-role articulation, no walking. Deliberately "mud" on harp,
    which is the point: L1 motivates the climb up the ladder.
    """
    return _tag_level(hymn, 1)


def apply_level_2(hymn: dict) -> dict:
    """L2 -- lead-sheet reduction. Melody on V1; LH plays the chord's root
    twice per bar at half the melody's attack rate. No triads, no trefoil.
    """
    return _tag_level(hymn, 2)


def apply_level_3(hymn: dict) -> dict:
    """L3 -- trefoil block-135 triads (the canonical "this is Retab" level).

    LH emits the diatonic root+3rd+5th triad once per chord. No-piano-stomp
    rule: never re-strike the same triad on consecutive beats -- walk
    through chord tones when the bar has multiple beat-groups. No phrase-
    role articulation yet; every bar uses the same walking recipe.
    """
    return _tag_level(hymn, 3)


def apply_level_4(hymn: dict) -> dict:
    """L4 -- L3 + phrase-role articulation. Rhythm varies by opening /
    middle / cadence_approach / cadence. Still static block triads -- no
    low-bass anchors, no contour matching.
    """
    return _tag_level(hymn, 4)


def apply_level_5(hymn: dict) -> dict:
    """L5 -- L4 + structural low-bass anchors. On opening/cadence bars,
    add the root an octave below the triad (C1-B1 range), struck once and
    let ring. Still block-only (not rolled) at this level.
    """
    return _tag_level(hymn, 5)


def apply_level_6(hymn: dict) -> dict:
    """L6 -- L5 + trefoil-path contour matching. Voicing responds to the
    direction of harmonic motion between chords (4ths up/down, 3rd pivot,
    2nds stepwise). Low-bass anchors are still bare blocks (no roll).
    """
    return _tag_level(hymn, 6)


def apply_level_7(hymn: dict) -> dict:
    """L7 -- everything on. L6 + rolled chords on anchors, final-cadence
    octave doubling in the melody, counter-melody arpeggio under sustained
    soprano, bisbigliando on the final tonic hold.
    """
    return _tag_level(hymn, 7)


RETAB_LEVELS = {
    1: apply_level_1,
    2: apply_level_2,
    3: apply_level_3,
    4: apply_level_4,
    5: apply_level_5,
    6: apply_level_6,
    7: apply_level_7,
}


# -----------------------------------------------------------------------------
# L1 SATB block-chord LH (bypasses the trefoil pipeline)

def lh_satb_block(bar: dict, degree: int, key_root: str, mult: int) -> str:
    """Emit a V2 bar that strikes a block A-T-B chord on every melody attack.

    Alto sits a third above the tenor, tenor a third above the bass root.
    Crude but deliberately so -- this is the "piano-ish" baseline RETAB.md
    calls out.
    """
    root = scale_degree_to_abc(degree, key_root, LH_TRIAD_OCTAVE)
    third = scale_degree_to_abc(degree + 2, key_root, LH_TRIAD_OCTAVE)
    fifth = scale_degree_to_abc(degree + 4, key_root, LH_TRIAD_OCTAVE)
    block = f"[{root}{third}{fifth}]"
    toks = []
    for ev in bar["melody"]:
        n = int(round(ev["duration"] * mult))
        if n <= 0:
            continue
        if ev["kind"] == "rest":
            toks.append(_safe_note_dur("z", n))
        else:
            toks.append(_safe_chord(block, n))
    return " ".join(t for t in toks if t)


# -----------------------------------------------------------------------------
# L2 lead-sheet LH (root-only, two attacks per bar)

def lh_leadsheet(degree: int, key_root: str, total_sixteenths: int) -> str:
    """Emit a V2 bar that strikes the chord's root twice at half-bar points."""
    if total_sixteenths <= 0:
        return ""
    root = scale_degree_to_abc(degree, key_root, LH_TRIAD_OCTAVE)
    half = total_sixteenths // 2
    if half <= 0:
        return _safe_note_dur(root, total_sixteenths)
    rem = total_sixteenths - half
    a = _safe_note_dur(root, half)
    b = _safe_note_dur(root, rem) if rem > 0 else ""
    return (a + (" " + b if b else "")).strip()


# -----------------------------------------------------------------------------
# Build ABC output

def build_abc(hymn: dict, x_num: int = 1, num_prefix: str | None = None,
              level: int | None = None) -> str:
    title = hymn["title"]
    if num_prefix:
        title = f"{num_prefix}. {title}"
    key_root = hymn["key"]["root"]
    mode = hymn["key"]["mode"]
    meter_beats = hymn["meter"]["beats"]
    meter_unit = hymn["meter"]["unit"]
    bars = hymn["bars"]
    phrases = hymn["phrases"]

    # Resolution order for level: explicit arg wins, else hymn tag from a
    # level pass, else default to L7 (preserves the historical full-texture
    # output when called with a plain hymn dict).
    if level is None:
        level = hymn.get("_retab_level", 7)

    # For minor hymns, translate to relative major for the staff key signature
    # and translate roman numerals Aeolian->Ionian-relative so triads come out
    # diatonic in the surface key.
    if mode == "minor":
        effective_key = relative_major(key_root, mode)
    else:
        effective_key = key_root

    roles = assign_phrase_roles(len(bars), phrases)
    mult = detect_duration_multiplier(hymn)

    # L7: the final bar of the hymn is the climax -- RH melody doubled an
    # octave up into the 5-6 range. Disabled below L7.
    final_bar_idx = len(bars) - 1

    melody_bars = [
        render_melody_bar(
            b, mult,
            octave_double=(level >= 7 and i == final_bar_idx),
        )
        for i, b in enumerate(bars)
    ]

    # Pre-compute each bar's scale-degree so we can look ahead to the next
    # chord (enables L6 contour matching).
    degrees = []
    for bar in bars:
        chord = bar["chord"] or {}
        num = chord.get("numeral") or "I"
        if mode == "minor":
            num = AEOLIAN_TO_IONIAN.get(num, num)
        degrees.append(parse_roman(num))

    # LH V2: emitter path depends on level.
    #   L1 -- SATB block chord on every melody attack.
    #   L2 -- chord-root lead sheet, two attacks per bar.
    #   L3+ -- trefoil block-135, feature-gated inside lh_pattern.
    lh_bars = []
    for i, bar in enumerate(bars):
        bar_16ths = bar_length_sixteenths(bar, mult)
        if level == 1:
            pat = lh_satb_block(bar, degrees[i], effective_key, mult)
        elif level == 2:
            pat = lh_leadsheet(degrees[i], effective_key, bar_16ths)
        else:
            next_deg = degrees[i + 1] if i + 1 < len(degrees) else None
            sustained = is_sustained_melody(bar)
            pat = lh_pattern(
                degrees[i], effective_key, roles[i],
                bar_16ths, meter_beats, meter_unit,
                next_degree=next_deg,
                melody_sustained=sustained,
                level=level,
            )
        # L7 bisbigliando: only the hymn's FINAL cadence -- and only when
        # the final melody note is genuinely long (>= 95% of the bar).
        # A shimmer is a rare gesture; one per hymn is the ceiling.
        if (level >= 7 and i == final_bar_idx and degrees[i] == 0
                and _bar_has_long_hold(bar, 0.95)):
            pat = '"_bisb."' + pat
        lh_bars.append(pat)

    # Content-aware line packing: estimate each bar's rendered width from its
    # token count, accumulate bars into a line until a width budget is hit.
    # Result: dense bars claim more room, sparse bars pack 5-6 per line —
    # the number of bars per line varies by content.
    LINE_BUDGET = 65  # approximate char-width tuned for %%scale 0.75 output

    def bar_cost(v1: str, v2: str) -> int:
        # Tokens roughly correspond to note heads; chord-labels cost extra.
        tv1 = len(v1.split())
        tv2 = len(v2.split())
        # Count annotation overhead ("^..." labels add width)
        extra = v1.count('"^')
        return tv1 + tv2 + 3 * extra + 2

    def pack_lines(bar_pairs: list) -> tuple[list, list]:
        """Split parallel V1/V2 bar lists into lines of variable bar count."""
        v1_lines, v2_lines = [], []
        cur_v1, cur_v2, cur_cost = [], [], 0
        for v1, v2 in bar_pairs:
            c = bar_cost(v1, v2)
            if cur_v1 and cur_cost + c > LINE_BUDGET:
                v1_lines.append(" | ".join(cur_v1) + " |")
                v2_lines.append(" | ".join(cur_v2) + " |")
                cur_v1, cur_v2, cur_cost = [], [], 0
            cur_v1.append(v1)
            cur_v2.append(v2)
            cur_cost += c
        if cur_v1:
            v1_lines.append(" | ".join(cur_v1) + " |")
            v2_lines.append(" | ".join(cur_v2) + " |")
        return v1_lines, v2_lines

    abc = []
    abc.append(f"X:{x_num}")
    abc.append(f"T:{title}")
    abc.append(f"M:{meter_beats}/{meter_unit}")
    abc.append("L:1/16")
    abc.append(f"K:{effective_key}")
    abc.append("%%scale 0.75")
    abc.append("%%annotationfont Times-Italic 13")
    abc.append("%%setfont-1 Times-Bold 13")
    abc.append("%%setfont-2 Times-Italic 11")
    abc.append("%%score {V1 V2}")
    abc.append("V:V1 clef=treble")
    abc.append("V:V2 clef=bass")
    v1_lines, v2_lines = pack_lines(list(zip(melody_bars, lh_bars)))
    abc.append("[V:V1]")
    abc.extend(v1_lines)
    abc.append("[V:V2]")
    abc.extend(v2_lines)
    return "\n".join(abc) + "\n"


# -----------------------------------------------------------------------------
# CLI

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("hymn_json", help="path to HarpHymnal data/hymns/<slug>.json")
    ap.add_argument("-o", "--output", help="output ABC path (default stdout)")
    ap.add_argument("-x", "--xnum", type=int, default=1)
    ap.add_argument("--level", type=int, default=3, choices=range(1, 8),
                    help="retab level 1-7 (default 3, the canonical trefoil)")
    args = ap.parse_args()

    hymn = json.loads(Path(args.hymn_json).read_text(encoding="utf-8"))
    retabbed = RETAB_LEVELS[args.level](hymn)
    abc = build_abc(retabbed, x_num=args.xnum, level=args.level)
    if args.output:
        Path(args.output).write_text(abc, encoding="utf-8")
    else:
        print(abc)


if __name__ == "__main__":
    main()
