# Repository preparation

This folder is a standalone Git repository prepared for publication. Source, documentation, baseline fixtures/replays, the expanded study configuration/metrics/summary/plots and `raw_evidence.zip` are included. Virtual environments, duplicate local baselines, uncompressed study fixture/run trees and large combined study-viewer bundles are excluded from Git; full detailed working data remains on Desktop.

To audit the published study after cloning, restore the deduplicated raw archive using the supplied script. It recreates the `fixtures/` and `runs/` paths referenced by the saved configuration and fixture manifest. Run:

```sh
python restore_evidence.py results/study_20261003
python -I -S verify_artifacts.py results/study_20261003
```

The GitHub workflow performs baseline software/artifact verification, Node replay-control checks and a reduced study. Remote: `RHUDHRESH/sih-voice-validation`, created with private visibility. Research documentation, computed scientific figures and the codebase are included. App screenshots are excluded. To push subsequent commits:

```sh
git push -u origin main
```

Local commits use the configured Git identity. Publication archives contain only Git-tracked files, excluding app screenshots. All PCM is synthetic; no human speech, microphone recordings or external ASR results are included. See STUDY_REPORT.md for the retention formula and limits.
