"""Generate the checked-in, exploratory scenario manifest. No fitting or training."""
from dataclasses import asdict, replace
from pathlib import Path
import json
import random
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice_harness.core import Scenario, Utterance, OracleTrigger


def build():
    u = Utterance("command_1", 16000, 16000, 32000)
    t = OracleTrigger(19200, "trigger_1", "command_1", 16000, 19200)
    base = Scenario("golden_no_pause", "Oracle decision 200 ms after wake endpoint; receiver accepts after a further 300 ms.",
                    [u], [t], accept_delay_samples=4800,
                    expected={"naive": {"handoff_status": "complete", "onset_lost_samples": 3200},
                              "buffered": {"handoff_status": "complete", "onset_lost_samples": 0}})
    cases = [base]
    def add(name, description, naive="complete", buffered="complete", **kw):
        case = replace(base, scenario_id=name, description=description, accept_delay_samples=0,
                       expected={"naive": {"handoff_status": naive}, "buffered": {"handoff_status": buffered}})
        case = replace(case, **kw)
        cases.append(case)
    add("pause_300ms", "A 300 ms pause makes the 200 ms decision early enough for both capture policies.",
        utterances=[replace(u, command_start=20800, command_end=36800)])
    add("zero_detector_delay", "Oracle trigger exactly at the keyword endpoint.", triggers=[replace(t, at=16000, detected_at=16000)])
    add("detector_delay_500ms", "Half-second oracle decision delay; fixed guard still fits the ring.",
        triggers=[replace(t, at=24000, detected_at=24000)])
    add("detector_delay_exceeds_ring", "Required pre-trigger history is already gone at the oracle event.", buffered="aborted",
        triggers=[replace(t, at=32000, detected_at=32000)], utterances=[replace(u, command_end=48000)])
    add("acceptance_capacity_exact", "Acceptance at precisely the oldest retained requested sample; fast sink then catches up.",
        accept_delay_samples=11200)
    add("acceptance_capacity_plus_one", "One additional sample of acceptance delay exceeds ring retention; no clamping.",
        buffered="aborted", accept_delay_samples=11201)
    add("slow_sink_overflow", "Sink can consume only half of the source rate during a four-second command.",
        naive="aborted", buffered="aborted", packet_samples=160, packet_interval_samples=320,
        utterances=[replace(u, command_end=80000)])
    add("one_dropped_packet", "One simulated packet drop is retried from retained data.", drop_attempts=[2])
    add("duplicate_packets", "Exact duplicate chunks are acknowledged once and never appended twice.", duplicate_attempts=[2, 3])
    add("all_packets_dropped", "Persistent transport loss must end in explicit bounded failure.", naive="aborted", buffered="aborted", drop_all=True)
    add("disconnect_aborts", "Connection loss cancels the session, even if a prefix was received.",
        naive="aborted", buffered="aborted", outages=[(20800, 24000)])
    add("reconnect_session_isolation", "A new trigger after reconnect creates a new session; an old in-flight packet is rejected.",
        outages=[(19360, 19840)], transport_delay_samples=800, packet_samples=1600,
        triggers=[t, replace(t, at=19840, event_id="trigger_2", detected_at=19840)])
    add("repeated_and_busy_triggers", "Repeated event ids and a fresh trigger while busy do not fork capture sessions.",
        triggers=[t, replace(t, at=19360), replace(t, at=19680),
                  replace(t, at=19840, event_id="trigger_busy", detected_at=19840)])
    add("stale_trigger", "An event older than the configured maximum age is rejected before session creation.",
        naive="rejected", buffered="rejected", triggers=[replace(t, at=20801)])
    add("future_trigger", "An impossible future detector timestamp is rejected.", naive="rejected", buffered="rejected",
        triggers=[replace(t, detected_at=19201)])
    add("mute_during_capture", "Mute zeroes the ring and aborts the stream; no subsequent sends or new capture.",
        naive="aborted", buffered="aborted", transport_delay_samples=400,
        mute_events=[(20160, True)])
    u2 = Utterance("command_2", 38400, 38400, 48000)
    t2 = OracleTrigger(40000, "trigger_2", "command_2", 38400, 40000)
    add("mute_then_fresh_session", "After unmute, only a new session can capture the second oracle-labelled utterance.",
        utterances=[u, u2], triggers=[t, t2], mute_events=[(20800, True), (35200, False)])
    add("long_idle_ring_wrap", "Ring has wrapped several times before detection; absolute indices remain correct.",
        utterances=[Utterance("command_1", 64000, 64000, 80000)],
        triggers=[OracleTrigger(67200, "trigger_1", "command_1", 64000, 67200)])
    add("corrupted_packet", "An in-transit payload-bit corruption fails the packet checksum and aborts.",
        naive="aborted", buffered="aborted", corrupt_attempts=[2])
    add("reordered_metadata", "A wrong first-sample index is rejected rather than silently concatenated.",
        naive="aborted", buffered="aborted", reorder_attempts=[2])
    add("insufficient_startup_history", "Guard requests samples before startup, which must not be silently clamped to zero.", buffered="aborted",
        utterances=[Utterance("command_1", 800, 800, 8800)],
        triggers=[OracleTrigger(1200, "trigger_1", "command_1", 800, 1200)])
    add("acceptance_timeout", "No acceptance before the simulation deadline, with no need to overflow the ring first.",
        naive="aborted", buffered="aborted", ring_samples=64000, accept_delay_samples=100000)
    rng = random.Random(26172)
    add("irregular_packet_sizes", "Identical capture range with seeded packet sizes 1 through 317.",
        packet_samples=317, packet_interval_samples=40, packet_sizes=[rng.randint(1, 317) for _ in range(128)])
    add("post_endpoint_slow_drain", "Acquisition continues after oracle endpoint; a slow drain cannot freeze ring retention.",
        buffered="aborted", utterances=[replace(u, command_end=20000)],
        packet_samples=160, packet_interval_samples=1600)
    add("mute_while_waiting_acceptance", "Mute cancels a pending request, zeroes PCM, and prevents any wire audio.",
        naive="aborted", buffered="aborted", accept_delay_samples=4800, mute_events=[(20800, True)])
    add("capacity_with_inflight_protection", "The copied in-flight chunk protects samples overwritten before its acknowledgement.",
        accept_delay_samples=11200, transport_delay_samples=2)
    add("old_trigger_after_unmute", "An old pre-mute trigger cannot restart capture after the privacy reset, even within the age limit.",
        naive="aborted", buffered="aborted", mute_events=[(19360, True), (20000, False)],
        triggers=[t, replace(t, at=20160)])
    return cases


if __name__ == "__main__":
    manifest = {"schema_version": "1.0", "evidence_label": "simulated", "evaluation_stage": "exploratory_development",
                "detector": "oracle_events_no_trained_model", "endpoint": "oracle_no_vad",
                "seed": 26172, "sample_format": "16000_Hz_mono_signed_16bit_little_endian",
                "scenarios": [asdict(case) for case in build()]}
    dest = Path(__file__).with_name("scenarios.json")
    dest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(dest)
