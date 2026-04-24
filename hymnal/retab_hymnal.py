#!/usr/bin/env python3
"""Retab Hymnal — apply trefoil LH patterns + RH melody to HarpHymnal hymns.

Reads HarpHymnal's per-bar JSON (data/hymns/<slug>.json) and emits a grand-staff
ABC file. V1 = melody (as given). V2 = diatonic block-135 trefoil pattern,
rhythm chosen by phrase_role (same guide used by reharm/tactics.json):

    opening          whole-note block 135       (settle the phrase)
    middle           half-note block 135, twice (walk)
    cadence_approach arpeggio 1-3-5 quarters    (lift into cadence)
    cadence          whole-note block 135 root  (resolve)

Compile with:  abcm2ps <out.abc> -O <name> -g    (per-tune SVG)
"""

from __future__ import annotations
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


def render_melody_bar(bar: dict, mult: int) -> str:
    """Emit melody bar; prepend chord annotation (if any) to the first event."""
    toks = []
    label = chord_label(bar.get("chord"))
    annotation = f'"^{label}"' if label else ""
    first = True
    for ev in bar["melody"]:
        n = int(round(ev["duration"] * mult))
        if ev["kind"] == "rest":
            tok = _safe_note_dur("z", n)
        else:
            tok = _safe_note_dur(pitch_to_abc(ev["pitch"]), n)
        if first and annotation and tok:
            tok = annotation + tok
            first = False
        elif tok:
            first = False
        toks.append(tok)
    return " ".join(t for t in toks if t)


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


def lh_pattern(degree: int, key_root: str, phrase_role: str,
               total_sixteenths: int, beats: int, unit: int) -> str:
    """Emit bass-clef trefoil pattern filling exactly `total_sixteenths`."""
    if total_sixteenths <= 0:
        return ""

    r = scale_degree_to_abc(degree, key_root, LH_TRIAD_OCTAVE)
    t = scale_degree_to_abc(degree + 2, key_root, LH_TRIAD_OCTAVE)
    f = scale_degree_to_abc(degree + 4, key_root, LH_TRIAD_OCTAVE)
    block = f"[{r}{t}{f}]"

    # Low-bass ditto on opening + cadence: the root struck once at beat 1
    # an octave below the triad. Single strike — never a rhythm — so
    # octave-1 strings (C1–B1) read as a structural pedal anchor.
    ditto_block = None
    if phrase_role in ("opening", "cadence"):
        ditto = scale_degree_to_abc(degree, key_root, LH_DITTO_OCTAVE)
        ditto_block = f"[{ditto}{r}{t}{f}]"

    beat_16 = beat_group_sixteenths(beats, unit)
    if beat_16 > 0 and total_sixteenths % beat_16 == 0:
        num_groups = total_sixteenths // beat_16
    else:
        num_groups = 0  # fallback: treat bar as one chunk

    # Cadence approach: 1-3-5 arpeggio filling the bar (needs ≥3 beat groups).
    if phrase_role == "cadence_approach" and num_groups >= 3:
        # r on beat 1, t on beat 2, f sustained for the rest.
        f_dur = (num_groups - 2) * beat_16
        return (
            _safe_chord(r, beat_16) + " " +
            _safe_chord(t, beat_16) + " " +
            _safe_chord(f, f_dur)
        )

    # Middle phrase: two equal half-bar blocks when bar splits cleanly in half.
    if phrase_role == "middle" and num_groups >= 2 and num_groups % 2 == 0:
        half = (num_groups // 2) * beat_16
        return _safe_chord(block, half) + " " + _safe_chord(block, half)

    # Default: one block per beat group. On opening/cadence, the first strike
    # carries the low-bass ditto; subsequent strikes are plain triads.
    if num_groups >= 1:
        first = _safe_chord(ditto_block or block, beat_16)
        rest = [_safe_chord(block, beat_16) for _ in range(num_groups - 1)]
        return " ".join([first] + rest)

    # Fallback: irregular bar (pickup, etc.) — emit as tied block.
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
# Build ABC output

def build_abc(hymn: dict, x_num: int = 1, num_prefix: str | None = None) -> str:
    title = hymn["title"]
    if num_prefix:
        title = f"{num_prefix}. {title}"
    key_root = hymn["key"]["root"]
    mode = hymn["key"]["mode"]
    meter_beats = hymn["meter"]["beats"]
    meter_unit = hymn["meter"]["unit"]
    bars = hymn["bars"]
    phrases = hymn["phrases"]

    # For minor hymns, translate to relative major for the staff key signature
    # and translate roman numerals Aeolian→Ionian-relative so triads come out
    # diatonic in the surface key.
    if mode == "minor":
        effective_key = relative_major(key_root, mode)
    else:
        effective_key = key_root

    roles = assign_phrase_roles(len(bars), phrases)
    mult = detect_duration_multiplier(hymn)

    # Melody V1: octave-sensitive, use as-is.
    melody_bars = [render_melody_bar(b, mult) for b in bars]

    # LH V2: trefoil pattern per bar, sized to the melody's actual bar length.
    lh_bars = []
    for i, bar in enumerate(bars):
        chord = bar["chord"] or {}
        num = chord.get("numeral") or "I"
        if mode == "minor":
            num = AEOLIAN_TO_IONIAN.get(num, num)
        degree = parse_roman(num)
        bar_16ths = bar_length_sixteenths(bar, mult)
        lh_bars.append(lh_pattern(degree, effective_key, roles[i], bar_16ths,
                                   meter_beats, meter_unit))

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
    args = ap.parse_args()

    hymn = json.loads(Path(args.hymn_json).read_text(encoding="utf-8"))
    abc = build_abc(hymn, x_num=args.xnum)
    if args.output:
        Path(args.output).write_text(abc, encoding="utf-8")
    else:
        print(abc)


if __name__ == "__main__":
    main()
