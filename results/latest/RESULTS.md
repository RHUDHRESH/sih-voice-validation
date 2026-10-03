# SIH26172: first software-validation results

**Synthetic PCM, oracle triggers and endpointing, simulated transport. No trained KWS, speech recognition or hardware measurement.**

- 30 unit/property test functions: PASS
- 56 paired replay runs across 28 scenarios: expected-behavior status PASS
- Golden fixture: 16,000 command samples; naive onset loss 3,200 samples, buffered onset loss 0 samples. Buffered command-integrity status: pass; received range [14400, 32000).

Passing an expected-abort test is not successful command delivery. The full matrix retains failed handoffs and incomplete commands. The capture result depends on oracle keyword/command endpoints and configured retention; it is not acoustic accuracy.

Acquisition continues through post-command drain. Only bytes already copied into the bounded in-flight packet are protected outside the ring. Loss of that packet cannot magically restore overwritten samples. Receiver acceptance models immediate acknowledgement; ACK loss is not modelled.

See summary.csv/JSON, metrics.csv, manifest.json, tests.txt, fixture_manifest.json and per-run event/packet/PCM artifacts. Plots regenerate from saved summary and telemetry. Host timing is in host_runtime.csv and is not MCU timing or utilization.
