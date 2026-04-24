#!/usr/bin/env python3
"""Bulk-build Retab Hymnal: every data/hymns/*.json → SVG via retab_hymnal.py.

Writes:
  - /tmp/retab_hymnal/<slug>.abc    (intermediate ABC)
  - /tmp/retab_hymnal/<slug>.svg    (compiled by abcm2ps -g)
  - tablet_app/assets/retab/hymns/<slug>.svg   (post-processed viewBox)
  - tablet_app/assets/retab/retab_hymns.js     (window.RETAB_HYMNS index)
"""

from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from retab_hymnal import build_abc  # noqa

HYMNS_DIR = Path("/home/james.clements/projects/HarpHymnal/data/hymns")
STAGE = Path("/tmp/retab_hymnal")
DEST = Path("/home/james.clements/projects/HarpHymnal/tablet_app/app/src/main/assets/retab/hymns")
INDEX_JS = Path("/home/james.clements/projects/HarpHymnal/tablet_app/app/src/main/assets/retab/retab_hymns.js")

STAGE.mkdir(parents=True, exist_ok=True)
DEST.mkdir(parents=True, exist_ok=True)


def add_viewbox(svg_text: str) -> str:
    """abcm2ps emits <svg width=Wpx height=Hpx>; add viewBox for responsive."""
    m = re.search(r'<svg[^>]*width="([\d.]+)px"\s+height="([\d.]+)px"', svg_text)
    if not m:
        return svg_text
    w, h = m.group(1), m.group(2)
    if 'viewBox=' in svg_text:
        return svg_text
    return svg_text.replace(
        m.group(0),
        m.group(0) + f' viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet"',
        1,
    )


def build_one(jpath: Path, num_prefix: str | None = None) -> dict | None:
    slug = jpath.stem
    try:
        hymn = json.loads(jpath.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  SKIP {slug}: JSON load: {e}")
        return None

    # Skip hymns with no bars or missing key.
    if not hymn.get("bars") or not hymn.get("key"):
        print(f"  SKIP {slug}: no bars/key")
        return None

    try:
        abc = build_abc(hymn, x_num=1, num_prefix=num_prefix)
    except Exception as e:
        print(f"  FAIL {slug}: build_abc: {e}")
        return None

    abc_path = STAGE / f"{slug}.abc"
    abc_path.write_text(abc, encoding="utf-8")

    # Compile with abcm2ps -g (SVG, one-tune-per-file via -O).
    out_prefix = STAGE / slug
    try:
        subprocess.run(
            ["abcm2ps", str(abc_path), "-g", "-O", str(out_prefix)],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        print(f"  FAIL {slug}: abcm2ps: {e.stderr.decode()[:200]}")
        return None
    except subprocess.TimeoutExpired:
        print(f"  FAIL {slug}: abcm2ps timeout")
        return None

    # abcm2ps outputs <prefix>001.svg, <prefix>002.svg, etc.
    svgs = sorted(STAGE.glob(f"{slug}[0-9][0-9][0-9].svg"))
    if not svgs:
        print(f"  FAIL {slug}: no SVG produced")
        return None

    # If multi-page, concatenate visually? For now, take the first page only.
    # (v1: hymns fit one page; flag the rest.)
    svg_in = svgs[0]
    svg_text = svg_in.read_text(encoding="utf-8")
    svg_text = add_viewbox(svg_text)
    dest_path = DEST / f"{slug}.svg"
    dest_path.write_text(svg_text, encoding="utf-8")

    return {
        "slug": slug,
        "num": num_prefix,
        "title": hymn["title"],
        "key": f"{hymn['key']['root']} {hymn['key']['mode']}",
        "meter": f"{hymn['meter']['beats']}/{hymn['meter']['unit']}",
        "bars": len(hymn["bars"]),
        "svg": f"retab/hymns/{slug}.svg",
        "pages": len(svgs),
    }


def main():
    # Pre-pass: load titles for every hymn, sort alphabetically, assign numbers.
    jsons = sorted(HYMNS_DIR.glob("*.json"))
    pre = []
    for jp in jsons:
        try:
            h = json.loads(jp.read_text(encoding="utf-8"))
            pre.append((h.get("title", jp.stem), jp))
        except Exception:
            pre.append((jp.stem, jp))
    pre.sort(key=lambda t: t[0].lower())
    numbered = [(f"{i:03d}", jp) for i, (_, jp) in enumerate(pre, 1)]

    results = []
    fails = []
    print(f"Processing {len(numbered)} hymns…")
    for i, (num, jp) in enumerate(numbered, 1):
        rec = build_one(jp, num_prefix=num)
        if rec is None:
            fails.append(jp.stem)
            continue
        results.append(rec)
        if i % 25 == 0:
            print(f"  {i}/{len(numbered)}  OK={len(results)} FAIL={len(fails)}")

    print(f"Done. OK={len(results)} FAIL={len(fails)}")
    if fails:
        print(f"Failures: {fails[:10]}{'…' if len(fails) > 10 else ''}")

    results.sort(key=lambda r: r["num"])
    js = "window.RETAB_HYMNS = " + json.dumps(results, indent=2, ensure_ascii=False) + ";\n"
    INDEX_JS.write_text(js, encoding="utf-8")
    print(f"Wrote index: {INDEX_JS} ({len(results)} entries)")


if __name__ == "__main__":
    main()
