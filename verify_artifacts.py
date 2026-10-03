#!/usr/bin/env python3
"""Independent offline audit of serialized PCM, chunk indices and summary counts.

Does not import or invoke the simulator. Exit nonzero on any inconsistency.
"""
import argparse
import csv
import io
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(root):
    if not __debug__:
        raise RuntimeError('Run the auditor without -O; correctness assertions must be enabled')
    summary = json.loads((root / 'summary.json').read_text())
    fixtures = {x['scenario_id']: x for x in json.loads((root / 'fixture_manifest.json').read_text())}
    config = json.loads((root / 'config_used.json').read_text())
    cases = {c['scenario_id']: c for c in config['scenarios']}
    assert len(cases) == len(config['scenarios']), 'duplicate config scenario id'
    assert len(fixtures) == len(json.loads((root / 'fixture_manifest.json').read_text())), 'duplicate fixture id'
    policies = {}
    seen_keys = set()
    checked_sessions = checked_packets = 0
    for run in summary['runs']:
        case_id, policy = run['scenario_id'], run['policy']
        assert case_id in cases and policy in {'naive', 'buffered'}
        assert (case_id, policy) not in seen_keys, 'duplicate scenario/policy key'
        seen_keys.add((case_id, policy))
        fixture = fixtures[case_id]
        source = (root / fixture['path']).read_bytes()
        assert len(source) == fixture['samples'] * 2, case_id
        assert digest(source) == fixture['sha256'] == run['input_sha256'], case_id
        policies.setdefault(case_id, {})[policy] = run['input_sha256']
        directory = root / 'runs' / f'{case_id}__{policy}'
        assert json.loads((directory/'result.json').read_text()) == run, 'per-run result differs from summary'
        ground_truth = {u['utterance_id']: u for u in cases[case_id]['utterances']}
        assert len(ground_truth) == len(cases[case_id]['utterances'])
        assert {c['utterance_id'] for c in run['commands']} == set(ground_truth)
        assert len(run['commands']) == len(ground_truth)
        events = list(csv.DictReader(io.StringIO((directory / 'events.csv').read_text())))
        packets = list(csv.DictReader(io.StringIO((directory / 'packets.csv').read_text())))
        saved = {}
        for meta_path in sorted(directory.glob('receiver_session_*.json')):
            meta = json.loads(meta_path.read_text())
            raw = meta_path.with_suffix('.pcm').read_bytes()
            start, end = meta['declared_start'], meta['received_end']
            assert start >= 0 and end >= start
            assert raw == source[2*start:2*end], meta_path
            assert digest(raw) == meta['pcm_sha256']
            assert len(raw) == 2*meta['sample_count'] == 2*(end-start)
            sid = meta['session_id']
            accepted = [p for p in packets if p['session_id'] == sid and p['disposition'] == 'ACCEPTED']
            cursor = start
            for seq, packet in enumerate(accepted):
                first, count = int(packet['first_sample_index']), int(packet['sample_count'])
                assert int(packet['seq']) == seq and first == cursor
                assert count > 0
                assert digest(source[2*first:2*(first+count)]) == packet['sha256']
                cursor += count
                checked_packets += 1
            assert cursor == end
            if meta['state'] == 'COMPLETE':
                assert meta['completed_end'] == end
            saved[sid] = meta
            checked_sessions += 1
        for session in run['sessions']:
            sends = [e for e in events if e['session_id'] == session['session_id'] and e['event'] == 'SEND']
            for event in sends:
                assert session['accepted_at'] is not None and int(event['at_sample']) >= session['accepted_at']
            if session['state'] == 'COMPLETE':
                assert saved[session['session_id']]['completed_end'] == session['capture_end']
        for command in run['commands']:
            truth = ground_truth[command['utterance_id']]
            assert command['ground_truth_start'] == truth['command_start']
            assert command['ground_truth_end'] == truth['command_end']
            if command['selected_session_id'] is not None:
                selected = next(s for s in run['sessions'] if s['session_id']==command['selected_session_id'])
                assert selected['utterance_id'] == command['utterance_id']
                if selected['state'] == 'COMPLETE':
                    assert selected['capture_end'] == truth['command_end']
            remote = saved.get(command['selected_session_id'])
            start, end = command['ground_truth_start'], command['ground_truth_end']
            count = end-start
            received = max(0, min(remote['received_end'], end)-max(remote['declared_start'], start)) if remote else 0
            lost = min(count, max(0, remote['declared_start']-start)) if remote and received > 0 else count
            assert command['command_samples'] == count
            assert command['command_samples_received'] == received
            assert command['command_samples_missing'] == count-received
            assert command['onset_lost_samples'] == lost
            complete = bool(remote and remote['state'] == 'COMPLETE' and received == count)
            assert command['command_integrity_status'] == ('pass' if complete else 'fail')
        assert run['command_integrity_status'] == ('pass' if all(c['command_integrity_status']=='pass' for c in run['commands']) else 'fail')
    assert len(summary['runs']) == 2*len(config['scenarios'])
    assert len(policies) == len(config['scenarios'])
    assert all(set(p)=={'naive','buffered'} and p['naive']==p['buffered'] for p in policies.values())
    return {'status': 'pass', 'replays_audited': len(summary['runs']),
            'receiver_sessions_audited': checked_sessions, 'accepted_packets_audited': checked_packets,
            'method': 'independent serialized PCM/chunk/summary verification; no simulator imported',
            'evidence_label': 'simulated-artifact-audit'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path, nargs='?', default=Path(__file__).resolve().parent/'results/latest')
    args = parser.parse_args()
    result = verify(args.results.resolve())
    print(json.dumps(result, indent=2))
    (args.results / 'artifact_audit.json').write_text(json.dumps(result, indent=2)+'\n')
