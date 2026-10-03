# Local release checklist · 0.1.0

This is a professional software-validation milestone, not certification, production approval or proof of compliance with a named industry standard.

## Reproducibility gates

- [x] No third-party Python packages, network downloads or paid APIs required
- [x] Tested interpreter recorded: CPython 3.12.14; other Python versions not verified
- [x] Versioned schema/config, seeds, source/config/data/lock hashes and host environment recorded
- [x] Paired policies receive identical input PCM and timing
- [x] Golden/boundary/fault/property tests run and preserve expected failure cases
- [x] Independent saved-artifact audit checks configuration-bound truth, exact PCM/chunk continuity, pair identity and result/summary agreement
- [x] Evidence tamper tests reject altered ground truth, changed PCM, duplicate run keys and inconsistent per-run summaries
- [x] Host timing separated from source sample time and hardware resource claims
- [x] Requirements-to-tests mapping and honest claim ledger included
- [x] Locally generated PCM contains no human recordings or external-data licence dependency
- [x] No GitHub publishing, external speech upload, hardware operation or public hosting performed by this package

## Replay viewer gates

- [x] Minimal local server, loopback binding, explicit route allowlist, no write/upload endpoint
- [x] Side-by-side panels use saved computed artifacts for the same selected scenario
- [x] Separate current replay state from final recorded outcome
- [x] Play/pause, speed, restart, event step, scrub and final-result controls implemented
- [x] Synthetic/oracle/no-hardware labels visible in page content and result data
- [x] Isolated JavaScript control-logic checks cover golden, overflow and multi-command recovery
- [x] Local Microsoft Edge desktop smoke review of golden results, scenario changes and explicit boundary failure; see BROWSER_QA.md
- [ ] Full mobile layout, cross-browser and accessibility QA remain unmeasured
- [ ] Real microphone capture, detector inference, ASR, transport interoperability and embedded deployment are not implemented/tested

## Before presenting to judges

1. Run `sh ci_local.sh` in a fresh extracted directory and preserve the results/manifest
2. Open the local viewer on the same computer; check desktop and phone-sized layout, keyboard focus and playback controls
3. Demonstrate golden no-pause, capacity-plus-one failure, post-endpoint slow drain and mute/reconnect cases
4. Say “oracle-triggered software simulation” before displaying the favorable result
5. Do not claim embedded RAM, CPU, energy, acoustic accuracy, real ASR or standards compliance from these artifacts
6. Keep the recorded failures in the evidence package; changing parameters is a new exploratory run
7. Freeze real-model/hardware acceptance targets before the later held-out evaluation

## Change control

Changes to the buffer, protocol, metrics, manifest or viewer require affected tests plus a full clean rerun. Source-tree hashing excludes generated `results`, Python caches and local `.venv`/`venv` folders. Keep a new result directory per changed configuration; the current output is not a cryptographically signed release or supply-chain attestation.
