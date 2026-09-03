"""Validate NoiseAwareScoring's fidelity estimate against noise-model simulation.

IMPORTANT SCOPE NOTE: this validates the analytic independent-error
approximation against a Qiskit Aer noise-model *simulation built from the
same calibration data* NoiseAwareScoring reads (via `AerSimulator.from_backend`).
It is a self-consistency check of the math, not validation against real
hardware. Aer's noise model (thermal relaxation + depolarizing channels per
gate) does not capture crosstalk, calibration drift, or non-Markovian
effects a real device has. Agreement here shows the analytic estimate is a
reasonable approximation *of the calibration-data noise model itself* — it
says nothing about whether that noise model matches a real backend on any
given day. Real-hardware validation still requires `live_smoke_test.py`
(or a dedicated hardware-comparison run) against actual device results.

Run:
    python scripts/validate_fidelity_estimate.py
"""

from __future__ import annotations

import math

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeManilaV2, FakeSherbrooke

from qiskit_loadbalancer.scoring import NoiseAwareScoring

SHOTS = 20000


def bell_pair() -> QuantumCircuit:
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


def ghz(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n, n)
    qc.h(0)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    qc.measure(range(n), range(n))
    return qc


def hellinger_fidelity(p: dict, q: dict) -> float:
    keys = set(p) | set(q)
    s = sum(math.sqrt(p.get(k, 0.0) * q.get(k, 0.0)) for k in keys)
    return s * s


def counts_to_probs(counts: dict, shots: int) -> dict:
    return {k: v / shots for k, v in counts.items()}


def evaluate(circuit: QuantumCircuit, backend, label: str):
    scorer = NoiseAwareScoring()
    predicted = scorer.score(backend, circuit)

    transpiled = transpile(circuit, backend=backend, optimization_level=1)

    ideal_sim = AerSimulator()
    ideal_counts = ideal_sim.run(transpiled, shots=SHOTS).result().get_counts()
    ideal_probs = counts_to_probs(ideal_counts, SHOTS)

    noisy_sim = AerSimulator.from_backend(backend)
    noisy_counts = noisy_sim.run(transpiled, shots=SHOTS).result().get_counts()
    noisy_probs = counts_to_probs(noisy_counts, SHOTS)

    empirical = hellinger_fidelity(ideal_probs, noisy_probs)

    print(f"{label:30s} predicted={predicted:.4f}  empirical={empirical:.4f}  "
          f"diff={predicted - empirical:+.4f}")


def main():
    cases = [
        (bell_pair(), FakeManilaV2(), "bell_pair / Manila"),
        (bell_pair(), FakeSherbrooke(), "bell_pair / Sherbrooke"),
        (ghz(3), FakeManilaV2(), "ghz3 / Manila"),
        (ghz(5), FakeSherbrooke(), "ghz5 / Sherbrooke"),
        (ghz(4), FakeManilaV2(), "ghz4 / Manila"),
    ]
    print(f"{'case':30s} {'predicted':>10s}  {'empirical':>10s}  {'diff':>7s}")
    for circuit, backend, label in cases:
        evaluate(circuit, backend, label)


if __name__ == "__main__":
    main()
