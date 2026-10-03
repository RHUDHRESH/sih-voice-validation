# Artifact contract · schema version 1.0

The JSON manifests and summary use `schema_version: "1.0"`. Version changes must accompany incompatible field/semantic changes. No formal JSON Schema validator is required; `Scenario.validate`, manifest-parity tests and the independent artifact auditor enforce the implemented contract.

## Units and clock

PCM is mono signed 16-bit little-endian at exactly 16,000 samples/sec. Sample indices are zero-based absolute integers. Every range is half-open `[start,end)`. At event boundary `t`, source samples `[0,t)` have arrived; sample `t` has not. Source acquisition continues while delayed command payload drains, up to the configured finite simulation deadline. Interleaving order in `simulate` is part of version 1.0 semantics: acquire; mute/disconnect/trigger/endpoints; accept; deliver pending packet; enforce retention; send; telemetry.

The minimum packet transit is one source sample even when configured transport delay is zero. Wall runtime is separate `time.perf_counter()` data, labelled host-measured. It is not inference latency, real audio throughput or target utilization.

## Input `config/scenarios.json`

Top level: `schema_version`, `evidence_label`, `evaluation_stage`, `detector`, `endpoint`, `seed`, `sample_format`, `scenarios`.

Each scenario has a unique safe `scenario_id`, description, seed, sample rate, ring/guard/packet/timing settings, oracle `utterances`, oracle `triggers`, mute events, outage intervals, packet-fault attempt indices and `expected` outcomes by policy. Ring/packet sizes and send cadence are positive; packet size cannot exceed ring capacity. Timing delays are nonnegative.

Utterance fields: `utterance_id`, `keyword_end`, `command_start`, `command_end`. Trigger fields: `at` (delivery), `event_id`, `utterance_id`, `keyword_end`, `detected_at`. Trigger age/future inconsistencies are deliberately accepted as test inputs but rejected by the simulated state machine. The oracle endpoint is delivered only when its source time is reached.

Policies: `naive` starts at trigger delivery; `buffered` starts at oracle keyword endpoint minus guard. Both use the same source, ring and network settings.

## `summary.json` / per-run `result.json`

Each run is uniquely keyed by `(scenario_id, policy)` and labelled `simulated`. Key fields:

- `test_status`: `pass`/`fail` for declared expected behavior
- `handoff_status`: last session `complete`/`aborted`, or `rejected` with no valid trigger
- `command_integrity_status`: `pass` only when every utterance was fully delivered in a completed byte-exact session
- `reason`: explicit terminal failure code; empty on success
- `commands`: exact input ground truth, selected session, received range, retained/missing prefix/total samples, byte equality and command-integrity status
- `sessions`: requested/accepted/finished times, requested start, cursor, oracle capture end, state and reason
- ring/packet fields: payload counts only; not total resident memory
- `input_sha256`: full synthetic PCM fixture hash
- `host_runtime_seconds`: separate host-measured simulation duration; includes internal equality checks but not artifact writing

`handoff_status` never overrides the aggregate command-integrity result. An empty receiver cannot retain the onset. A partial prefix in an aborted session remains a failed complete command.

## Raw artifacts

- `fixtures/*.pcm` and WAV: synthetic source including post-command acquisition tail; fixture manifest records hash, length, seed and generated-input provenance
- `events.csv`: exact sample time, event, session ID, details, evidence label
- `telemetry.csv`: snapshots every 160 samples (10 ms), oldest/end ring indices, retained/backlog samples, mute/network state and in-flight payload bytes
- `packets.csv`: exact arrival sample, session ID, seq, first index, sample count, hash, receiver disposition
- `receiver_session_N.pcm` + JSON: accepted contiguous PCM, declared start, received end, optional completed end, session state and hash
- `metrics.csv`: metric name, numerator, denominator, unit, exact estimate, status/reason and evidence label. CI fields are empty with the reason that this is deterministic counting, not sampling a population
- `manifest.json`: UTC host timestamp, source/config/data/lock hashes, interpreter/OS/CPU, seeds, clock assumptions and absent-model explanation
- `tests.json` / `tests.txt`: actual unit/property outcomes and host runtime
- `artifact_audit.json`: independent replay/session/packet counts and verification status

## State and error contract

`REQUESTED → STREAMING → COMPLETE`, or `REQUESTED/STREAMING → ABORTED`. Invalid/stale events create no session. Events whose keyword endpoint or detection precedes the latest mute/unmute reset are rejected as PRE_RESET_EVENT. Duplicate/busy events do not fork an active session. A reconnect creates a fresh session ID.

Representative failure codes: `CAPTURE_START_NOT_RETAINED`, `BUFFER_OVERFLOW_PENDING`, `BUFFER_OVERFLOW_STREAMING`, `NETWORK_DISCONNECTED`, `MUTED`, `SIMULATION_TIMEOUT`, `REJECT_NONCONTIGUOUS`, `REJECT_CHECKSUM_OR_LENGTH`, `REJECT_CONFLICTING_DUPLICATE`, `REJECT_NONCAUSAL_TIMING`. A late old packet gets `REJECT_CLOSED_SESSION`. Exact duplicates get `DUPLICATE_IGNORED` without appending data twice.
