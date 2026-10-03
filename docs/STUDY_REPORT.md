# Expanded edge voice capture study

Prototype Pioneers · Team 160289 · SIH26172 · 3 October 2026

Buffered capture preserved complete commands when required history remained available. It explicitly aborted when retention was exceeded. Across 250 randomized clean no-pause cases, buffered capture preserved 154 complete commands; naive capture preserved none. Those counts apply to the declared synthetic oracle fixtures, not speech recognition accuracy.

## Experiment design

`study.py` declares all scenarios and expected outcomes before simulation using seed 2617203. Both policies use identical seeded PCM, oracle trigger events, command endpoints and simulated transport conditions. The edge retains a bounded ring and at most one in-flight packet; full source/receiver archives are host evidence instruments.

For the clean sweep, keyword endpoint and command start are sample 8,000 and command endpoint is 24,000, giving a one-second command at 16 kHz. The fast sink uses at most 320 samples per packet and a 16-sample send interval with the minimum one-sample transport delivery step. Flush allowance is 8,000 samples. The sink can drain initial backlog quickly; this assumption is essential to the clean retention formula.

| Group | Scenarios | Paired runs | Design |
|---|---:|---:|---|
| Capacity/delay grid | 240 | 480 | Four rings × two guards × five detector delays × six acceptance delays |
| Exact boundaries | 36 | 72 | Three rings × four detector delays × {boundary−1, boundary, boundary+1} |
| Random clean captures | 250 | 500 | Independently drawn ring, guard, detector delay and acceptance delay |
| Transport/privacy faults | 175 | 350 | Seven fault types × 25 seeded packet/source variations |
| Total | 701 | 1,402 | Full saved expected-behavior and byte/packet audits |

Grid rings are 2,000, 4,000, 8,000 and 16,000 samples; guards are 0 and 800 samples. Detector delays are 0, 400, 1,600, 3,200 and 6,400 samples. Acceptance delays are 0, 400, 1,600, 3,200, 6,400 and 8,000 samples. Divide samples by 16 to obtain milliseconds. Random rings range from 500–16,000 samples, guards from 0–1,600 samples and detector/acceptance delays independently from 0–6,000 samples.

Faults cover one dropped packet, exact duplicate delivery, corruption, incorrect first-sample metadata, persistent loss, mute during streaming and a sink at half the acquisition rate. Fault injection operates inside an independently established feasible initial-retention region. Drop-once and duplicate cases should complete; corruption, wrong indices, persistent loss, mute and sustained slow drain should abort. Expected aborts remain command-integrity failures.

## Analytical acceptance boundary

Let D be detector delay, G the requested guard, A receiver acceptance delay and R ring capacity, in samples. At acceptance, buffered requested history is D+G+A samples old. Under the fast clean sink, valid startup history and a trigger/acceptance before endpoint, complete buffered capture requires:

**D + G + A ≤ R**

Naive capture requires A≤R to hand off its selected interval, but it excludes D command samples at the beginning of a no-pause command. A complete naive handoff can therefore be an incomplete command. The inequality is a clean-case retention contract, not a sufficiency theorem for lossy or slow transport. It does not model detector endpoint error, acoustic errors or concurrency.

All 12 boundary settings passed their predeclared expectations: buffered capture completed at one sample below and exactly on the boundary (24 runs), then aborted at boundary+1 (12 runs).

## Results

| Group | Naive completed handoffs | Naive intact commands | Buffered completed handoffs | Buffered intact commands |
|---|---:|---:|---:|---:|
| Grid, 240 each | 190 | 38 | 139 | 139 |
| Boundary, 36 each | 36 | 9 | 24 | 24 |
| Random, 250 each | 224 | 0 | 154 | 154 |
| Fault, 175 each | 50 | 0 | 50 | 50 |
| Total, 701 each | 500 | 47 | 367 | 367 |

![Detector and acceptance delay versus ring capacity](../results/study_20261003/delay_capacity_heatmap.svg)

The software expectation suite passed for all 1,402 runs. The independent saved-artifact auditor checked 630,511 accepted packets, 1,117 receiver sessions, full fixture hashes, byte-exact receiver prefixes, contiguous chunk ranges and summary counts. This proves consistency of the simulated captures and persisted evidence within the declared model. It does not establish that all handoffs succeeded.

The original 28-scenario baseline remains available in `results/latest`: 56 paired replays and a final suite of 30 Python tests, including randomized captures, serialized-artifact tamper tests and three publication-archive checks. The full study executed the 27-test suite before archive support was added. The baseline golden no-pause fixture loses 3,200 onset samples under naive capture and zero under buffered capture, with all 16,000 command samples preserved byte-for-byte.

## Reproduction and evidence

```powershell
python -I -S run_validation.py
python -I -S study.py --out results/my-study
python -I -S verify_artifacts.py results/my-study
```

No third-party Python package is required. `--quick --trials 2` runs 31 scenarios/62 paired replays for CI smoke verification. Reduced heatmaps shade unexecuted cells grey. The full matrix may take several minutes, especially when auditing hundreds of thousands of packet records.

The published study directory contains the configuration, results, metrics, packet audit, test logs, hashes and heatmap. `raw_evidence.zip` deduplicates identical files into SHA-256 addressed blobs with an `index.json` mapping their original `fixtures/` and `runs/` paths. Run `python restore_evidence.py results/study_20261003` before rerunning `verify_artifacts.py` or opening a study replay. Restoration verifies every blob and refuses to overwrite different evidence. The Desktop working copy already retains the restored raw evidence. Full-study viewer bundles are omitted because this matrix generates a very large combined replay; the baseline viewer is the practical demonstration.

`--summarize-existing` regenerates report/heatmap files only when saved configuration, test status and replay audit count match the requested study. It does not rerun the simulation or independent audit. Hashes are tamper-evidence, not a signature. Timestamps and host runtime vary; PCM, sample indices, events and outcome counts are deterministic for unchanged source and seed. The execution manifest's source snapshot is preserved; later reporting-only changes are documented separately.

## Next real-system gate

Integrate a causal wake detector and endpoint estimator with the chosen microphone and board. Evaluate held-out consented speech including no-pause commands, accents, noise, false activations and endpoint error. Port retention/session/mute rules to the real transport, add delayed/lost acknowledgements and race tests, then measure total RAM, deadline misses, CPU and power on target hardware. The current ring allocation is PCM payload only; it supports no complete application-memory or acoustic accuracy claim.
