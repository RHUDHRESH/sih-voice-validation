#!/usr/bin/env python3
"""One-command offline reproduction: tests -> paired replay -> evidence -> plots."""
from __future__ import annotations
import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import unittest
import wave

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from voice_harness.core import Scenario, pcm_bytes, sha, simulate
from voice_harness.plots import render


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def write_csv(path, rows):
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def source_hashes():
    files = {}
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(x in {'results', '__pycache__', '.git', '.venv', 'venv', '.playwright-cli', 'output'} for x in p.relative_to(ROOT).parts):
            continue
        if p.relative_to(ROOT).parts[:2] == ('docs', 'images'):
            continue
        if p.suffix in {'.pyc', '.zip'}:
            continue
        files[p.relative_to(ROOT).as_posix()] = sha(p.read_bytes())
    tree = sha(json.dumps(files, sort_keys=True).encode())
    return tree, files


def cpu_model():
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):
                return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or 'not disclosed by host'


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({'test': test.id(), 'status': 'pass'})
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({'test': test.id(), 'status': 'fail'})
    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({'test': test.id(), 'status': 'fail'})
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append({'test': test.id(), 'status': 'not-run', 'reason': reason})


def run(out: Path, config: Path):
    if not __debug__:
        raise RuntimeError('Run validation without -O; correctness assertions must be enabled')
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    config_bytes = config.read_bytes()
    manifest = json.loads(config_bytes)
    scenario_ids = [s['scenario_id'] for s in manifest['scenarios']]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError('scenario identifiers must be unique')
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    test_started = time.perf_counter()
    tests = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordingResult).run(suite)
    test_elapsed = time.perf_counter()-test_started
    (out / 'tests.txt').write_text(stream.getvalue())
    write_json(out / 'tests.json', {'schema_version': '1.0', 'evidence_label': 'host-measured-test-execution', 'tests_run': tests.testsRun,
                                  'status': 'pass' if tests.wasSuccessful() else 'fail',
                                  'host_runtime_seconds': test_elapsed, 'tests': tests.records,
                                  'property_seeds': [26172, 160289], 'random_capture_trials': 80,
                                  'paired_manifest_replays': 2 * len(manifest['scenarios'])})
    rows, flat, metric_rows, fixture_manifest, runtime_rows = [], [], [], [], []
    for item in manifest['scenarios']:
        case = Scenario.from_dict(item)
        pair_hash = None
        for policy in ('naive', 'buffered'):
            before = time.perf_counter()
            replay = simulate(case, policy)
            runtime = time.perf_counter() - before
            metrics = replay.metrics()
            checks = []
            for key, expected in case.expected.get(policy, {}).items():
                actual = metrics['commands'][0][key] if key == 'onset_lost_samples' else metrics[key]
                checks.append({'field': key, 'expected': expected, 'actual': actual, 'status': 'pass' if actual == expected else 'fail'})
            metrics['expected_behavior_checks'] = checks
            metrics['test_status'] = 'pass' if checks and all(c['status'] == 'pass' for c in checks) else 'fail'
            metrics['host_runtime_seconds'] = runtime
            if pair_hash is not None and pair_hash != metrics['input_sha256']:
                raise AssertionError('paired policies did not use identical PCM')
            pair_hash = metrics['input_sha256']
            rows.append(metrics)
            run_dir = out / 'runs' / f'{case.scenario_id}__{policy}'
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / 'result.json', metrics)
            write_csv(run_dir / 'events.csv', replay.events)
            write_csv(run_dir / 'telemetry.csv', replay.telemetry)
            write_csv(run_dir / 'packets.csv', replay.receiver.packets)
            for i, remote in enumerate(replay.receiver.sessions.values(), 1):
                (run_dir / f'receiver_session_{i}.pcm').write_bytes(pcm_bytes(remote.samples))
                write_json(run_dir / f'receiver_session_{i}.json', {'session_id': remote.session_id,
                            'declared_start': remote.declared_start, 'received_end': remote.end,
                            'completed_end': remote.completed_end, 'state': remote.state,
                            'sample_count': len(remote.samples), 'pcm_sha256': sha(pcm_bytes(remote.samples)),
                            'format': 's16le_mono_16000Hz', 'evidence_label': 'simulated'})
            if policy == 'naive':
                fixture_dir = out / 'fixtures'
                fixture_dir.mkdir(exist_ok=True)
                pcm_path = fixture_dir / f'{case.scenario_id}.pcm'
                pcm_path.write_bytes(pcm_bytes(replay.source))
                with wave.open(str(fixture_dir / f'{case.scenario_id}.wav'), 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(pcm_bytes(replay.source))
                fixture_manifest.append({'scenario_id': case.scenario_id, 'path': str(pcm_path.relative_to(out)),
                                         'sha256': metrics['input_sha256'], 'samples': len(replay.source),
                                         'seed': case.seed, 'kind': 'synthetic_index_pattern_not_speech',
                                         'consent': 'no_human_recordings', 'license': 'generated_for_this_validation'})
            for command in metrics['commands']:
                flat.append({'scenario_id': case.scenario_id, 'policy': policy, 'utterance_id': command['utterance_id'],
                             'evidence_label': 'simulated', 'test_status': metrics['test_status'],
                             'handoff_status': metrics['handoff_status'], 'reason': metrics['reason'],
                             'command_integrity_status': command['command_integrity_status'],
                             'command_samples': command['command_samples'],
                             'command_samples_received': command['command_samples_received'],
                             'command_samples_missing': command['command_samples_missing'],
                             'onset_lost_samples': command['onset_lost_samples'],
                             'onset_lost_ms': command['onset_lost_ms'],
                             'input_sha256': metrics['input_sha256']})
                metric_rows.append({'scenario_id': case.scenario_id, 'policy': policy, 'utterance_id': command['utterance_id'],
                                    'metric': 'command_sample_retention_fraction', 'numerator': command['command_samples_received'],
                                    'denominator': command['command_samples'], 'unit': 'fraction',
                                    'estimate': command['command_samples_received']/command['command_samples'],
                                    'confidence_interval_low': '', 'confidence_interval_high': '',
                                    'confidence_interval_reason': 'exact deterministic fixture count; not a population estimate',
                                    'status': command['command_integrity_status'],
                                    'reason': metrics['reason'] or ('complete command' if command['command_integrity_status'] == 'pass' else 'missing onset'),
                                    'evidence_label': 'simulated'})
            runtime_rows.append({'scenario_id': case.scenario_id, 'policy': policy, 'host_runtime_seconds': runtime,
                                 'evidence_label': 'host-measured', 'scope': 'simulation and internal equality checks; excludes artifact writing'})
    write_json(out / 'fixture_manifest.json', fixture_manifest)
    write_json(out / 'config_used.json', manifest)
    write_csv(out / 'summary.csv', flat)
    write_csv(out / 'metrics.csv', metric_rows)
    write_csv(out / 'host_runtime.csv', runtime_rows)
    tree_hash, files = source_hashes()
    provenance = {'run_started_utc': started, 'run_id': started.replace(':','').replace('+0000','Z'),
                  'project': 'SIH26172', 'team': 'Prototype Pioneers', 'team_id': '160289',
                  'evidence_labels': ['synthetic', 'simulated', 'host-measured runtime only'],
                  'evaluation_stage': 'exploratory_development_not_locked_generalization_test',
                  'source_tree_sha256': tree_hash, 'source_file_sha256': files, 'source_commit': None,
                  'source_commit_reason': 'standalone workspace; no repository commit claimed',
                  'config_sha256': sha(config_bytes),
                  'config_used_sha256': sha((out / 'config_used.json').read_bytes()),
                  'data_manifest_sha256': sha((out / 'fixture_manifest.json').read_bytes()),
                  'dependency_lock_sha256': sha((ROOT / 'requirements.lock').read_bytes()),
                  'model_sha256': None, 'model_status': 'not applicable: oracle events; no trained model',
                  'python': sys.version, 'implementation': platform.python_implementation(),
                  'os': platform.platform(), 'machine': platform.machine(), 'cpu_model': cpu_model(),
                  'host_logical_cpus_visible': os.cpu_count(), 'host_runtime_unit': 'perf_counter wall seconds',
                  'clock_note': 'simulated sample clock is separate from host wall time; minimum transport step is one sample',
                  'baseline_id': 'naive_capture_at_trigger_delivery',
                  'variant_id': 'buffered_capture_from_oracle_keyword_endpoint_minus_guard',
                  'units': 'sample indices half-open; PCM bytes decimal; 16000 samples/sec; two bytes/sample',
                  'seeds': [26172, 160289], 'privacy': 'all generated locally; no human speech or external transmission'}
    write_json(out / 'manifest.json', provenance)
    status = 'pass' if tests.wasSuccessful() and all(r['test_status'] == 'pass' for r in rows) else 'fail'
    summary = {'schema_version': '1.0', 'evidence_label': 'simulated', 'status': status,
               'status_meaning': 'declared software checks passed; NOT a claim that every command succeeded',
               'scenario_count': len(manifest['scenarios']), 'paired_replay_count': len(rows),
               'command_integrity_pass_count': sum(r['command_integrity_status'] == 'pass' for r in rows),
               'runs': rows}
    write_json(out / 'summary.json', summary)
    render(out)
    golden = {r['policy']: r for r in rows if r['scenario_id'] == 'golden_no_pause'}
    if set(golden) == {'naive', 'buffered'}:
        n, b = golden['naive']['commands'][0], golden['buffered']['commands'][0]
        golden_text = (f"Golden fixture: {b['command_samples']:,} command samples; naive onset loss "
                       f"{n['onset_lost_samples']:,} samples, buffered onset loss {b['onset_lost_samples']:,} samples. "
                       f"Buffered command-integrity status: {b['command_integrity_status']}; "
                       f"received range [{b['received_start']}, {b['received_end']}).")
    else:
        golden_text = 'Golden no-pause fixture is absent in this configuration; no golden result claimed.'
    (out / 'RESULTS.md').write_text(
        '# SIH26172: first software-validation results\n\n'
        '**Synthetic PCM, oracle triggers and endpointing, simulated transport. No trained KWS, speech recognition or hardware measurement.**\n\n'
        f'- {tests.testsRun} unit/property test functions: {"PASS" if tests.wasSuccessful() else "FAIL"}\n'
        f'- {len(rows)} paired replay runs across {len(manifest["scenarios"])} scenarios: expected-behavior status {status.upper()}\n'
        f'- {golden_text}\n\n'
        'Passing an expected-abort test is not successful command delivery. The full matrix retains failed handoffs and incomplete commands. '
        'The capture result depends on oracle keyword/command endpoints and configured retention; it is not acoustic accuracy.\n\n'
        'Acquisition continues through post-command drain. Only bytes already copied into the bounded in-flight packet are protected outside the ring. '
        'Loss of that packet cannot magically restore overwritten samples. Receiver acceptance models immediate acknowledgement; ACK loss is not modelled.\n\n'
        'See summary.csv/JSON, metrics.csv, manifest.json, tests.txt, fixture_manifest.json and per-run event/packet/PCM artifacts. '
        'Plots regenerate from saved summary and telemetry. Host timing is in host_runtime.csv and is not MCU timing or utilization.\n')
    from verify_artifacts import verify
    audit = verify(out)
    write_json(out / 'artifact_audit.json', audit)
    print(f'{status.upper()}: {tests.testsRun} test functions; {len(rows)} paired replays; artifacts: {out}')
    print('SIMULATED: ' + golden_text)
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'results' / 'latest')
    parser.add_argument('--config', type=Path, default=ROOT / 'config' / 'scenarios.json')
    args = parser.parse_args()
    raise SystemExit(run(args.out.resolve(), args.config.resolve()))
