# AF-3 v0.1.2 recovery result

All 15 retained raw manifests verified on 2026-09-06. All 15 records are incomplete with provider exit 1. Their retained server error states that GPT-6 Astra requires a newer Codex version. No agent completion or completed-turn usage was found in the inspected error stream. The remaining 27 planned units have no raw bundle. This cohort is stopped, not completed or silently excluded. Its manifest index is af-3-v0.1.2-recovery-manifests.sha256.

Successor v0.1.3 uses isolated CLI 0.153.4. Prior records and protocol bytes remain unchanged. The current collector stops on the first incomplete unit and reports retained failures when resuming; it does not reinterpret already-sealed failures as successes.

Historical provider manifests describe earlier source revisions. The v0.1.3 collector manifest separately identifies the new implementation.
