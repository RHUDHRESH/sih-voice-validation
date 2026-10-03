"""Dependency-free static SVG plots, generated from saved results only."""
from html import escape
from pathlib import Path
import csv
import io
import json

BLUE, ORANGE, RED, GREEN, INK = '#2563eb', '#d97706', '#b91c1c', '#087f5b', '#14213d'


def text(x, y, label, size=15, fill=INK, anchor='start', weight='normal'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">{escape(str(label))}</text>'


def header(width, height, title, subtitle):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
            f'<title>{escape(title)}</title>', f'<desc>{escape(subtitle)}</desc>',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            '<g font-family="DejaVu Sans, Arial, sans-serif">',
            text(32, 35, 'SIMULATED · ORACLE TRIGGERS · NO KWS / ASR / HARDWARE MEASUREMENT', 12, '#526173', weight='bold'),
            text(32, 70, title, 26, weight='bold'), text(32, 100, subtitle, 14, '#526173')]


def save(path, parts):
    path.write_text('\n'.join(parts + ['</g>', '</svg>']) + '\n')


def render(results_dir: Path):
    payload = json.loads((results_dir / 'summary.json').read_text())
    rows = payload['runs']
    lookup = {(r['scenario_id'], r['policy']): r for r in rows}
    out = results_dir / 'plots'
    out.mkdir(exist_ok=True)
    golden_n, golden_b = lookup.get(('golden_no_pause', 'naive')), lookup.get(('golden_no_pause', 'buffered'))
    if golden_n is not None and golden_b is not None:
        n, b = golden_n['commands'][0], golden_b['commands'][0]
        start, end = b['ground_truth_start'], b['ground_truth_end']
        bs = golden_b['sessions'][0] if golden_b['sessions'] else None
        ns = golden_n['sessions'][0] if golden_n['sessions'] else None
        markers = [(start, 'Command onset'), (end, 'Command end')]
        if bs:
            markers += [(bs['requested_start'], 'Requested start'), (bs['requested_at'], 'Oracle trigger')]
            if bs['accepted_at'] is not None:
                markers.append((bs['accepted_at'], 'Accepted'))
        lo, hi = min(v for v, _ in markers), max(v for v, _ in markers)
        margin = max(1, (hi-lo)*0.05)
        xmin, xmax, left, width = lo-margin, hi+margin, 200, 850
        x = lambda sample: left + (sample-xmin)/(xmax-xmin)*width
        parts = header(1120, 450,
                       f"Golden onset loss: {n['onset_lost_samples']:,} vs {b['onset_lost_samples']:,} samples",
                       f"Identical PCM: {golden_b['input_sha256'][:20]}… | Ring payload: {golden_b['ring_pcm_payload_bytes']:,} bytes")
        for i, (sample, label) in enumerate(sorted(markers)):
            parts.append(f'<line x1="{x(sample)}" y1="150" x2="{x(sample)}" y2="337" stroke="#cbd5e1" stroke-dasharray="4 4"/>')
            parts.append(text(x(sample), 126 if i%2==0 else 143, label, 11, anchor='middle'))
            parts.append(text(x(sample), 358 if i%2==0 else 375, f'{sample/16000:.4f} s', 11, anchor='middle'))
        tracks = [(180, 'Required command', start, end, INK),
                  (245, 'Naive received', n['received_start'], n['received_end'], ORANGE),
                  (310, 'Buffered received', b['received_start'], b['received_end'], BLUE)]
        for y, label, first, last, color in tracks:
            parts.append(text(32, y+5, label, 15, weight='bold'))
            if first is not None and last is not None and last > first:
                parts.append(f'<rect x="{x(first)}" y="{y-15}" width="{x(last)-x(first)}" height="28" fill="{color}" rx="3"/>')
            else:
                parts.append(text(left+10, y+4, 'No received samples', 13, RED))
        if n['received_start'] is not None and n['received_start'] > start:
            lost_end = min(n['received_start'], end)
            parts.append(f'<rect x="{x(start)}" y="230" width="{x(lost_end)-x(start)}" height="28" fill="#fee2e2"/>')
            parts.append(text((x(start)+x(lost_end))/2, 249, f"{n['onset_lost_ms']:g} ms lost", 12, RED, 'middle'))
        parts.append(text(32, 408, f"Buffered: {b['command_samples_received']:,}/{b['command_samples']:,} command samples received; integrity {b['command_integrity_status'].upper()}.", 14))
        parts.append(text(32, 431, 'Oracle keyword endpoint and endpointing are test inputs. Exact byte checks apply only to these simulated captures.', 13, '#526173'))
        save(out/'golden_coverage.svg', parts)
    else:
        save(out/'golden_coverage.svg', header(1120, 180, 'Golden fixture unavailable',
             'This configuration contains no paired golden_no_pause fixture. No golden result is plotted.'))

    candidates = [('golden_no_pause', BLUE, 'Golden'), ('slow_sink_overflow', ORANGE, 'Slow sink')]
    series = []
    for name, color, label in candidates:
        if (name, 'buffered') in lookup:
            telemetry = list(csv.DictReader(io.StringIO((results_dir/'runs'/f'{name}__buffered'/'telemetry.csv').read_text())))
            series.append((name, color, label, telemetry))
    if series:
        parts = header(1120, 520, 'Finite retention and explicit failure',
                       'Buffered policy; unacknowledged backlog may include one protected in-flight packet.')
        xmax = max(int(r['at_sample'])/16000 for _, _, _, rows_t in series for r in rows_t) or 1
        capacity = max(lookup[(name, 'buffered')]['ring_capacity_samples'] for name, _, _, _ in series)
        ymax = max(capacity, max(int(r['unacknowledged_backlog_samples']) for _, _, _, rows_t in series for r in rows_t))*1.12
        left, top, width, height = 100, 140, 930, 280
        for i in range(5):
            tick = capacity*i/4
            y = top+height*(1-tick/ymax)
            parts += [f'<line x1="{left}" y1="{y}" x2="{left+width}" y2="{y}" stroke="#e2e8f0"/>', text(left-12, y+4, f'{tick:,.0f}', 12, anchor='end')]
        for i in range(6):
            parts.append(text(left+i*width/5, top+height+24, f'{i*xmax/5:.1f}', 12, anchor='middle'))
        for index, (name, color, label, telemetry) in enumerate(series):
            cap = lookup[(name, 'buffered')]['ring_capacity_samples']
            cy = top+height*(1-cap/ymax)
            parts.append(f'<line x1="{left}" y1="{cy}" x2="{left+width}" y2="{cy}" stroke="{color}" stroke-dasharray="6 4"/>')
            points = ' '.join(f'{left+int(r["at_sample"])/16000/xmax*width:.2f},{top+height*(1-int(r["unacknowledged_backlog_samples"])/ymax):.2f}' for r in telemetry)
            parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>')
            parts.append(f'<rect x="{120+index*410}" y="468" width="18" height="8" fill="{color}"/>')
            status = lookup[(name, 'buffered')]['handoff_status'].upper()
            parts.append(text(146+index*410, 478, f'{label}: {status}; ring {cap:,}', 13))
        parts.append(text(565, 460, 'Source sample clock (seconds)', 13, anchor='middle'))
        parts.append(text(32, 505, 'A drop after cancellation means the session was abandoned. It does not mean missing audio was delivered.', 13, '#526173'))
        save(out/'backlog_and_overflow.svg', parts)
    else:
        save(out/'backlog_and_overflow.svg', header(1120, 180, 'Selected backlog fixtures unavailable',
             'This configuration does not include golden_no_pause or slow_sink_overflow.'))

    names = list(dict.fromkeys(r['scenario_id'] for r in rows))
    parts = header(1180, 190 + len(names)*38, 'All declared cases, including deliberate failures',
                   'Each cell reports handoff state / complete-command checks passed. An aborted prefix never counts as a complete command.')
    parts += [text(32, 144, 'Scenario', 15, weight='bold'), text(620, 144, 'Naive', 15, weight='bold'), text(925, 144, 'Buffered', 15, weight='bold')]
    for i, name in enumerate(names):
        y = 178 + i*38
        if i % 2 == 0:
            parts.append(f'<rect x="24" y="{y-23}" width="1132" height="37" fill="#f6f8fb"/>')
        parts.append(text(32, y, name.replace('_', ' '), 14))
        for px, policy in ((620, 'naive'), (925, 'buffered')):
            row = lookup[(name, policy)]
            n = sum(c['command_integrity_status'] == 'pass' for c in row['commands'])
            d = len(row['commands'])
            color = GREEN if n == d else RED
            parts.append(text(px, y, f'{row["handoff_status"].upper()} / {n} of {d}', 14, color))
    parts.append(text(32, 173+len(names)*38, 'Every expected behavior check can pass while a handoff or command-integrity result deliberately fails. See summary.json.', 12, '#526173'))
    save(out / 'all_scenario_outcomes.svg', parts)
