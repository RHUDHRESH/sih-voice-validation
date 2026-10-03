"""Sample-clock simulation with a fixed PCM ring and one bounded in-flight packet.

All acoustic, endpoint and network events are synthetic/oracle inputs. The fixture,
receiver and test logs are host-side instruments, NOT device memory.
"""
from __future__ import annotations

from array import array
from collections import deque
from dataclasses import asdict, dataclass, field
import hashlib
import sys
import re


def pcm_bytes(samples: array) -> bytes:
    values = array("h", samples)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def from_pcm(payload: bytes) -> array:
    values = array("h")
    values.frombytes(payload)
    if sys.byteorder != "little":
        values.byteswap()
    return values


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class RetentionError(RuntimeError):
    pass


class PCMBuffer:
    """Fixed allocation; sample indices use a monotonic absolute source clock."""
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.storage = array("h", [0]) * capacity
        if self.storage.itemsize != 2:
            raise RuntimeError("this harness requires 16-bit array('h')")
        self.base = self.end = 0
        self.high_water = 0

    @property
    def oldest(self) -> int:
        return max(self.base, self.end - self.capacity)

    @property
    def retained(self) -> int:
        return self.end - self.oldest

    def append(self, index: int, value: int) -> None:
        if index != self.end:
            raise ValueError("source indices must be contiguous; clear before a gap")
        self.storage[index % self.capacity] = value
        self.end += 1
        self.high_water = max(self.high_water, self.retained)

    def clear(self, next_index: int) -> None:
        # In-place zeroing preserves the allocation; no second full PCM ring.
        for i in range(self.capacity):
            self.storage[i] = 0
        self.base = self.end = next_index

    def read_bytes(self, start: int, end: int) -> bytes:
        if start < self.oldest or end > self.end or start > end:
            raise RetentionError(f"requested [{start},{end}), retained [{self.oldest},{self.end})")
        # Temporary copy is bounded by the configured maximum packet size.
        payload = bytearray(2 * (end - start))
        for offset, i in enumerate(range(start, end)):
            value = self.storage[i % self.capacity] & 65535
            payload[2 * offset] = value & 255
            payload[2 * offset + 1] = value >> 8
        return bytes(payload)


@dataclass(frozen=True)
class Utterance:
    utterance_id: str
    keyword_end: int
    command_start: int
    command_end: int


@dataclass(frozen=True)
class OracleTrigger:
    at: int
    event_id: str
    utterance_id: str
    keyword_end: int
    detected_at: int


@dataclass
class Scenario:
    scenario_id: str
    description: str
    utterances: list[Utterance]
    triggers: list[OracleTrigger]
    seed: int = 26172
    sample_rate: int = 16000
    ring_samples: int = 16000
    guard_samples: int = 1600
    packet_samples: int = 320
    packet_interval_samples: int = 160
    packet_sizes: list[int] = field(default_factory=list)
    accept_delay_samples: int = 0
    transport_delay_samples: int = 0
    outages: list[tuple[int, int]] = field(default_factory=list)
    mute_events: list[tuple[int, bool]] = field(default_factory=list)
    drop_attempts: list[int] = field(default_factory=list)
    duplicate_attempts: list[int] = field(default_factory=list)
    corrupt_attempts: list[int] = field(default_factory=list)
    reorder_attempts: list[int] = field(default_factory=list)
    drop_all: bool = False
    max_trigger_age_samples: int = 1600
    flush_timeout_samples: int = 32000
    expected: dict = field(default_factory=dict)

    def validate(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.scenario_id):
            raise ValueError("scenario_id must be a safe alphanumeric artifact name")
        if self.sample_rate != 16000:
            raise ValueError("initial milestone fixes the sample rate at 16 kHz")
        if min(self.ring_samples, self.packet_samples, self.packet_interval_samples) <= 0:
            raise ValueError("buffer and packet settings must be positive")
        if min(self.guard_samples, self.accept_delay_samples, self.transport_delay_samples,
               self.max_trigger_age_samples, self.flush_timeout_samples) < 0:
            raise ValueError("timing values must be nonnegative")
        if self.packet_samples > self.ring_samples:
            raise ValueError("packet size cannot exceed ring capacity")
        if any(n <= 0 or n > self.packet_samples for n in self.packet_sizes):
            raise ValueError("every packet size must fit the declared packet bound")
        if not self.utterances:
            raise ValueError("at least one ground-truth utterance is required")
        ids = {u.utterance_id for u in self.utterances}
        if len(ids) != len(self.utterances):
            raise ValueError("utterance identifiers must be unique")
        for u in self.utterances:
            if not 0 <= u.keyword_end <= u.command_start < u.command_end:
                raise ValueError("invalid half-open utterance ranges")
        for e in self.triggers:
            if e.at < 0 or e.utterance_id not in ids:
                raise ValueError("invalid trigger envelope")
        if any(a < 0 or b <= a for a, b in self.outages):
            raise ValueError("invalid outage interval")

    @property
    def last_scheduled_sample(self) -> int:
        return max([u.command_end for u in self.utterances] + [e.at for e in self.triggers]
                   + [at for at, _ in self.mute_events])

    @property
    def source_samples(self) -> int:
        # Keep synthetic microphone acquisition active during endpoint flushing.
        return self.last_scheduled_sample + self.flush_timeout_samples

    @classmethod
    def from_dict(cls, values: dict) -> Scenario:
        values = dict(values)
        values["utterances"] = [Utterance(**u) for u in values["utterances"]]
        values["triggers"] = [OracleTrigger(**e) for e in values["triggers"]]
        return cls(**values)


def synthetic_pcm(samples: int, seed: int) -> array:
    """Seeded modular permutation, not speech. Unique values within each 65,536-sample period."""
    multiplier = ((seed * 2 + 1) & 65535) or 1
    offset = (seed * 40503 + 17) & 65535
    return array("h", (((i * multiplier + offset) & 65535) - 32768 for i in range(samples)))


@dataclass(frozen=True)
class Packet:
    session_id: str
    seq: int
    first_sample_index: int
    sample_count: int
    payload: bytes
    checksum: str


@dataclass
class ReceiverSession:
    session_id: str
    declared_start: int
    accepted_at: int
    state: str = "OPEN"
    samples: array = field(default_factory=lambda: array("h"))
    next_seq: int = 0
    packet_signatures: dict = field(default_factory=dict)
    completed_end: int | None = None

    @property
    def end(self) -> int:
        return self.declared_start + len(self.samples)


class Receiver:
    """Simulated external sink. Its archive is intentionally outside the edge budget."""
    def __init__(self):
        self.sessions: dict[str, ReceiverSession] = {}
        self.packets: list[dict] = []

    def open(self, session_id: str, start: int, at: int) -> None:
        if session_id in self.sessions:
            raise ValueError("session ids may never be reused")
        self.sessions[session_id] = ReceiverSession(session_id, start, at)

    def receive(self, packet: Packet, at: int) -> str:
        session = self.sessions.get(packet.session_id)
        signature = (packet.first_sample_index, packet.sample_count, packet.checksum)
        if session is None or session.state != "OPEN":
            disposition = "REJECT_CLOSED_SESSION"
        elif at < session.accepted_at or packet.first_sample_index + packet.sample_count > at:
            disposition = "REJECT_NONCAUSAL_TIMING"
        elif packet.sample_count <= 0 or len(packet.payload) != 2 * packet.sample_count or sha(packet.payload) != packet.checksum:
            disposition = "REJECT_CHECKSUM_OR_LENGTH"
        elif packet.seq < session.next_seq:
            disposition = ("DUPLICATE_IGNORED" if session.packet_signatures.get(packet.seq) == signature
                           else "REJECT_CONFLICTING_DUPLICATE")
        elif packet.seq != session.next_seq or packet.first_sample_index != session.end:
            disposition = "REJECT_NONCONTIGUOUS"
        else:
            session.samples.extend(from_pcm(packet.payload))
            session.packet_signatures[packet.seq] = signature
            session.next_seq += 1
            disposition = "ACCEPTED"
        self.packets.append({"at_sample": at, "session_id": packet.session_id,
                             "seq": packet.seq, "first_sample_index": packet.first_sample_index,
                             "sample_count": packet.sample_count, "sha256": packet.checksum,
                             "disposition": disposition, "evidence_label": "simulated"})
        return disposition

    def finish(self, session_id: str, end: int) -> None:
        session = self.sessions[session_id]
        if session.state != "OPEN" or session.end != end:
            raise AssertionError("receiver completion must match its exact contiguous end")
        session.state = "COMPLETE"
        session.completed_end = end

    def abort(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions[session_id].state = "ABORTED"


@dataclass
class CaptureSession:
    session_id: str
    utterance_id: str
    requested_start: int
    requested_at: int
    cursor: int
    state: str = "REQUESTED"
    reason: str = ""
    accepted_at: int | None = None
    finished_at: int | None = None
    capture_end: int | None = None
    seq: int = 0
    next_send_at: int = 0


@dataclass
class Flight:
    packet: Packet
    deliver_at: int
    drop: bool
    duplicate: bool
    corrupt: bool
    reorder: bool


@dataclass
class Run:
    scenario: Scenario
    policy: str
    source: array
    sessions: list[CaptureSession]
    receiver: Receiver
    events: list[dict]
    telemetry: list[dict]
    ring: PCMBuffer
    maximum_packet_bytes: int
    wire_samples: int
    mute_clear_verified: bool

    def metrics(self) -> dict:
        command_rows = []
        for utterance in self.scenario.utterances:
            candidates = [s for s in self.sessions if s.utterance_id == utterance.utterance_id]
            complete = [s for s in candidates if s.state == "COMPLETE"]
            selected = complete[-1] if complete else (candidates[-1] if candidates else None)
            remote = self.receiver.sessions.get(selected.session_id) if selected else None
            start = remote.declared_start if remote else None
            end = remote.end if remote else None
            count = utterance.command_end - utterance.command_start
            retained = max(0, min(end, utterance.command_end) - max(start, utterance.command_start)) if remote else 0
            lost_prefix = (min(count, max(0, start - utterance.command_start)) if remote and retained > 0 else count)
            exact = bool(remote is not None and pcm_bytes(remote.samples) ==
                         pcm_bytes(self.source[remote.declared_start:remote.end]))
            delivered = bool(selected and selected.state == "COMPLETE" and exact and retained == count)
            command_rows.append({"utterance_id": utterance.utterance_id,
                                 "selected_session_id": selected.session_id if selected else None,
                                 "ground_truth_start": utterance.command_start,
                                 "ground_truth_end": utterance.command_end,
                                 "received_start": start, "received_end": end,
                                 "command_samples": count, "command_samples_received": retained,
                                 "command_samples_missing": count - retained,
                                 "onset_lost_samples": lost_prefix,
                                 "onset_lost_ms": 1000 * lost_prefix / self.scenario.sample_rate,
                                 "onset_retained": retained > 0 and lost_prefix == 0,
                                 "receiver_bytes_match_source": exact,
                                 "command_integrity_status": "pass" if delivered else "fail"})
        for sid, remote in self.receiver.sessions.items():
            if pcm_bytes(remote.samples) != pcm_bytes(self.source[remote.declared_start:remote.end]):
                raise AssertionError(f"receiver data differs from source in {sid}")
        last = self.sessions[-1] if self.sessions else None
        return {"scenario_id": self.scenario.scenario_id, "policy": self.policy,
                "evidence_label": "simulated", "detector": "oracle_events_no_kws_model",
                "endpoint": "oracle_endpoint_no_vad", "input_sha256": sha(pcm_bytes(self.source)),
                "handoff_status": last.state.lower() if last else "rejected",
                "reason": last.reason if last else "NO_VALID_TRIGGER",
                "command_integrity_status": "pass" if all(x["command_integrity_status"] == "pass" for x in command_rows) else "fail",
                "ring_capacity_samples": self.ring.capacity,
                "ring_pcm_payload_bytes": self.ring.capacity * 2,
                "ring_high_water_samples": self.ring.high_water,
                "maximum_packet_payload_bytes": self.maximum_packet_bytes,
                "configured_packet_payload_bound_bytes": self.scenario.packet_samples * 2,
                "wire_samples_including_retries": self.wire_samples,
                "receiver_accepted_samples": sum(len(s.samples) for s in self.receiver.sessions.values()),
                "duplicate_packets_ignored": sum(x["disposition"] == "DUPLICATE_IGNORED" for x in self.receiver.packets),
                "closed_session_packets_rejected": sum(x["disposition"] == "REJECT_CLOSED_SESSION" for x in self.receiver.packets),
                "mute_clear_verified": self.mute_clear_verified,
                "session_count": len(self.sessions), "commands": command_rows,
                "sessions": [asdict(s) for s in self.sessions]}


def simulate(scenario: Scenario, policy: str) -> Run:
    scenario.validate()
    if policy not in {"naive", "buffered"}:
        raise ValueError("unknown capture policy")
    source = synthetic_pcm(scenario.source_samples, scenario.seed)
    ring, receiver = PCMBuffer(scenario.ring_samples), Receiver()
    events, telemetry, sessions = [], [], []
    seen_events = deque(maxlen=8)  # Explicit bounded duplicate-event cache.
    active: CaptureSession | None = None
    flight: Flight | None = None  # At most one outstanding bounded packet.
    muted, mute_clear_verified = False, True
    last_reset_sample = 0
    attempts = maximum_packet_bytes = wire_samples = 0
    trigger_schedule: dict[int, list[OracleTrigger]] = {}
    endpoint_schedule: dict[int, list[Utterance]] = {}
    mute_schedule = dict(scenario.mute_events)
    for e in scenario.triggers:
        trigger_schedule.setdefault(e.at, []).append(e)
    for u in scenario.utterances:
        endpoint_schedule.setdefault(u.command_end, []).append(u)
    deadline = scenario.source_samples

    def log(at: int, event: str, sid: str = "", detail: str = "") -> None:
        events.append({"at_sample": at, "event": event, "session_id": sid,
                       "detail": detail, "evidence_label": "simulated"})

    def online(at: int) -> bool:
        return not any(start <= at < end for start, end in scenario.outages)

    def abort(at: int, reason: str) -> None:
        nonlocal active
        if active is not None:
            active.state, active.reason, active.finished_at = "ABORTED", reason, at
            receiver.abort(active.session_id)
            log(at, "ABORT", active.session_id, reason)
            active = None

    for now in range(deadline + 1):
        delivered = packet = payload = damaged = None
        # t is a boundary: exactly source[0:t] is available, never source[t].
        if 0 < now <= len(source) and not muted:
            ring.append(now - 1, source[now - 1])
        if now in mute_schedule:
            muted = bool(mute_schedule[now])
            abort(now, "MUTED" if muted else "UNMUTE_RESET")
            ring.clear(now)
            last_reset_sample = now
            seen_events.clear()
            mute_clear_verified &= all(v == 0 for v in ring.storage)
            # A packet already put on the simulated wire cannot be recalled.
            # It belongs to a now-aborted session and is rejected on late arrival.
            log(now, "MUTE" if muted else "UNMUTE", detail="ring zeroed; capture session cancelled")
        if active is not None and active.state == "STREAMING" and not online(now):
            abort(now, "NETWORK_DISCONNECTED")
        for event in trigger_schedule.get(now, []):
            if muted:
                log(now, "TRIGGER_REJECTED", detail="MUTED")
            elif event.event_id in seen_events:
                log(now, "TRIGGER_IGNORED", detail="DUPLICATE_EVENT")
            elif event.detected_at > now or event.keyword_end > event.detected_at or event.keyword_end < 0:
                log(now, "TRIGGER_REJECTED", detail="INVALID_EVENT_TIME")
            elif now - event.detected_at > scenario.max_trigger_age_samples:
                log(now, "TRIGGER_REJECTED", detail="STALE_EVENT")
            elif event.detected_at < last_reset_sample or event.keyword_end < last_reset_sample:
                log(now, "TRIGGER_REJECTED", detail="PRE_RESET_EVENT")
            elif active is not None:
                seen_events.append(event.event_id)
                log(now, "TRIGGER_IGNORED", active.session_id, "BUSY")
            else:
                seen_events.append(event.event_id)
                start = event.keyword_end - scenario.guard_samples if policy == "buffered" else now
                sid = f"{scenario.scenario_id}:{policy}:{len(sessions) + 1}"
                active = CaptureSession(sid, event.utterance_id, start, now, start)
                sessions.append(active)
                log(now, "ORACLE_TRIGGER", sid, f"requested_start={start}; keyword_end={event.keyword_end}")
                if start < ring.oldest:
                    abort(now, "CAPTURE_START_NOT_RETAINED")
        for utterance in endpoint_schedule.get(now, []):
            if active is not None and active.utterance_id == utterance.utterance_id:
                active.capture_end = now
                log(now, "ORACLE_ENDPOINT", active.session_id, f"capture_end={now}")
        if active is not None and active.state == "REQUESTED" and active.cursor < ring.oldest:
            abort(now, "BUFFER_OVERFLOW_PENDING")
        if (active is not None and active.state == "REQUESTED" and online(now)
                and now >= active.requested_at + scenario.accept_delay_samples):
            # Never clamp a missing requested start to the ring's oldest sample.
            if active.requested_start < ring.oldest:
                abort(now, "CAPTURE_START_NOT_RETAINED")
            else:
                active.state, active.accepted_at = "STREAMING", now
                active.next_send_at = now
                receiver.open(active.session_id, active.requested_start, now)
                log(now, "ACCEPT", active.session_id, f"start={active.requested_start}")
        if flight is not None and now >= flight.deliver_at:
            delivered = flight
            flight = None
            packet = delivered.packet
            if delivered.drop or not online(now):
                log(now, "PACKET_DROPPED", packet.session_id, f"seq={packet.seq}")
            else:
                if delivered.corrupt:
                    damaged = bytes([packet.payload[0] ^ 1]) + packet.payload[1:]
                    packet = Packet(packet.session_id, packet.seq, packet.first_sample_index,
                                    packet.sample_count, damaged, packet.checksum)
                if delivered.reorder:
                    packet = Packet(packet.session_id, packet.seq, packet.first_sample_index + 1,
                                    packet.sample_count, packet.payload, packet.checksum)
                disposition = receiver.receive(packet, now)
                if delivered.duplicate:
                    receiver.receive(packet, now)
                log(now, "PACKET_DELIVERY", packet.session_id, disposition)
                if active is not None and active.session_id == packet.session_id:
                    if disposition in {"ACCEPTED", "DUPLICATE_IGNORED"}:
                        active.cursor = packet.first_sample_index + packet.sample_count
                        active.seq += 1
                    else:
                        abort(now, disposition)
        if active is not None and active.state == "STREAMING":
            # Bytes already copied into the one bounded in-flight packet remain
            # protected even if their old ring locations are overwritten. They
            # are NOT reconstructible after a failed delivery unless still in ring.
            required_start = active.cursor
            if flight is not None and flight.packet.session_id == active.session_id:
                assert flight.packet.first_sample_index == active.cursor
                required_start += flight.packet.sample_count
            required_end = min(ring.end, active.capture_end if active.capture_end is not None else ring.end)
            if required_start < required_end and required_start < ring.oldest:
                abort(now, "BUFFER_OVERFLOW_STREAMING")
        if active is not None and active.state == "STREAMING":
            end = min(ring.end, active.capture_end if active.capture_end is not None else ring.end)
            if active.capture_end is not None and active.cursor == active.capture_end and flight is None:
                receiver.finish(active.session_id, active.capture_end)
                active.state, active.finished_at = "COMPLETE", now
                log(now, "COMPLETE", active.session_id, f"end={active.capture_end}")
                active = None
            elif flight is None and now >= active.next_send_at and active.cursor < end:
                size = (scenario.packet_sizes[attempts % len(scenario.packet_sizes)]
                        if scenario.packet_sizes else scenario.packet_samples)
                count = min(size, end - active.cursor)
                payload = ring.read_bytes(active.cursor, active.cursor + count)
                packet = Packet(active.session_id, active.seq, active.cursor, count, payload, sha(payload))
                attempts += 1
                maximum_packet_bytes = max(maximum_packet_bytes, len(payload))
                wire_samples += count
                assert active.accepted_at is not None and now >= active.accepted_at and not muted
                flight = Flight(packet, now + max(1, scenario.transport_delay_samples),
                                scenario.drop_all or attempts in scenario.drop_attempts,
                                attempts in scenario.duplicate_attempts,
                                attempts in scenario.corrupt_attempts,
                                attempts in scenario.reorder_attempts)
                active.next_send_at = now + scenario.packet_interval_samples
                log(now, "SEND", active.session_id, f"seq={packet.seq}; start={packet.first_sample_index}; count={count}")
        if now % 160 == 0 or now == deadline:
            backlog = max(0, ring.end - active.cursor) if active is not None else 0
            telemetry.append({"at_sample": now, "ring_oldest": ring.oldest,
                              "ring_end": ring.end, "ring_retained_samples": ring.retained,
                              "unacknowledged_backlog_samples": backlog,
                              "active_session": active.session_id if active else "",
                              "muted": muted, "network_online": online(now),
                              "inflight_payload_bytes": len(flight.packet.payload) if flight else 0,
                              "evidence_label": "simulated"})
        if now >= scenario.last_scheduled_sample and active is None and flight is None:
            break
    if active is not None:
        abort(deadline, "SIMULATION_TIMEOUT")
    run = Run(scenario, policy, source, sessions, receiver, events, telemetry, ring,
              maximum_packet_bytes, wire_samples, mute_clear_verified)
    # Every run, including aborts, must preserve all receiver prefixes exactly.
    run.metrics()
    return run
