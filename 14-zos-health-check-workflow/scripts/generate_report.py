#!/usr/bin/env python3
"""
generate_report.py &mdash; z/OS Health Check HTML Report Generator
=============================================================
Parses the structured VERDICT: and TOP_CONSUMER: lines emitted by the
zos_health_check.xml workflow steps and renders a self-contained HTML
file with inline SVG gauges and a prioritised action list.

No third-party dependencies. Requires Python 3.7+.

Usage
-----
  # From a raw spool text file collected by collect_and_report.sh:
  python scripts/generate_report.py --input spool_output.txt

  # Writing to a specific output file:
  python scripts/generate_report.py --input spool_output.txt \
      --output zos_health_report_20250716.html

  # Dry-run: parse and print findings without generating HTML:
  python scripts/generate_report.py --input spool_output.txt --dry-run

Line format expected in the input
----------------------------------
  VERDICT:<axis>:<value>:<threshold>:<grade>
  TOP_CONSUMER:<axis>:<name>:<metric>

  <axis>      : SPOOL | CPU | MEMORY | DATASET_IO
  <value>     : numeric (spool %, paging rate, opens/hr, or 0 for CPU)
  <threshold> : numeric threshold used for the grade
  <grade>     : GREEN | AMBER | RED | UNKNOWN
"""

import argparse
import html
import math
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# IBM Carbon status tokens (light theme) &mdash; matches the z/OSMF UI.
# Status colors are reserved for state and always ship with a text label
# (never color alone). Carbon yellow fails 3:1 contrast on white, so every
# amber mark carries a darker outline (GRADE_STROKE) as relief.
GRADE_COLOR = {          # gauge/mark fill
    "GREEN":   "#24a148",
    "AMBER":   "#f1c21b",
    "RED":     "#da1e28",
    "UNKNOWN": "#8d8d8d",
}

GRADE_STROKE = {         # 1px relief outline on gauge fills
    "GREEN":   "#198038",
    "AMBER":   "#8e6a00",
    "RED":     "#a2191f",
    "UNKNOWN": "#6f6f6f",
}

GRADE_TAG_BG = {         # Carbon tag backgrounds
    "GREEN":   "#a7f0ba",
    "AMBER":   "#fcf4d6",
    "RED":     "#ffd7d9",
    "UNKNOWN": "#e0e0e0",
}

GRADE_TAG_TEXT = {       # Carbon tag ink (dark, WCAG-safe on the tag bg)
    "GREEN":   "#0e6027",
    "AMBER":   "#684e00",
    "RED":     "#a2191f",
    "UNKNOWN": "#393939",
}

# Carbon categorical hues for the spool consumer pie &mdash; validated with the
# dataviz palette checker (fixed order, never cycled). Gray is reserved for
# the "Other" fold-in slice (labeled, gap-separated), not an identity hue.
CAT_COLORS  = ["#6929c4", "#1192e8", "#198038", "#9f1853", "#b28600"]
OTHER_COLOR = "#8d8d8d"

AXIS_LABEL = {
    "SPOOL":      "Spool Utilisation",
    "CPU":        "CPU Shape (STCs)",
    "MEMORY":     "Memory / Paging",
    "DATASET_IO": "Dataset I/O Hotspots",
}

AXIS_UNIT = {
    "SPOOL":      "%",
    "CPU":        "% ratio",
    "MEMORY":     " page-ins/s",
    "DATASET_IO": " opens/hr",
}

ACTION_TEMPLATES = {
    "SPOOL": {
        "RED":   [
            "Purge held output (QUEUE=PRINT) for the largest owners immediately.",
            "Confirm top jobs are not needed for audit or problem determination.",
            "Offload dumps and large reports before purging their spool copy.",
            "If one job dominates, correct the application &mdash; purging alone won't hold.",
            "Engage JES operations if pressure persists after cleanup.",
        ],
        "AMBER": [
            "Monitor top consumers over the next 24 hours for growth trend.",
            "Identify held output that is no longer needed and schedule purge.",
            "Review whether any batch windows are generating duplicate output classes.",
        ],
    },
    "CPU": {
        "RED":   [
            "Review flagged STCs for idle wait &mdash; many hold MLC charges for near-zero work.",
            "Coordinate with application owners: consider reducing polling intervals.",
            "Evaluate whether flagged STCs can be stopped during off-peak windows.",
            "Quantify MLC exposure: CPU hours &times; software licence rate &times; days running.",
        ],
        "AMBER": [
            "Document flagged STCs and track CPU ratio over the next measurement window.",
            "Check whether flagged STCs are I/O-wait dominated &mdash; storage tuning may help.",
        ],
    },
    "MEMORY": {
        "RED":   [
            "Investigate address spaces driving the highest page-in counts (check RMF).",
            "Review LPAR real-storage allocation &mdash; consider rebalancing from idle LPARs.",
            "Identify workloads that can be moved to a less-constrained LPAR.",
            "Engage IBM or your hardware vendor for a storage sizing review.",
        ],
        "AMBER": [
            "Trend paging rate across the week &mdash; confirm this is not a growing pattern.",
            "Review working set sizes for the largest batch jobs in the window.",
        ],
    },
    "DATASET_IO": {
        "RED":   [
            "Assign the hottest dataset(s) to an EAV or flash-cache storage tier.",
            "Investigate whether multiple applications are reading the same dataset "
            "redundantly &mdash; a shared in-memory cache or copy may eliminate I/O.",
            "Review dataset RECFM/BLKSIZE: suboptimal blocking multiplies EXCP count.",
            "Raise with storage administration for a formal caching ROI calculation.",
        ],
        "AMBER": [
            "Flag top datasets for the next storage tiering review.",
            "Confirm the high-open datasets benefit from cache &mdash; some sequential "
            "workloads perform better without caching (pre-fetch bypassed).",
        ],
    },
}

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_spool(text: str) -> tuple[dict, dict]:
    """
    Returns:
        verdicts     : { axis: {"value": float, "threshold": float, "grade": str} }
        top_consumers: { axis: [ {"name": str, "metric": str}, ... ] }
    """
    verdicts: dict = {}
    top_consumers: dict = {}

    verdict_re = re.compile(
        r"^VERDICT:([A-Z_]+):([0-9.]+):([0-9.]+):(GREEN|AMBER|RED|UNKNOWN)",
        re.MULTILINE,
    )
    consumer_re = re.compile(
        r"^TOP_CONSUMER:([A-Z_]+):([^:]+):(.+)$",
        re.MULTILINE,
    )

    for m in verdict_re.finditer(text):
        axis, value, threshold, grade = m.groups()
        verdicts[axis] = {
            "value":     float(value),
            "threshold": float(threshold),
            "grade":     grade,
        }

    for m in consumer_re.finditer(text):
        axis, name, metric = m.groups()
        top_consumers.setdefault(axis, []).append(
            {"name": name.strip(), "metric": metric.strip()}
        )

    return verdicts, top_consumers


# ---------------------------------------------------------------------------
# SVG gauge helpers
# ---------------------------------------------------------------------------

def _bar_gauge(value: float, threshold: float, grade: str,
               width: int = 400, height: int = 28) -> str:
    """
    Horizontal bar gauge.  value and threshold are both on a 0-max scale
    where max = max(value, threshold) * 1.25 so the threshold marker is
    always visible.
    """
    max_val = max(value, threshold, 1) * 1.25
    fill_w  = int(min(value / max_val, 1.0) * width)
    thr_x   = int(min(threshold / max_val, 1.0) * width)
    color   = GRADE_COLOR.get(grade, GRADE_COLOR["UNKNOWN"])
    stroke  = GRADE_STROKE.get(grade, GRADE_STROKE["UNKNOWN"])

    return f"""<svg width="{width}" height="{height}" style="display:block" role="img">
  <title>value {value:g}, threshold {threshold:g}, grade {grade}</title>
  <rect x="0" y="6" width="{width}" height="16" rx="2" fill="#e0e0e0"/>
  <rect x="0.5" y="6.5" width="{max(fill_w - 1, 1)}" height="15" rx="2"
        fill="{color}" stroke="{stroke}" stroke-width="1"/>
  <line x1="{thr_x}" y1="2" x2="{thr_x}" y2="{height-2}"
        stroke="#161616" stroke-width="1.5" stroke-dasharray="3,2"/>
</svg>"""


def _donut_gauge(value: float, threshold: float, grade: str,
                 size: int = 132) -> str:
    """Donut gauge for a 0-100% axis: value arc in the grade color, a tick
    on the ring at the threshold angle, numeric value in the hole."""
    color = GRADE_COLOR.get(grade, GRADE_COLOR["UNKNOWN"])
    c    = size / 2
    r    = c - 16
    circ = 2 * math.pi * r
    pct  = max(0.0, min(value, 100.0))
    arc  = circ * pct / 100
    ang  = math.radians(min(threshold, 100.0) / 100 * 360 - 90)
    tx1  = c + (r - 9) * math.cos(ang)
    ty1  = c + (r - 9) * math.sin(ang)
    tx2  = c + (r + 9) * math.cos(ang)
    ty2  = c + (r + 9) * math.sin(ang)
    return f"""<svg width="{size}" height="{size}" role="img">
  <title>value {value:g}%, threshold {threshold:g}%, grade {grade}</title>
  <circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="#e0e0e0" stroke-width="14"/>
  <circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{color}" stroke-width="14"
          stroke-dasharray="{arc:.1f} {circ:.1f}" transform="rotate(-90 {c} {c})"/>
  <line x1="{tx1:.1f}" y1="{ty1:.1f}" x2="{tx2:.1f}" y2="{ty2:.1f}"
        stroke="#161616" stroke-width="2"/>
  <text x="{c}" y="{c + 7}" text-anchor="middle"
        font-size="20" font-weight="600" fill="#161616"
        font-family="IBM Plex Sans, Helvetica Neue, Arial, sans-serif">{value:g}%</text>
</svg>"""


def _slice_pcts(consumers: list) -> list:
    """[(name, pct), ...] extracted from spool TOP_CONSUMER metrics
    (metric text looks like 'OWNER:12.5%')."""
    out = []
    for c in consumers[:5]:
        m = re.search(r"([0-9.]+)\s*%", c["metric"])
        if m:
            out.append((c["name"], float(m.group(1))))
    return out


def _consumer_pie(slices: list, size: int = 132) -> str:
    """Pie of top spool-consumer shares plus a gray 'Other' remainder.
    2px white gaps between wedges; identity is carried by the legend
    chips in the consumer list, never by color alone."""
    total = sum(p for _, p in slices)
    if not slices or total <= 0:
        return ""
    work = list(slices)
    if total < 99.9:
        work.append(("Other", 100.0 - total))
    c = size / 2
    r = c - 4
    paths, a0 = "", -90.0
    for i, (name, pct) in enumerate(work):
        col = OTHER_COLOR if name == "Other" else CAT_COLORS[i % len(CAT_COLORS)]
        tip = f"<title>{html.escape(name)} {pct:g}%</title>"
        if pct >= 99.95:
            paths += f'<circle cx="{c}" cy="{c}" r="{r}" fill="{col}">{tip}</circle>'
            break
        a1 = a0 + pct / 100 * 360
        large = 1 if (a1 - a0) > 180 else 0
        x0 = c + r * math.cos(math.radians(a0))
        y0 = c + r * math.sin(math.radians(a0))
        x1 = c + r * math.cos(math.radians(a1))
        y1 = c + r * math.sin(math.radians(a1))
        paths += (f'<path d="M{c},{c} L{x0:.1f},{y0:.1f} '
                  f'A{r},{r} 0 {large} 1 {x1:.1f},{y1:.1f} Z" '
                  f'fill="{col}" stroke="#ffffff" stroke-width="2">{tip}</path>')
        a0 = a1
    return f'<svg width="{size}" height="{size}" role="img">{paths}</svg>'


def _grade_badge(grade: str) -> str:
    # Carbon "tag" component: pill, tinted background, dark ink.
    bg  = GRADE_TAG_BG.get(grade, GRADE_TAG_BG["UNKNOWN"])
    ink = GRADE_TAG_TEXT.get(grade, GRADE_TAG_TEXT["UNKNOWN"])
    return (
        f'<span style="display:inline-block;padding:2px 12px;border-radius:12px;'
        f'font-size:12px;font-weight:600;letter-spacing:.02em;'
        f'background:{bg};color:{ink}">'
        f'{html.escape(grade)}</span>'
    )


def _overall_badge(verdicts: dict) -> str:
    grades = [v["grade"] for v in verdicts.values()]
    if "RED"     in grades: overall = "RED"
    elif "AMBER" in grades: overall = "AMBER"
    elif "GREEN" in grades: overall = "GREEN"
    else:                   overall = "UNKNOWN"
    bg  = GRADE_TAG_BG[overall]
    ink = GRADE_TAG_TEXT[overall]
    return (
        f'<span style="font-size:22px;font-weight:600;color:{ink};'
        f'background:{bg};padding:6px 24px;'
        f'border-radius:20px;letter-spacing:.02em">{overall}</span>',
        overall,
    )


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

# IBM Carbon light theme, laid out like the z/OSMF web UI: black product
# header bar, IBM Plex Sans, gray-10 page on white tiles, blue-60 accents.
STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif;
  background: #f4f4f4;
  color: #161616;
  font-size: 14px;
  line-height: 1.6;
}
.topbar {
  background: #161616;
  color: #ffffff;
  height: 48px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px;
  font-size: 14px;
}
.topbar .prod { letter-spacing: .01em; }
.topbar .prod b { font-weight: 600; margin-right: 6px; }
.topbar .ctx { color: #c6c6c6; font-size: 12px; }
.page { max-width: 760px; margin: 0 auto; padding: 0 16px 48px; }
.hero {
  background: #ffffff;
  border: 1px solid #e0e0e0;
  padding: 32px;
  margin: 24px 0 32px;
}
.eyebrow {
  font-size: 12px;
  letter-spacing: .02em;
  color: #0f62fe;
  margin-bottom: 12px;
}
.title {
  font-size: 28px;
  font-weight: 400;
  color: #161616;
  margin-bottom: 8px;
  line-height: 1.25;
}
.subtitle { color: #525252; margin-bottom: 24px; font-size: 13px; }
.meta-row { display: flex; gap: 32px; flex-wrap: wrap; }
.meta-item { border-left: 3px solid #0f62fe; padding-left: 12px; }
.meta-num { font-size: 24px; font-weight: 400; color: #161616; line-height: 1.2; }
.meta-label { font-size: 12px; color: #525252; }
.section { margin-bottom: 40px; }
.section-hdr {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 16px;
}
.section-tag {
  font-size: 11px; letter-spacing: .02em;
  color: #393939; background: #e0e0e0;
  padding: 2px 10px; border-radius: 12px;
}
.section-title { font-size: 16px; font-weight: 600; color: #161616; }
.axis-card {
  background: #ffffff; border: 1px solid #e0e0e0;
  padding: 16px 20px; margin-bottom: 12px;
}
.axis-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.axis-name { font-size: 15px; font-weight: 600; color: #161616; margin-bottom: 2px; }
.axis-reading { font-size: 12px; color: #525252; }
.axis-gauge { margin: 10px 0 4px; }
.consumers { margin-top: 12px; }
.consumer-row {
  display: flex; justify-content: space-between;
  font-size: 12px; color: #525252;
  border-top: 1px solid #e0e0e0; padding: 6px 0;
}
.consumer-name { color: #0f62fe; font-family: "IBM Plex Mono", monospace; }
.consumer-metric { color: #161616; }
.actions { list-style: none; }
.actions li {
  padding: 8px 0 8px 18px;
  border-bottom: 1px solid #e0e0e0;
  position: relative;
  font-size: 13px;
  color: #161616;
}
.actions li:last-child { border-bottom: none; }
.actions li::before {
  content: '>';
  position: absolute; left: 2px;
  color: #0f62fe; font-weight: 600;
}
.actions li.red-action::before { color: #da1e28; }
.actions li.amber-action::before { color: #8e6a00; }
.no-findings { color: #525252; font-size: 13px; font-style: italic; }
.footer {
  margin-top: 48px; padding-top: 16px;
  border-top: 1px solid #e0e0e0;
  text-align: center; font-size: 12px; color: #6f6f6f;
}
"""


def render_html(verdicts: dict, top_consumers: dict,
                run_date: str, source_file: str) -> str:

    badge_html, overall = _overall_badge(verdicts)

    # ---- overall summary pill row ----
    axes_html = ""
    for axis in ["SPOOL", "CPU", "MEMORY", "DATASET_IO"]:
        v = verdicts.get(axis)
        if v is None:
            continue
        grade     = v["grade"]
        value     = v["value"]
        threshold = v["threshold"]
        unit      = AXIS_UNIT.get(axis, "")
        label     = AXIS_LABEL.get(axis, axis)
        consumers = top_consumers.get(axis, [])

        chips: dict = {}
        if axis == "SPOOL":
            slices = _slice_pcts(consumers)
            donut  = _donut_gauge(value, threshold, grade)
            pie    = _consumer_pie(slices)
            cap    = ('<div style="font-size:11px;color:#525252">'
                      'spool used vs threshold &middot; consumer share</div>')
            gauge  = (f'<div style="display:flex;gap:40px;align-items:center;'
                      f'flex-wrap:wrap">{donut}{pie}</div>{cap}')
            for i, (nm, _) in enumerate(slices):
                chips[nm] = CAT_COLORS[i % len(CAT_COLORS)]
        else:
            gauge = _bar_gauge(value, threshold, grade)
        badge = _grade_badge(grade)
        color = GRADE_STROKE.get(grade, GRADE_STROKE["UNKNOWN"])

        reading = f"{value:g}{unit}  &middot;  threshold {threshold:g}{unit}"
        if axis == "CPU":
            reading = f"Worst STC ratio graded &middot; threshold {threshold:g}{unit}"

        consumer_rows = ""
        for c in consumers[:5]:
            chip = ""
            col = chips.get(c["name"])
            if col:
                chip = (f'<span style="display:inline-block;width:10px;'
                        f'height:10px;border-radius:2px;background:{col};'
                        f'margin-right:8px"></span>')
            consumer_rows += (
                f'<div class="consumer-row">'
                f'<span class="consumer-name">{chip}{html.escape(c["name"])}</span>'
                f'<span class="consumer-metric">{html.escape(c["metric"])}</span>'
                f'</div>'
            )

        consumers_block = (
            f'<div class="consumers">{consumer_rows}</div>'
            if consumer_rows else ""
        )

        axes_html += f"""
<div class="axis-card" style="border-left:3px solid {color}">
  <div class="axis-top">
    <div>
      <div class="axis-name">{html.escape(label)}</div>
      <div class="axis-reading">{html.escape(reading)}</div>
    </div>
    <div>{badge}</div>
  </div>
  <div class="axis-gauge">{gauge}</div>
  {consumers_block}
</div>"""

    # ---- action list ----
    actions_html = ""
    for axis in ["CPU", "SPOOL", "DATASET_IO", "MEMORY"]:
        v = verdicts.get(axis)
        if v is None or v["grade"] not in ("RED", "AMBER"):
            continue
        grade   = v["grade"]
        label   = AXIS_LABEL.get(axis, axis)
        actions = ACTION_TEMPLATES.get(axis, {}).get(grade, [])
        if not actions:
            continue
        css_class = "red-action" if grade == "RED" else "amber-action"
        color     = GRADE_TAG_TEXT[grade]
        items     = "".join(
            f'<li class="{css_class}">{html.escape(a)}</li>' for a in actions
        )
        actions_html += f"""
<div style="margin-bottom:20px">
  <div style="font-size:12px;font-weight:700;color:{color};
              margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em">
    {html.escape(label)} &mdash; {grade}
  </div>
  <ul class="actions">{items}</ul>
</div>"""

    if not actions_html:
        actions_html = '<p class="no-findings">All axes GREEN &mdash; no actions required.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>z/OS Health Check &mdash; {html.escape(run_date)}</title>
<style>{STYLE}</style>
</head>
<body>
<div class="topbar">
  <span class="prod"><b>IBM</b>z/OS Management Facility</span>
  <span class="ctx">Health Check Report</span>
</div>
<div class="page">

  <div class="hero">
    <div class="eyebrow">z/OS Health Check &middot; {html.escape(run_date)}</div>
    <div class="title">System Health<br>Scorecard</div>
    <div class="subtitle">Source: {html.escape(source_file)}</div>
    <div class="meta-row">
      <div class="meta-item">
        <div class="meta-num">{len(verdicts)}</div>
        <div class="meta-label">axes measured</div>
      </div>
      <div class="meta-item">
        <div class="meta-num">{sum(1 for v in verdicts.values() if v["grade"]=="RED")}</div>
        <div class="meta-label">red findings</div>
      </div>
      <div class="meta-item">
        <div class="meta-num">{sum(1 for v in verdicts.values() if v["grade"]=="AMBER")}</div>
        <div class="meta-label">amber findings</div>
      </div>
      <div class="meta-item">
        <div style="margin-bottom:6px">{badge_html}</div>
        <div class="meta-label">overall grade</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-hdr">
      <span class="section-tag">Scorecard</span>
      <span class="section-title">Health Axes</span>
    </div>
    {axes_html}
  </div>

  <div class="section">
    <div class="section-hdr">
      <span class="section-tag">Actions</span>
      <span class="section-title">Prioritised Remediation</span>
    </div>
    {actions_html}
  </div>

  <div class="footer">
    Generated {html.escape(run_date)} &middot; z/OS Health Check Workflow &middot; Made with IBM Bob
  </div>

</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse z/OS Health Check spool output and generate an HTML report."
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the collected spool text file (output of collect_and_report.sh)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output HTML file path. Defaults to zos_health_report_YYYYMMDD.html",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print findings to stdout without writing the HTML file",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    text = input_path.read_text(encoding="utf-8", errors="replace")
    verdicts, top_consumers = parse_spool(text)

    if not verdicts:
        print(
            "WARNING: No VERDICT: lines found in the input.\n"
            "Ensure all workflow steps completed successfully and that\n"
            "collect_and_report.sh captured output from every step.",
            file=sys.stderr,
        )
        return 2

    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    if args.dry_run:
        print(f"Parsed {len(verdicts)} verdict(s) from {input_path}")
        for axis, v in verdicts.items():
            label = AXIS_LABEL.get(axis, axis)
            print(f"  {v['grade']:7s}  {label}")
        consumers_found = sum(len(c) for c in top_consumers.values())
        print(f"Parsed {consumers_found} top-consumer entries")
        return 0

    output_path = Path(
        args.output or f"zos_health_report_{datetime.now().strftime('%Y%m%d')}.html"
    )
    html_out = render_html(verdicts, top_consumers, run_date, str(input_path))
    output_path.write_text(html_out, encoding="utf-8")
    print(f"Report written to: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
