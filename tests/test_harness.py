from array import array
from dataclasses import replace
import random
import json
from pathlib import Path
from dataclasses import asdict
import unittest

from config.make_scenarios import build
from voice_harness.core import (PCMBuffer, RetentionError, Receiver, Packet, OracleTrigger,
                                Utterance, pcm_bytes, sha, simulate, synthetic_pcm)


def fixture(name):
    return next(c for c in build() if c.scenario_id == name)


class RingTests(unittest.TestCase):
    def test_exact_capacity_and_no_clamping(self):
        ring = PCMBuffer(4)
        for i in range(4):
            ring.append(i, i)
        self.assertEqual(ring.read_bytes(0, 4), pcm_bytes(array('h', range(4))))
        ring.append(4, 4)
        self.assertEqual(ring.oldest, 1)
        with self.assertRaises(RetentionError):
            ring.read_bytes(0, 4)
        self.assertEqual(ring.read_bytes(1, 5), pcm_bytes(array('h', range(1, 5))))

    def test_fixed_storage_and_secure_clear(self):
        ring = PCMBuffer(317)
        original = id(ring.storage)
        for i in range(10000):
            ring.append(i, (i % 65536) - 32768)
        self.assertEqual(id(ring.storage), original)
        self.assertEqual(len(ring.storage), 317)
        ring.clear(12000)
        self.assertEqual(id(ring.storage), original)
        self.assertEqual(ring.retained, 0)
        self.assertTrue(all(x == 0 for x in ring.storage))
        ring.append(12000, 42)
        self.assertEqual(ring.read_bytes(12000, 12001), b'\x2a\x00')

    def test_noncontiguous_source_rejected(self):
        ring = PCMBuffer(3)
        with self.assertRaises(ValueError):
            ring.append(1, 0)

    def test_every_wrap_offset_and_random_windows(self):
        rng = random.Random(160289)
        for capacity in (1, 2, 3, 7, 31, 160, 317):
            ring = PCMBuffer(capacity)
            source = synthetic_pcm(4 * capacity, 26172)
            seen_offsets = set()
            for i, value in enumerate(source):
                ring.append(i, value)
                seen_offsets.add(ring.end % capacity)
                start = rng.randint(ring.oldest, ring.end)
                end = rng.randint(start, ring.end)
                self.assertEqual(ring.read_bytes(start, end), pcm_bytes(source[start:end]))
                self.assertLessEqual(ring.retained, capacity)
            self.assertEqual(seen_offsets, set(range(capacity)))
            with self.assertRaises(RetentionError):
                ring.read_bytes(ring.oldest - 1, ring.end)


class CaptureTests(unittest.TestCase):
    def test_golden_exact_3200_vs_zero_and_paired_pcm(self):
        case = fixture('golden_no_pause')
        naive, buffered = simulate(case, 'naive'), simulate(case, 'buffered')
        nm, bm = naive.metrics(), buffered.metrics()
        self.assertEqual(nm['input_sha256'], bm['input_sha256'])
        self.assertEqual(nm['commands'][0]['onset_lost_samples'], 3200)
        self.assertEqual(bm['commands'][0]['onset_lost_samples'], 0)
        self.assertEqual(bm['commands'][0]['command_samples_received'], 16000)
        remote = next(iter(buffered.receiver.sessions.values()))
        self.assertEqual(remote.accepted_at, 24000)
        self.assertEqual(remote.declared_start, 14400)
        self.assertEqual(pcm_bytes(remote.samples[1600:]), pcm_bytes(buffered.source[16000:32000]))
        self.assertEqual(nm['command_integrity_status'], 'fail')
        self.assertEqual(bm['command_integrity_status'], 'pass')

    def test_capacity_boundary_then_one_sample_failure(self):
        exact = simulate(fixture('acceptance_capacity_exact'), 'buffered').metrics()
        over = simulate(fixture('acceptance_capacity_plus_one'), 'buffered').metrics()
        self.assertEqual(exact['handoff_status'], 'complete')
        self.assertEqual(over['handoff_status'], 'aborted')
        self.assertEqual(over['reason'], 'BUFFER_OVERFLOW_PENDING')
        self.assertEqual(over['wire_samples_including_retries'], 0)

    def test_all_scenario_outcomes_and_invariants(self):
        for case in build():
            for policy in ('naive', 'buffered'):
                with self.subTest(case=case.scenario_id, policy=policy):
                    run = simulate(case, policy)
                    metrics = run.metrics()
                    expected = case.expected[policy]
                    self.assertEqual(metrics['handoff_status'], expected['handoff_status'])
                    if 'onset_lost_samples' in expected:
                        self.assertEqual(metrics['commands'][0]['onset_lost_samples'], expected['onset_lost_samples'])
                    self.assertLessEqual(metrics['ring_high_water_samples'], case.ring_samples)
                    self.assertLessEqual(metrics['maximum_packet_payload_bytes'], 2 * case.packet_samples)
                    self.assertEqual(len(run.ring.storage), case.ring_samples)
                    accepted_at = {s.session_id: s.accepted_at for s in run.sessions}
                    for event in run.events:
                        if event['event'] == 'SEND':
                            self.assertIsNotNone(accepted_at[event['session_id']])
                            self.assertGreaterEqual(event['at_sample'], accepted_at[event['session_id']])
                    for remote in run.receiver.sessions.values():
                        self.assertEqual(pcm_bytes(remote.samples), pcm_bytes(run.source[remote.declared_start:remote.end]))

    def test_manifest_matches_generator(self):
        path = Path(__file__).resolve().parents[1] / 'config' / 'scenarios.json'
        saved = json.loads(path.read_text())['scenarios']
        generated = json.loads(json.dumps([asdict(c) for c in build()]))
        self.assertEqual(saved, generated)

    def test_continuous_acquisition_after_endpoint(self):
        run = simulate(fixture('post_endpoint_slow_drain'), 'buffered')
        self.assertEqual(run.metrics()['reason'], 'BUFFER_OVERFLOW_STREAMING')
        self.assertGreater(run.sessions[0].finished_at, 20000)
        self.assertGreater(run.ring.end, 20000)
        self.assertGreater(len(run.source), 20000)

    def test_inflight_packet_protects_overwritten_ring_prefix(self):
        run = simulate(fixture('capacity_with_inflight_protection'), 'buffered')
        self.assertEqual(run.metrics()['command_integrity_status'], 'pass')
        # Dropping that same protected packet cannot magically recover overwritten audio.
        run = simulate(replace(fixture('capacity_with_inflight_protection'), drop_attempts=[1]), 'buffered')
        self.assertEqual(run.metrics()['reason'], 'BUFFER_OVERFLOW_STREAMING')

    def test_mute_before_acceptance(self):
        for policy in ('naive', 'buffered'):
            run = simulate(fixture('mute_while_waiting_acceptance'), policy)
            self.assertEqual(run.metrics()['reason'], 'MUTED')
            self.assertEqual(run.wire_samples, 0)
            self.assertEqual(run.ring.retained, 0)
            self.assertTrue(run.mute_clear_verified)

    def test_packet_boundaries_do_not_change_capture_range(self):
        case = fixture('golden_no_pause')
        for size in (1, 160, 317):
            changed = replace(case, packet_samples=size, packet_interval_samples=max(1, size // 2))
            run = simulate(changed, 'buffered')
            metrics = run.metrics()
            self.assertEqual(metrics['handoff_status'], 'complete')
            remote = next(iter(run.receiver.sessions.values()))
            self.assertEqual((remote.declared_start, remote.end), (14400, 32000))
            self.assertEqual(pcm_bytes(remote.samples), pcm_bytes(run.source[14400:32000]))
        irregular = simulate(fixture('irregular_packet_sizes'), 'buffered')
        self.assertEqual(irregular.metrics()['commands'][0]['command_integrity_status'], 'pass')

    def test_seeded_random_capture_properties(self):
        rng = random.Random(160289)
        for trial in range(80):
            keyword = rng.randint(1000, 3000)
            delay = rng.randint(0, 400)
            guard = rng.randint(0, 128)
            size = rng.randint(1, 128)
            case = replace(fixture('golden_no_pause'), scenario_id=f'property_{trial}', seed=rng.randrange(65536),
                           utterances=[Utterance('u', keyword, keyword, keyword + rng.randint(500, 1600))],
                           triggers=[OracleTrigger(keyword + delay, 'event', 'u', keyword, keyword + delay)],
                           ring_samples=2048, guard_samples=guard, accept_delay_samples=rng.randint(0, 300),
                           packet_samples=size, packet_interval_samples=max(1, size // 2),
                           drop_attempts=[2, 5], flush_timeout_samples=8000)
            for policy in ('naive', 'buffered'):
                run = simulate(case, policy)
                metrics = run.metrics()
                self.assertEqual(metrics['handoff_status'], 'complete')
                expected_loss = delay if policy == 'naive' else 0
                self.assertEqual(metrics['commands'][0]['onset_lost_samples'], expected_loss)
                self.assertTrue(metrics['commands'][0]['receiver_bytes_match_source'])

    def test_retries_duplicates_and_reconnect(self):
        dropped = simulate(fixture('one_dropped_packet'), 'buffered')
        self.assertEqual(dropped.metrics()['handoff_status'], 'complete')
        self.assertTrue(any(e['event'] == 'PACKET_DROPPED' for e in dropped.events))
        duplicates = simulate(fixture('duplicate_packets'), 'buffered').metrics()
        self.assertEqual(duplicates['duplicate_packets_ignored'], 2)
        reconnect = simulate(fixture('reconnect_session_isolation'), 'buffered').metrics()
        self.assertEqual(reconnect['session_count'], 2)
        self.assertEqual(reconnect['sessions'][0]['state'], 'ABORTED')
        self.assertEqual(reconnect['sessions'][1]['state'], 'COMPLETE')
        self.assertEqual(reconnect['closed_session_packets_rejected'], 1)
        self.assertEqual(reconnect['command_integrity_status'], 'pass')

    def test_mute_no_new_capture_or_send_and_fresh_session(self):
        run = simulate(fixture('mute_during_capture'), 'buffered')
        self.assertTrue(run.mute_clear_verified)
        self.assertTrue(all(e['at_sample'] < 20160 for e in run.events if e['event'] == 'SEND'))
        self.assertTrue(all(x == 0 for x in run.ring.storage))
        self.assertEqual(run.ring.retained, 0)
        self.assertEqual(run.metrics()['reason'], 'MUTED')
        resumed = simulate(fixture('mute_then_fresh_session'), 'buffered').metrics()
        self.assertEqual(resumed['sessions'][0]['state'], 'ABORTED')
        self.assertEqual(resumed['sessions'][1]['state'], 'COMPLETE')
        self.assertEqual(resumed['commands'][1]['command_integrity_status'], 'pass')
        self.assertEqual(resumed['command_integrity_status'], 'fail')  # First command remains lost.

    def test_repeated_stale_and_future_triggers(self):
        run = simulate(fixture('repeated_and_busy_triggers'), 'buffered')
        self.assertEqual(len(run.sessions), 1)
        self.assertEqual(sum(e['detail'] == 'DUPLICATE_EVENT' for e in run.events), 2)
        for name in ('stale_trigger', 'future_trigger'):
            run = simulate(fixture(name), 'buffered')
            self.assertEqual(len(run.sessions), 0)
            self.assertEqual(run.wire_samples, 0)

    def test_empty_receiver_is_not_onset_retention(self):
        metrics = simulate(fixture('all_packets_dropped'), 'naive').metrics()
        self.assertEqual(metrics['commands'][0]['command_samples_received'], 0)
        self.assertEqual(metrics['commands'][0]['onset_lost_samples'], 16000)
        self.assertFalse(metrics['commands'][0]['onset_retained'])

    def test_pre_reset_trigger_cannot_reactivate_capture(self):
        for policy in ('naive', 'buffered'):
            run = simulate(fixture('old_trigger_after_unmute'), policy)
            self.assertEqual(len(run.sessions), 1)
            self.assertEqual(run.metrics()['reason'], 'MUTED')
            self.assertTrue(any(e['detail'] == 'PRE_RESET_EVENT' for e in run.events))
            self.assertTrue(all(e['at_sample'] < 19360 for e in run.events if e['event'] == 'SEND'))

    def test_pcm_period_and_seed_reproducibility(self):
        self.assertEqual(synthetic_pcm(70000, 1), synthetic_pcm(70000, 1))
        self.assertEqual(len(set(synthetic_pcm(65536, 1))), 65536)
        self.assertNotEqual(synthetic_pcm(10, 1), synthetic_pcm(10, 2))


class ReceiverTests(unittest.TestCase):
    def test_duplicate_gap_corruption_and_closed_session(self):
        receiver = Receiver()
        receiver.open('a', 100, 200)
        payload = pcm_bytes(array('h', [10, 20]))
        packet = Packet('a', 0, 100, 2, payload, sha(payload))
        self.assertEqual(receiver.receive(packet, 201), 'ACCEPTED')
        self.assertEqual(receiver.receive(packet, 202), 'DUPLICATE_IGNORED')
        gap = replace(packet, seq=1, first_sample_index=103)
        self.assertEqual(receiver.receive(gap, 203), 'REJECT_NONCONTIGUOUS')
        bad = replace(packet, payload=b'\0' * 4)
        self.assertEqual(receiver.receive(bad, 204), 'REJECT_CHECKSUM_OR_LENGTH')
        receiver.abort('a')
        self.assertEqual(receiver.receive(packet, 205), 'REJECT_CLOSED_SESSION')
        self.assertEqual(len(receiver.sessions['a'].samples), 2)

    def test_conflicting_duplicate_true_sequence_gap_and_timing(self):
        receiver = Receiver()
        receiver.open('a', 100, 200)
        payload = pcm_bytes(array('h', [10, 20]))
        packet = Packet('a', 0, 100, 2, payload, sha(payload))
        self.assertEqual(receiver.receive(packet, 199), 'REJECT_NONCAUSAL_TIMING')
        self.assertEqual(receiver.receive(replace(packet, first_sample_index=201), 200), 'REJECT_NONCAUSAL_TIMING')
        self.assertEqual(receiver.receive(packet, 201), 'ACCEPTED')
        conflict = pcm_bytes(array('h', [10, 21]))
        self.assertEqual(receiver.receive(replace(packet, payload=conflict, checksum=sha(conflict)), 202),
                         'REJECT_CONFLICTING_DUPLICATE')
        self.assertEqual(receiver.receive(replace(packet, seq=2, first_sample_index=102), 203),
                         'REJECT_NONCONTIGUOUS')

    def test_incomplete_receiver_cannot_claim_completion(self):
        receiver = Receiver()
        receiver.open('a', 100, 0)
        with self.assertRaises(AssertionError):
            receiver.finish('a', 200)


if __name__ == '__main__':
    unittest.main()
