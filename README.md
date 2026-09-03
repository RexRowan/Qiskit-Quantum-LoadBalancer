# Qiskit Quantum Load Balancer

Noise- and queue-aware backend selection and routing for IBM Quantum
backends, built on `qiskit-ibm-runtime`.

`QiskitRuntimeService.least_busy()` only looks at queue depth. This
package scores candidate backends per-circuit — factoring in whether the
circuit actually fits, and (optionally) an estimate of expected fidelity
after transpilation — then can route job submission with automatic
failover if a backend errors out.

## Install

```bash
pip install -e .
```

## Quick start

```python
from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_loadbalancer import BackendSelector, HybridScoring

service = QiskitRuntimeService()
selector = BackendSelector(service=service, strategy=HybridScoring())

qc = QuantumCircuit(2, 2)
qc.h(0)
qc.cx(0, 1)
qc.measure([0, 1], [0, 1])

best_backend = selector.select(qc)
```

With automatic failover on submission errors:

```python
from qiskit_ibm_runtime import SamplerV2 as Sampler
from qiskit_loadbalancer import BackendRouter

router = BackendRouter(selector, max_attempts=3)

def submit(backend, circuit):
    sampler = Sampler(mode=backend)
    return sampler.run([circuit])

job = router.submit(qc, submit)
```

## Scoring strategies

- **`QueueOnlyScoring`** — ranks by reported pending-job count. Cheap,
  equivalent in spirit to `least_busy()`.
- **`NoiseAwareScoring`** — transpiles the circuit against each candidate
  backend's real coupling map and basis gates, then estimates fidelity by
  multiplying per-gate and per-readout error rates from `backend.properties()`
  along the transpiled circuit.
- **`HybridScoring`** — weighted sum of the two above (`queue_weight`,
  `noise_weight`, defaults 0.4/0.6).

Any strategy that implements `score(backend, circuit) -> float | None`
can be dropped in; returning `None` excludes a backend (e.g. it doesn't
have enough qubits for the circuit).

`QueueOnlyScoring`, `NoiseAwareScoring`, and `HybridScoring` all accept
an optional `CalibrationCache` (see `monitor.py`) to avoid refetching
`backend.status()`/`backend.properties()` on every call when scoring
many circuits in a short window:

```python
from qiskit_loadbalancer import HybridScoring, CalibrationCache

queue_cache = CalibrationCache(ttl_seconds=30)     # queue depth changes fast
noise_cache = CalibrationCache(ttl_seconds=3600)   # calibration data doesn't
strategy = HybridScoring(queue_cache=queue_cache, noise_cache=noise_cache)
```

## Live smoke test

`scripts/live_smoke_test.py` exercises this against a real
`QiskitRuntimeService` — real auth, real calibration data, an actual job
submission — none of which the fake-backend test suite covers. Run it
manually with your own IBM Quantum credentials configured:

```bash
python scripts/live_smoke_test.py
```

This has **not yet been run against a live service** as part of building
this package — it's provided but unverified. Run it before relying on
this in front of real hardware.

## Known limitations

- **Independent-error assumption.** `NoiseAwareScoring` multiplies gate
  and readout error rates as if they were independent. Real device noise
  is correlated (crosstalk, drift, spatially correlated errors), so this
  systematically overstates fidelity, especially on wider circuits. It's
  a useful *relative* ranking signal, not an absolute fidelity prediction.
- **Transpile cost.** Noise-aware scoring transpiles the circuit against
  every candidate backend on every call. `CalibrationCache` (now wired in)
  avoids refetching `status()`/`properties()`, but transpilation itself
  isn't cached — for large batches of circuits against many backends this
  still gets expensive.
- **Queue score ignores job cost.** `QueueOnlyScoring` counts pending jobs,
  not their size or expected runtime, so it can't tell a queue of five
  quick jobs from a queue of five expensive ones.
- **Hybrid weights are defaults, not tuned.** The 0.4/0.6 split in
  `HybridScoring` is a reasonable starting point, not the result of
  empirical calibration against real turnaround-time or fidelity data.
- **No live-service integration tests.** The pytest suite runs entirely
  against `qiskit_ibm_runtime.fake_provider` backends (no network calls).
  `scripts/live_smoke_test.py` exists for manual real-service checks but
  has not itself been run yet — `BackendRouter`'s failover path is
  verified only against an injected `submit_fn`, not real Runtime API
  error modes (auth failures, rate limits, mid-job backend retirement).
- **Static circuit assumption.** Scoring assumes a fixed circuit width
  known ahead of time. Dynamic circuits with mid-circuit measurement and
  classical feedforward are transpiled and scored the same way, but the
  fidelity estimate doesn't account for any additional overhead specific
  to dynamic execution.

## License

Apache-2.0
