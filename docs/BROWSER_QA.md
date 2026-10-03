# Local browser smoke verification

3 October 2026 · Windows · Microsoft Edge driven through Playwright CLI · localhost HTTP

The baseline replay loaded 28 recorded scenarios. The golden final result displayed 3,200 missing onset samples for naive capture and a complete command with zero missing onset samples for buffered capture. Selecting `acceptance_capacity_plus_one` and showing the final result displayed explicit buffered `ABORTED` state while naive handoff completed its later selected capture interval. Final command integrity and current replay state remain distinct.

Screenshots are retained in the local Desktop workspace and excluded from repository publication.

This is a desktop rendering/control smoke review, alongside the separate DOM-free replay-control tests. Full accessibility, mobile layouts and cross-browser behavior have not been assessed. An initial missing favicon request was corrected with an explicit empty favicon. The viewer contains no microphone permission or external transmission.
