#!/usr/bin/env python3
"""Bulk-build Retab Hymnal at multiple levels side-by-side.

Mirrors ../../reharm/hymnal/build_hymnal.py so the tablet app can flip
through L1 / L2 / L3 / L4 / L5 / L6 / L7 for the same hymn.

Writes:

  - /tmp/retab_hymnal_L<level>/<slug>.abc    (intermediate ABC)
  - /tmp/retab_hymnal_L<level>/<slug>.svg    (compiled by abcm2ps -g)
  - tablet_app/assets/retab/hymns/L<level>/<slug>.svg   (viewBox-patched)
  - tablet_app/assets/retab/retab_hymns.js              (window.RETAB_HYMNS)

Run:

    python build_hymnal.py                  # builds L1..L7 (default)
    python build_hymnal.py --levels 3,6,7   # custom subset

Catalog entries have shape:
    {slug, num, title, key, meter, bars, svgs: {"1": ..., "2": ..., ...}, pages}

so the tablet UI picks svgs[currentLevel] at render time.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from retab_hymnal import RETAB_LEVELS, build_abc  # noqa

HYMNS_DIR = Path("/home/james.clements/projects/HarpHymnal/data/hymns")
DEST_ROOT = Path("/home/james.clements/projects/HarpHymnal/tablet_app/"
                 "app/src/main/assets/retab/hymns")
INDEX_JS = Path("/home/james.clements/projects/HarpHymnal/tablet_app/"
                "app/src/main/assets/retab/retab_hymns.js")


def add_viewbox(svg_text: str) -> str:
    m = re.search(r'<svg[^>]*width="([\d.]+)px"\s+height="([\d.]+)px"', svg_text)
    if not m:
        return svg_text
    if 'viewBox=' in svg_text:
        return svg_text
    w, h = m.group(1), m.group(2)
    return svg_text.replace(
        m.group(0),
        m.group(0) + f' viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet"',
        1,
    )


def build_one_level(jpath: Path, level: int, stage: Path, dest: Path,
                    num_prefix: str) -> tuple[bool, int]:
    slug = jpath.stem
    hymn = json.loads(jpath.read_text(encoding="utf-8"))

    leveled = RETAB_LEVELS[level](hymn)
    abc = build_abc(leveled, x_num=1, num_prefix=num_prefix, level=level)

    abc_path = stage / f"{slug}.abc"
    abc_path.write_text(abc, encoding="utf-8")

    out_prefix = stage / slug
    subprocess.run(
        ["abcm2ps", str(abc_path), "-g", "-O", str(out_prefix)],
        check=True, capture_output=True, timeout=30,
    )
    svgs = sorted(stage.glob(f"{slug}[0-9][0-9][0-9].svg"))
    if not svgs:
        return False, 0

    svg_text = svgs[0].read_text(encoding="utf-8")
    svg_text = add_viewbox(svg_text)
    (dest / f"{slug}.svg").write_text(svg_text, encoding="utf-8")
    return True, len(svgs)


def build_one_all_levels(jpath: Path, levels: list[int], num_prefix: str,
                         stages: dict[int, Path], dests: dict[int, Path]
                         ) -> dict | None:
    slug = jpath.stem
    try:
        hymn = json.loads(jpath.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  SKIP {slug}: JSON load: {e}")
        return None
    if not hymn.get("bars") or not hymn.get("key"):
        print(f"  SKIP {slug}: no bars/key")
        return None

    svgs_map = {}
    pages = 0
    for lvl in levels:
        try:
            ok, n_pages = build_one_level(jpath, lvl, stages[lvl],
                                          dests[lvl], num_prefix)
        except subprocess.CalledProcessError as e:
            print(f"  FAIL {slug} L{lvl}: abcm2ps: "
                  f"{e.stderr.decode()[:160]}")
            return None
        except subprocess.TimeoutExpired:
            print(f"  FAIL {slug} L{lvl}: abcm2ps timeout")
            return None
        except Exception as e:
            print(f"  FAIL {slug} L{lvl}: {e}")
            return None
        if not ok:
            print(f"  FAIL {slug} L{lvl}: no SVG produced")
            return None
        svgs_map[str(lvl)] = f"retab/hymns/L{lvl}/{slug}.svg"
        pages = max(pages, n_pages)

    return {
        "slug": slug,
        "num": num_prefix,
        "title": hymn["title"],
        "key": f"{hymn['key']['root']} {hymn['key']['mode']}",
        "meter": f"{hymn['meter']['beats']}/{hymn['meter']['unit']}",
        "bars": len(hymn["bars"]),
        "svgs": svgs_map,
        "pages": pages,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=str, default="1,2,3,4,5,6,7",
                    help="Comma-separated levels (default: 1,2,3,4,5,6,7).")
    ap.add_argument("--hymn-dir", type=Path, default=HYMNS_DIR)
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    for lvl in levels:
        if lvl not in RETAB_LEVELS:
            sys.exit(f"unknown level: {lvl}")

    stages = {lvl: Path(f"/tmp/retab_hymnal_L{lvl}") for lvl in levels}
    dests = {lvl: DEST_ROOT / f"L{lvl}" for lvl in levels}
    for p in list(stages.values()) + list(dests.values()):
        p.mkdir(parents=True, exist_ok=True)

    jsons = sorted(args.hymn_dir.glob("*.json"))
    pre = []
    for jp in jsons:
        try:
            h = json.loads(jp.read_text(encoding="utf-8"))
            pre.append((h.get("title", jp.stem), jp))
        except Exception:
            pre.append((jp.stem, jp))
    pre.sort(key=lambda t: t[0].lower())
    numbered = [(f"{i:03d}", jp) for i, (_, jp) in enumerate(pre, 1)]

    print(f"Processing {len(numbered)} hymns at levels {levels}...")
    results = []
    fails = []
    for i, (num, jp) in enumerate(numbered, 1):
        rec = build_one_all_levels(jp, levels, num, stages, dests)
        if rec is None:
            fails.append(jp.stem)
            continue
        results.append(rec)
        if i % 25 == 0:
            print(f"  {i}/{len(numbered)}  OK={len(results)} FAIL={len(fails)}")

    print(f"Done. OK={len(results)} FAIL={len(fails)}")
    if fails:
        print(f"Failures: {fails[:10]}{'...' if len(fails) > 10 else ''}")

    results.sort(key=lambda r: r["num"])
    js = ("window.RETAB_HYMNS = "
          + json.dumps(results, indent=2, ensure_ascii=False) + ";\n")
    INDEX_JS.write_text(js, encoding="utf-8")
    print(f"Wrote index: {INDEX_JS} ({len(results)} entries, "
          f"levels={levels})")


if __name__ == "__main__":
    main()
