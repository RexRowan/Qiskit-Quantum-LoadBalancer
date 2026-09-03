# Changelog

## 0.1.0 — 2026-09-03

Initial release.

- `QueueOnlyScoring`, `NoiseAwareScoring`, `HybridScoring` backend scoring
  strategies.
- `BackendSelector` for ranking candidate backends per-circuit.
- `BackendRouter` for job submission with automatic ISA transpilation and
  failover across ranked backends.
- `CalibrationCache` for avoiding redundant `status()`/`properties()` calls
  when scoring many circuits in a short window.
- Fidelity-estimate regression test against Aer noise-model simulation
  (`tests/test_fidelity_validation.py`, optional `qiskit-aer` extra).
- Manual live-service smoke test script (`scripts/live_smoke_test.py`),
  run twice against a real `QiskitRuntimeService`: first run caught a
  non-ISA circuit submission bug (fixed in `BackendRouter`), second run
  confirmed the fix end-to-end on `ibm_fez`.
