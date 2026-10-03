"""Reproducible delay/capacity sweeps and seeded capture/transport stress cases."""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_validation import run, write_json
from voice_harness.core import Scenario, Utterance, OracleTrigger

ROOT = Path(__file__).resolve().parent
SEED = 2617203


def clean_case(name, ring, guard, detector, acceptance):
    # 16 kHz; trigger and acceptance precede the command endpoint in this study.
    keyword, endpoint = 8000, 24000
    at = keyword+detector
    naive_ok = acceptance <= ring
    buffered_ok = detector+guard+acceptance <= ring
    expected = {
        'naive': {'handoff_status': 'complete' if naive_ok else 'aborted'},
        'buffered': {'handoff_status': 'complete' if buffered_ok else 'aborted'}}
    if naive_ok:
        expected['naive']['onset_lost_samples'] = detector
    if buffered_ok:
        expected['buffered']['onset_lost_samples'] = 0
        expected['buffered']['command_integrity_status'] = 'pass'
    return Scenario(name, 'Synthetic no-pause oracle case; expected retention derived from D + G + A <= R.',
                    [Utterance('command_1', keyword, keyword, endpoint)],
                    [OracleTrigger(at, 'trigger_1', 'command_1', keyword, at)],
                    seed=SEED, ring_samples=ring, guard_samples=guard,
                    accept_delay_samples=acceptance, packet_samples=min(320, ring),
                    packet_interval_samples=16, flush_timeout_samples=8000, expected=expected)


def build(trials=250, quick=False):
    cases = []
    for ring, guard, detector, acceptance in itertools.product([2000, 8000] if quick else [2000, 4000, 8000, 16000], [0, 800], [0, 1600] if quick else [0, 400, 1600, 3200, 6400], [0, 1600] if quick else [0, 400, 1600, 3200, 6400, 8000]):
        cases.append(clean_case(f'grid_r{ring}_g{guard}_d{detector}_a{acceptance}', ring, guard, detector, acceptance))
    for ring, detector, offset in itertools.product([2000] if quick else [2000, 4000, 8000], [0, 400] if quick else [0, 400, 800, 1200], [-1, 0, 1]):
        cases.append(clean_case(f'boundary_{ring}_{detector}_{offset+1}', ring, 400, detector, ring-detector-400+offset))
    rng = random.Random(SEED)
    for i in range(trials):
        cases.append(clean_case(f'random_{i:04}', rng.randint(500, 16000), rng.randint(0, 1600), rng.randint(0, 6000), rng.randint(0, 6000)))
    # Each fault operates in a separately established feasible retention region.
    for i in range(1 if quick else 25):
        base = clean_case('temporary', 8000, 800, 400, 400)
        base = replace(base, seed=SEED+i, packet_samples=rng.randint(100, 320))
        specs = [('drop_once', {'drop_attempts': [1]}, 'complete'),
                 ('duplicate', {'duplicate_attempts': [1, 2]}, 'complete'),
                 ('corruption', {'corrupt_attempts': [1]}, 'aborted'),
                 ('wrong_index', {'reorder_attempts': [1]}, 'aborted'),
                 ('persistent_loss', {'drop_all': True}, 'aborted'),
                 ('mute', {'mute_events': [(9600, True)]}, 'aborted'),
                 ('slow_sink', {'packet_samples': 80, 'packet_interval_samples': 160}, 'aborted')]
        for fault, changes, status in specs:
            expected = {policy: {'handoff_status': status, 'command_integrity_status': 'pass' if status == 'complete' and policy == 'buffered' else 'fail'} for policy in ('naive', 'buffered')}
            cases.append(replace(base, scenario_id=f'fault_{fault}_{i:02}', description=f'Seeded {fault} stress case.', expected=expected, **changes))
    return cases


def heatmap(out, runs, cases):
    lookup = {(r['scenario_id'], r['policy']): r for r in runs}
    columns, rows = [0, 400, 1600, 3200, 6400, 8000], [0, 400, 1600, 3200, 6400]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="700" viewBox="0 0 1120 700">',
             '<rect width="1120" height="700" fill="#f6f8fa"/>',
             '<g font-family="Arial,sans-serif" fill="#172b4d">',
             '<text x="25" y="35" font-size="23">Synthetic no-pause command integrity: buffered capture</text>',
             '<text x="25" y="60" font-size="15">Guard 50 ms; fast simulated sink; green = byte-exact complete command; red = abort</text>']
    for panel, ring in enumerate([2000, 4000, 8000, 16000]):
        x, y = 90+(panel%2)*550, 115+(panel//2)*285
        parts.append(f'<text x="{x}" y="{y-15}" font-size="19">Ring {ring/16:g} ms ({ring*2:,} PCM bytes)</text>')
        for j, delay in enumerate(rows):
            parts.append(f'<text x="{x-60}" y="{y+j*36+23}" font-size="13">{delay/16:g}</text>')
            for k, accept in enumerate(columns):
                key = f'grid_r{ring}_g800_d{delay}_a{accept}'
                if (key, 'buffered') not in lookup:
                    parts.append(f'<rect x="{x+k*65}" y="{y+j*36}" width="60" height="31" fill="#cbd5e1"/>')
                    continue
                ok = lookup[key, 'buffered']['command_integrity_status'] == 'pass'
                parts.append(f'<rect x="{x+k*65}" y="{y+j*36}" width="60" height="31" fill="{"#277f63" if ok else "#b34141"}"/>')
        for k, accept in enumerate(columns):
            parts.append(f'<text x="{x+k*65+8}" y="{y+202}" font-size="13">{accept/16:g}</text>')
        parts.append(f'<text x="{x+45}" y="{y+225}" font-size="14">Receiver acceptance delay (ms)</text>')
    parts.extend(['<text transform="translate(18 495) rotate(-90)" font-size="14">Detector delay (ms)</text>', '</g></svg>'])
    (out/'delay_capacity_heatmap.svg').write_text('\n'.join(parts), encoding='utf-8')


def main(out, trials, summarize_existing=False, quick=False):
    if out.exists() and not summarize_existing:
        raise FileExistsError(f'Choose a fresh output directory: {out}')
    out.mkdir(parents=True, exist_ok=summarize_existing)
    cases = build(trials, quick)
    config = {'schema_version': '1.0', 'evidence_label': 'simulated', 'evaluation_stage': 'exploratory_parameter_sweep',
              'detector': 'oracle_events_no_trained_model', 'endpoint': 'oracle_no_vad', 'seed': SEED,
              'sample_format': '16000_Hz_mono_signed_16bit_little_endian', 'scenarios': [asdict(c) for c in cases]}
    if not summarize_existing:
        write_json(out/'study_config.json', config)
        print(f'Running {len(cases)} scenarios / {len(cases)*2} paired replays', flush=True)
        status = run(out, out/'study_config.json')
        if status:
            raise RuntimeError('Study expectations failed; inspect summary.json')
    elif json.loads((out/'config_used.json').read_text()) != json.loads(json.dumps(config)):
        raise ValueError('Existing configuration differs from the declared study')
    audit = json.loads((out/'artifact_audit.json').read_text())
    if audit['status'] != 'pass' or audit['replays_audited'] != 2*len(cases):
        raise ValueError('Saved evidence has not passed a complete artifact audit')
    summary = json.loads((out/'summary.json').read_text())
    if summary['status'] != 'pass' or len(summary['runs']) != 2*len(cases):
        raise ValueError('Expected-behavior checks failed or replay count differs')
    groups = {}
    for group in ('grid', 'boundary', 'random', 'fault'):
        subset = [r for r in summary['runs'] if r['scenario_id'].startswith(group+'_')]
        groups[group] = {policy: {'runs': len([r for r in subset if r['policy'] == policy]),
                                 'command_integrity_pass': sum(r['policy'] == policy and r['command_integrity_status'] == 'pass' for r in subset),
                                 'handoff_complete': sum(r['policy'] == policy and r['handoff_status'] == 'complete' for r in subset),
                                 'failure_reasons': dict(Counter(r['reason'] for r in subset if r['policy'] == policy and r['handoff_status'] != 'complete'))} for policy in ('naive', 'buffered')}
    report = {'status': summary['status'], 'seed': SEED, 'scenario_count': len(cases), 'paired_replays': len(summary['runs']),
              'groups': groups, 'expectation_basis': 'Fast clean sink: buffered D+G+A <= R; naive A <= R. Fault expectations predeclared.',
              'scope': 'Synthetic indexed PCM; oracle triggers/endpoints; exploratory distribution; no speech/hardware accuracy claim'}
    write_json(out/'study_summary.json', report)
    heatmap(out, summary['runs'], cases)
    hashes = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifact_hashes.json'}
    write_json(out/'artifact_hashes.json', hashes)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'results/study_20261003')
    parser.add_argument('--trials', type=int, default=250)
    parser.add_argument('--summarize-existing', action='store_true', help='Regenerate charts/summary for matching, previously audited evidence')
    parser.add_argument('--quick', action='store_true', help='Reduced matrix for CI smoke checks; grey chart cells are not run')
    args = parser.parse_args()
    if args.trials < 1:
        parser.error('trials must be positive')
    main(args.out.resolve(), args.trials, args.summarize_existing, args.quick)
