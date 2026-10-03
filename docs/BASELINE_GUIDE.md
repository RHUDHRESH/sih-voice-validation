# SIH26172 · Edge voice handoff validation

Prototype Pioneers · Team 160289 · Initial software milestone · Version 0.1.0

## Expanded study — 3 October 2026

The expanded study covers **701 scenarios and 1,402 paired replays**, with an independent audit of 630,511 accepted packets and 1,117 receiver sessions. All predeclared software expectations pass. Buffered capture preserves 154/250 commands in the seeded random clean cases; naive capture preserves 0/250. Exact retention boundaries and expected failures remain visible.

Read the [study report](STUDY_REPORT.md), [browser verification](BROWSER_QA.md) and [publication guide](GITHUB_READY.md). CSV/JSON evidence and the delay/capacity heatmap are in `results/study_20261003/`. Detailed fixtures and packet/event/PCM records are packaged in `raw_evidence.zip` for GitHub.

Windows: `.\run.ps1 -Python python` runs the baseline. `python -I -S study.py --out results/my-study` runs the full study without third-party imports. Use a fresh output directory. `python -I -S study.py --quick --trials 2 --out results/my-smoke` runs the reduced CI matrix.

**Every audio/transport result here is synthetic and simulated. Trigger events and utterance endpoints are oracles. There is no trained keyword detector, selected wake phrase, microphone integration, ASR call or hardware benchmark.**

## Reproduce in one command

From this directory, using CPython 3.12.14 (the tested version):

    python3 run_validation.py

No package installation or network access is needed. The Python standard library runs the unit/property checks, replays both policies against each declared input, saves raw evidence, independently audits the saved PCM/chunks/counts and generates three SVG plots. Expected-abort tests deliberately retain failed handoff outcomes. A nonzero exit means a software check failed. Do not run with Python `-O`, which disables assertions; the entrypoints reject it.

Strict no-third-party-import reproduction:

    python3 -I -S run_validation.py --out results/clean_reproduction

Results go to `results/latest/` by default. Use a new `--out` directory for a separate experiment; do not mix older output files with a different configuration. The source/config/data hashes and environment are recorded in each manifest. Host durations and timestamps vary; simulated input, events, PCM and outcome counts are deterministic.

## Side-by-side replay

    python3 serve_viewer.py

Open http://127.0.0.1:8765 on the same computer. Choose a scenario, play/pause, scrub the shared sample clock, step to the next lifecycle event or show the final result. Both panels use saved run artifacts, not reimplemented sample calculations or decorative fake results. Final results are labelled separately from the current replay time.

The server binds only to loopback and serves only explicit viewer assets plus a read-only result bundle. It has no microphone permission, credential flow, upload endpoint, external calls or publishing step. `--port 8766` selects another local port. `--results results/another_run` selects another result set. The viewer must be served over HTTP; opening its HTML as a `file://` page will not provide `/api/data`.

## Central result

The checked-in golden fixture is 16 kHz mono signed 16-bit little-endian PCM:

- Keyword endpoint and immediate command onset: sample 16,000
- Command endpoint: sample 32,000
- Oracle detection: sample 19,200, a 200 ms delay
- Receiver acceptance: sample 24,000, another 300 ms later
- PCM ring: 16,000 samples = 32,000 bytes = one second
- Guard: 1,600 samples = 100 ms

Naive capture starts at sample 19,200 and loses the first 3,200 command samples. Buffered capture requests sample 14,400 and delivers all 16,000 command samples byte-for-byte, once and in order. This result tests the application capture policy under an accurate oracle keyword-end estimate. It says nothing about whether a real detector can supply that event or estimate.

At the exact configured acceptance-capacity boundary the capture succeeds. One additional sample of acceptance delay causes explicit failure. Under a slow sink, acquisition keeps advancing after the command endpoint and can overwrite unsent data; the harness aborts rather than freezing the ring or reading from the full source fixture as a hidden rescue buffer.

## Files and commands

- `voice_harness/core.py`: fixed PCM ring, oracle event/state machine, bounded packet and simulated receiver
- `config/scenarios.json`: versioned, checked-in, exploratory manifest; 28 scenarios paired against both policies
- `config/make_scenarios.py`: deterministic manifest generator; tests catch drift from the checked-in JSON
- `tests/`: golden, boundary, fault, property and serialized-evidence tamper tests
- `verify_artifacts.py`: independent saved-artifact audit; imports no simulator
- `voice_harness/plots.py`: plots built from saved config/results/telemetry
- `serve_viewer.py`, `viewer/`: local-only replay viewer
- `docs/CLAIM_LEDGER.md`: permitted claims and unmeasured claims
- `docs/REQUIREMENTS_TO_TESTS.md`: traceability and remaining work
- `docs/SCHEMA.md`: version 1.0 input, result, event and metric contracts
- `docs/RELEASE_CHECKLIST.md`: local release gates and known verification limits
- `requirements.lock`, `.python-version`: no third-party dependencies; tested interpreter

Useful individual checks:

    python3 -m unittest discover -s tests -v
    python3 verify_artifacts.py results/latest
    python3 -m compileall -q voice_harness tests run_validation.py verify_artifacts.py serve_viewer.py
    sh ci_local.sh

`ci_local.sh` is a local check script; it creates no GitHub repository or hosted CI job. If Node.js is available, it also checks JavaScript syntax and the isolated replay-control logic. Those tests are not a substitute for real-browser rendering or accessibility testing.

## What the result states mean

- `test_status=pass`: the declared expected behavior happened, including deliberate abort/rejection
- `handoff_status=complete`: the **last session** delivered its entire declared capture interval
- `command_integrity_status=pass`: every command in the run was completely delivered in a completed, byte-exact session
- `onset_lost_samples`: missing prefix in the selected received command interval; equals the full command length when no command samples were received
- A partial aborted prefix can retain the onset yet fail command integrity. A resumed second command does not erase failure of an earlier muted command
- Confidence intervals are absent by design: these are exact fixture counts, not population accuracy or reliability estimates

## Model and memory boundaries

The logical edge data path owns a fixed `array('h')` PCM ring, scalar state, an eight-entry event-id cache and at most one packet in flight. The packet contains session ID, sequence number, first absolute sample index, sample count, payload and SHA-256. Exact duplicates are ignored; inconsistent or out-of-order metadata is rejected.

The complete synthetic source, receiver PCM archive, scenario schedule, result dictionaries and logs are host test instruments outside that logical edge data path. The sender can read audio only through the retained ring or an already-copied bounded packet. Its source reference is used to feed one sample at a time and for post-run checks, never to reconstruct lost payload.

`ring_pcm_payload_bytes` proves only the ring payload allocation. `maximum_packet_payload_bytes` is the largest individual packet, not peak resident packet memory. Serialization uses a temporary bytearray and a byte copy; delivery and a newly built packet can temporarily coexist. Python object metadata/allocators, interpreter memory, receiver/log storage, OS memory, DMA, drivers, TLS, stacks, model and frontend memory are not included. **No total application-RAM, less-than-256-KB, idle-CPU or power claim is supported.**

## Deliberate simulation limits

1. Synthetic index-pattern PCM is not speech. Values repeat after 65,536 samples; absolute indices, per-packet hashes and exact source-byte comparison disambiguate positions
2. Keyword-end and command-end oracles are explicit test assumptions. There is no trained KWS/VAD, causal frontend, false-activation benchmark, custom-phrase accuracy or real ASR score
3. Acquisition is sample-indexed, single-threaded and unpaced. Concurrency, DMA interrupt races, fixed-width counter rollover and wall-clock audio deadlines are untested
4. The transport is a bounded discrete-event model, not TCP/WebSocket/TLS. The minimum delivery step is one sample. ACKs are immediate when packets reach the receiver; lost/delayed ACKs are not modelled
5. Duplicate packets are injected at delivery. Wrong index and true sequence-gap receiver checks exercise framing rejection, not arbitrary asynchronous real-network reordering
6. Disconnection aborts the old session. A reconnect requires a fresh trigger/session and cannot mix old payload. A pending packet already on the wire cannot be recalled and is rejected after cancellation
7. Mute stops new capture and sends, zeroes retained ring samples and cancels pending application state. Previously sent bytes and receiver archives cannot be erased by local mute
8. The selected one-second ring and guard are experiment settings, not verified organizer requirements or an achieved embedded memory budget
9. Cases are exploratory development tests. They are not a frozen held-out generalization study, a standards certification or production approval
10. Current slide diagrams were not visually reviewed; this implementation was grounded in recovered submission text and the agreed first-milestone specification

## Next real-system gate

Choose the actual wake phrase, target board and microphone; recover existing firmware/model code; obtain consented no-pause recordings and an authorized ASR destination. Then integrate a real causal detector/endpoint estimator, evaluate held-out streams and false alarms, port the buffer contract into the real capture/transport stack, and measure target RAM/CPU/timing/power. Keep those claims separate from this reproducible software milestone.
