# Requirement-to-test mapping · version 1.0

Scope: first software-validation milestone, not a complete voice activator.

| ID | Software requirement | Automated evidence | Status/scope |
|---|---|---|---|
| V01 | Equal inputs and conditions for paired policies | golden paired hash check; independent pair audit | Tested |
| V02 | Exact first-command retention under declared golden timing | test_golden_exact_3200_vs_zero_and_paired_pcm | Tested: naive fails onset; buffered passes |
| V03 | Fixed ring capacity, wrap and full/empty handling | RingTests; every offset for capacities 1,2,3,7,31,160,317 | Tested; arbitrary fixed-width counter overflow untested |
| V04 | No silent clamping or overwrite recovery | capacity-plus-one; startup history; excessive detector delay | Tested with explicit aborts |
| V05 | Continued acquisition during delayed drain | test_continuous_acquisition_after_endpoint | Tested |
| V06 | Packet-boundary-independent payload | sizes 1,160,317 and seeded irregular sizes | Tested; this is transport partitioning, not DSP frame parity |
| V07 | Preserve exact ordered receiver prefix on every path | all scenario invariant checks; independent saved-artifact audit | Tested including aborted prefixes |
| V08 | Drop/retry and duplicate handling | dropped packet; all packets lost; duplicate tests | Tested under immediate-ACK transport model |
| V09 | Reject checksum corruption, index gap, seq gap and conflicting duplicate | ReceiverTests; corruption/reordered-metadata scenarios | Tested; arbitrary real transport reordering untested |
| V10 | Reject stale/future/repeated/busy trigger events | trigger tests and per-run event logs | Tested; event cache bounded to eight entries |
| V11 | Disconnect abort and reconnect session isolation | reconnect isolation with a late old packet | Tested |
| V12 | Mute while pending and streaming | pending-mute and midstream-mute tests | Tested; old remote bytes not recalled |
| V13 | Treat first failed command as failed after second succeeds | mute_then_fresh_session; aggregate integrity assertion | Tested |
| V14 | Bounded in-flight preservation without magical retry | in-flight protection + dropped protected packet regression | Tested |
| V15 | Manifest/output provenance and audit integrity | manifest parity; PCM/summary/config tamper tests; source hashes | Tested locally; no signed supply-chain attestation |
| V16 | Side-by-side replay uses real saved outputs | serve_viewer bundle + isolated control tests | Browser rendering status recorded separately in release checklist |
| V17 | A clean offline environment reproduces the suite | python3 -I -S run_validation.py | Tested on disclosed CPython host |
| V18 | Acoustic KWS/VAD and streaming frontend | None | Not run |
| V19 | Real ASR and real speech command preservation | None | Not run |
| V20 | Target RAM, CPU, timing, power | None | Not run |

Seeds: fixture generation 26172; randomized ring/capture coverage 160289. The randomized capture test has 80 trials × two policies. Finite property coverage is not a proof over all inputs.
