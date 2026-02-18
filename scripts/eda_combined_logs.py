#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/Users/sauravmohanty/ai-travel-agent')
INPUT = ROOT / 'runtime/logs/combined_test-failures.jsonl'
OUTDIR = ROOT / 'runtime/logs/eda'
OUTDIR.mkdir(parents=True, exist_ok=True)


def load_records(path: Path):
    records = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


def esc(s: str) -> str:
    return (
        str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&apos;')
    )


def write_svg(path: Path, body: str, w: int = 1200, h: int = 700):
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect x="0" y="0" width="{w}" height="{h}" fill="#f8fafc"/>
  {body}
</svg>\n'''
    path.write_text(svg, encoding='utf-8')


def bar_chart(title: str, data: list[tuple[str, int]], out: Path, color: str = '#2563eb'):
    w, h = 1200, 700
    l, r, t, b = 90, 40, 90, 130
    pw, ph = w - l - r, h - t - b
    maxv = max((v for _, v in data), default=1)
    n = max(len(data), 1)
    gap = 10
    bw = max(20, int((pw - gap * (n - 1)) / n))

    parts = [
        f'<text x="{w/2}" y="45" text-anchor="middle" font-size="30" font-family="Arial" fill="#0f172a">{esc(title)}</text>',
        f'<line x1="{l}" y1="{t+ph}" x2="{l+pw}" y2="{t+ph}" stroke="#334155" stroke-width="2"/>',
        f'<line x1="{l}" y1="{t}" x2="{l}" y2="{t+ph}" stroke="#334155" stroke-width="2"/>'
    ]

    for i, (k, v) in enumerate(data):
        x = l + i * (bw + gap)
        bh = 0 if maxv == 0 else int((v / maxv) * (ph - 20))
        y = t + ph - bh
        parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" fill="{color}" rx="4"/>')
        parts.append(f'<text x="{x + bw/2}" y="{y - 8}" text-anchor="middle" font-size="14" font-family="Arial" fill="#0f172a">{v}</text>')
        label = (k[:16] + '...') if len(k) > 19 else k
        parts.append(f'<text x="{x + bw/2}" y="{t+ph+22}" text-anchor="middle" font-size="12" font-family="Arial" fill="#1e293b" transform="rotate(25 {x + bw/2} {t+ph+22})">{esc(label)}</text>')

    # y ticks
    for tick in range(0, 6):
        tv = int(maxv * tick / 5)
        ty = t + ph - int((tick / 5) * ph)
        parts.append(f'<line x1="{l-5}" y1="{ty}" x2="{l}" y2="{ty}" stroke="#334155"/>')
        parts.append(f'<text x="{l-10}" y="{ty+5}" text-anchor="end" font-size="12" font-family="Arial" fill="#334155">{tv}</text>')

    write_svg(out, '\n  '.join(parts), w, h)


def line_chart(title: str, labels: list[str], values: list[int], out: Path):
    w, h = 1400, 700
    l, r, t, b = 90, 40, 90, 130
    pw, ph = w - l - r, h - t - b
    maxv = max(values) if values else 1
    n = len(values)
    step = pw / max(n - 1, 1)

    pts = []
    for i, v in enumerate(values):
        x = l + i * step
        y = t + ph - (0 if maxv == 0 else (v / maxv) * ph)
        pts.append((x, y, v, labels[i]))

    parts = [
        f'<text x="{w/2}" y="45" text-anchor="middle" font-size="30" font-family="Arial" fill="#0f172a">{esc(title)}</text>',
        f'<line x1="{l}" y1="{t+ph}" x2="{l+pw}" y2="{t+ph}" stroke="#334155" stroke-width="2"/>',
        f'<line x1="{l}" y1="{t}" x2="{l}" y2="{t+ph}" stroke="#334155" stroke-width="2"/>'
    ]

    if pts:
        poly = ' '.join(f'{x},{y}' for x, y, _, _ in pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="#0ea5e9" stroke-width="3"/>')
        for x, y, v, lbl in pts:
            parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#0284c7"/>')
            if n <= 40 or (int((x-l)/step) % max(n//20,1) == 0):
                parts.append(f'<text x="{x}" y="{t+ph+18}" text-anchor="middle" font-size="10" font-family="Arial" fill="#334155" transform="rotate(30 {x} {t+ph+18})">{esc(lbl[-5:])}</text>')

    # y ticks
    for tick in range(0, 6):
        tv = int(maxv * tick / 5)
        ty = t + ph - int((tick / 5) * ph)
        parts.append(f'<line x1="{l-5}" y1="{ty}" x2="{l}" y2="{ty}" stroke="#334155"/>')
        parts.append(f'<text x="{l-10}" y="{ty+5}" text-anchor="end" font-size="12" font-family="Arial" fill="#334155">{tv}</text>')

    write_svg(out, '\n  '.join(parts), w, h)


def summary_html(stats: dict, out: Path):
    rows = ''.join(f'<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>' for k, v in stats.items())
    html = f'''<!doctype html>
<html><head><meta charset="utf-8"><title>Combined Log EDA</title>
<style>body{{font-family:Arial,sans-serif;padding:24px;background:#f8fafc;color:#0f172a}}table{{border-collapse:collapse}}td,th{{border:1px solid #cbd5e1;padding:8px 12px}}img{{max-width:100%;height:auto;border:1px solid #cbd5e1;margin:12px 0}}</style></head>
<body>
<h1>Combined Log EDA</h1>
<table><tbody>{rows}</tbody></table>
<h2>Charts</h2>
<ul>
<li><a href="kind_distribution.svg">kind_distribution.svg</a></li>
<li><a href="top_events.svg">top_events.svg</a></li>
<li><a href="failure_categories.svg">failure_categories.svg</a></li>
<li><a href="failure_error_types.svg">failure_error_types.svg</a></li>
<li><a href="node_activity.svg">node_activity.svg</a></li>
<li><a href="records_timeline.svg">records_timeline.svg</a></li>
<li><a href="failures_timeline.svg">failures_timeline.svg</a></li>
</ul>
</body></html>
'''
    out.write_text(html, encoding='utf-8')


def main():
    recs = load_records(INPUT)
    if not recs:
        raise SystemExit('No records found')

    kind = Counter(str(r.get('kind', 'unknown')) for r in recs)
    events = Counter(str(r.get('event', '')) for r in recs)
    nodes = Counter(str(r.get('graph_node', '<none>')) for r in recs)

    failures = [r for r in recs if r.get('kind') == 'failure']
    fcat = Counter(str((r.get('data') or {}).get('category', 'unknown')) for r in failures)
    ferr = Counter(str((r.get('data') or {}).get('error_type', 'unknown')) for r in failures)

    dt_all = []
    for r in recs:
        ts = r.get('timestamp')
        if not ts:
            continue
        try:
            dt_all.append(datetime.fromisoformat(ts.replace('Z', '+00:00')))
        except Exception:
            continue

    by_minute = defaultdict(int)
    by_minute_fail = defaultdict(int)
    for r in recs:
        ts = r.get('timestamp')
        try:
            d = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except Exception:
            continue
        k = d.strftime('%Y-%m-%d %H:%M')
        by_minute[k] += 1
        if r.get('kind') == 'failure':
            by_minute_fail[k] += 1

    mins = sorted(by_minute.keys())
    vals_all = [by_minute[m] for m in mins]
    vals_fail = [by_minute_fail[m] for m in mins]

    bar_chart('Kind Distribution', kind.most_common(), OUTDIR / 'kind_distribution.svg', '#1d4ed8')
    bar_chart('Top Events (Top 15)', events.most_common(15), OUTDIR / 'top_events.svg', '#0f766e')
    bar_chart('Failure Categories', fcat.most_common(), OUTDIR / 'failure_categories.svg', '#b45309')
    bar_chart('Failure Error Types (Top 12)', ferr.most_common(12), OUTDIR / 'failure_error_types.svg', '#be123c')
    bar_chart('Node Activity', nodes.most_common(10), OUTDIR / 'node_activity.svg', '#7c3aed')
    line_chart('Records Per Minute', mins, vals_all, OUTDIR / 'records_timeline.svg')
    line_chart('Failures Per Minute', mins, vals_fail, OUTDIR / 'failures_timeline.svg')

    stats = {
        'input_file': str(INPUT),
        'total_records': len(recs),
        'normal_records': kind.get('normal', 0),
        'failure_records': kind.get('failure', 0),
        'unique_events': len(events),
        'unique_nodes': len(nodes),
        'time_start': min(dt_all).isoformat() if dt_all else 'n/a',
        'time_end': max(dt_all).isoformat() if dt_all else 'n/a',
    }
    summary_html(stats, OUTDIR / 'eda_summary.html')
    print('Generated charts in', OUTDIR)


if __name__ == '__main__':
    main()
