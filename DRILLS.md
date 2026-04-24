# Style Drills — Quick Reference

Abstract LH patterns for playing hymns on the 47-string lever harp. One row
per style.

**Shape** — hex tones the hand is preset on, low → high. `1`-`9` = scale
degrees 1-9; `a` = 10, `b` = 11, `c` = 12. (E.g., `135a` = root, 3rd, 5th,
10th.)

**Rhythm** — one Unicode glyph per temporal event, including rests:

    𝅝  whole      𝅗𝅥  half      ♩  quarter      ♪  eighth      𝅘𝅥𝅯  sixteenth
    𝄻  whole rest 𝄼  half rest 𝄽  quarter rest 𝄾  eighth rest 𝄿  sixteenth rest

Append `.` for a dotted value (`♩.` = dotted quarter, `𝄾.` = dotted eighth
rest).

**Fingering** — finger numbers 1-4 (thumb → pinky). Space-separated attack
groups; concatenated digits fire simultaneously (`23` = fingers 2 and 3
together). Fingerings can be non-sequential (`42 13`, `14 23`, etc.).
Aligns to the rhythm by skipping rest glyphs — first non-rest note ↔ first
fingering group, second non-rest ↔ second group, etc.

**Modes** — which of the 7 church modes the style fits, listed
preference-first. Mode digits match their starting scale degree:

    1 Ionian     2 Dorian     3 Phrygian     4 Lydian
    5 Mixolydian 6 Aeolian    7⚠ Locrian

To drill in mode `N`, rotate the path so it starts at scale degree `N`.

**Path** — the 8-chord trefoil loop, in unsigned (Ionian-labeled) roman
numerals.

─────────────────────────────────────────────────────────────────────────

| # | Style         | Modes | Shape  | Rhythm         | Fingering      | Path                               |
|---|---------------|-------|--------|----------------|----------------|------------------------------------|
| 1 | Chorale       | 1625  | `135`  | `𝅝`             | `123`          | `4cw` I IV vii° iii vi ii V I      |
| 2 | Rolled        | 1256  | `1358` | `♩ ♩ ♩ ♩`       | `1 2 3 4`      | `2cw` I ii iii IV V vi vii° I      |
| 3 | Gospel Walk   | 152   | `15`   | `♩ 𝄽 ♩ 𝄽`        | `1 2`          | `4ccw` I V ii vi iii vii° IV I     |
| 4 | Celtic Drone  | 2651  | `15`   | `𝅗𝅥.`            | `12`           | `2ccw` I vii° vi V IV iii ii I     |
| 5 | Praise Ballad | 1624  | `135`  | `♩ ♩ ♩ 𝄽`       | `1 2 3`        | `3cw` I iii V vii° ii IV vi I      |
| 6 | Spiritual     | 6251  | `1358` | `♩ ♩ ♩ ♩`       | `1 234 1 234`  | `3ccw` I vi IV ii vii° V iii I     |

All six trefoil paths drilled once each (2nds / 3rds / 4ths × CW / CCW).
