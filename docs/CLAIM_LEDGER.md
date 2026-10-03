# Claim ledger · version 1.0

All positive claims below are scoped to this deterministic, synthetic software model. No formal standards-conformance or industry certification is claimed.

| Claim | Status | Evidence | Limitation |
|---|---|---|---|
| No-pause onset preserved under the declared golden timing | Simulated, checked | golden test; paired raw PCM; packet audit; coverage plot | Oracle keyword endpoint/trigger/end; no acoustic model |
| Naive capture loses 3,200 samples in that same fixture | Simulated, checked | exact 16,000/19,200 source indices; golden test | Not a statistic over real speakers |
| Received data is contiguous and byte-exact from declared start | Simulated, checked | receiver protocol checks; independent PCM/chunk audit | Framing model, not a real transport stack |
| Ring payload storage is fixed at 32,000 bytes in the main configuration | Constructed and tested | fixed array identity/length; ring tests | Excludes all non-ring memory and transient copies |
| The sender has no unlimited audio rescue queue | Constructed and fault-tested | one flight; ring-only reads; overflow and packet-loss tests | Host fixture, receiver and logs intentionally grow as test instruments |
| One extra sample beyond pending-retention capacity aborts | Simulated, checked | capacity boundary/plus-one paired cases | Capacity includes configured guard and delays, not arbitrary network stalls |
| Already copied in-flight PCM can survive ring overwrite | Simulated, checked | two-sample delayed delivery at boundary; dropped-packet counterexample | Only one bounded packet protected; immediate ACK abstraction |
| Capture continues after endpoint while draining | Simulated, checked | post-endpoint slow-drain regression | No real microphone timing or concurrent producer |
| Mute stops new capture/sends and clears retained PCM | Simulated, checked | pending/streaming mute tests, ring-zero checks, event audit | Cannot recall audio already sent; remote archives remain |
| Reconnect does not merge old and new session PCM | Simulated, checked | stale in-flight packet rejected; fresh session exact bytes | No resumption/authentication handshake implementation |
| Real custom wake-phrase accuracy/false activations | Not run | None | Phrase, detector, consented data and held-out protocol required |
| Real speech first-phoneme/ASR preservation | Not run | None | Synthetic PCM does not establish intelligibility or ASR accuracy |
| MCU RAM less than 256 KB / idle CPU less than 10% | Not run; requirement wording unverified | None | Need official constraints and actual firmware/board measurements |
| Power, battery life, production throughput | Not run | None | Need hardware, instruments and representative duty cycles |
| Industry-standard compliance, certification or production readiness | Not claimed | Local quality checks only | Formal applicable standard, assessment scope and audit absent |

## Honest judge wording

“We implemented and reproducibly tested the capture and handoff logic using oracle trigger events. In one declared no-pause fixture, naive capture loses 200 ms while the buffered policy preserves the command exactly. The same tests show where finite retention fails and aborts. We have not yet validated acoustic wake detection, real ASR or embedded resource use.”

## Fairness

Each policy receives the same generated PCM hash, source clock, trigger envelope, ring capacity and network configuration. Only capture-start policy differs. Buffered capture includes a guard and therefore may require more retained history; cases where that added history causes failure remain in the full matrix. No best-seed selection or removal of failure cases is used.
