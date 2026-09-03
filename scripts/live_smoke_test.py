"""Live smoke test against a real QiskitRuntimeService.

Not part of the pytest suite (it needs real IBM Quantum credentials and
hits the network) — run it manually:

    python scripts/live_smoke_test.py

Exercises the paths the fake-backend test suite can't: auth, real
`backend.status()`/`backend.properties()` responses, an actual job
submission, and what `submit_fn` actually gets back from the Runtime
Sampler (to confirm `BackendRouter.submit`'s return type assumption
holds against a real `RuntimeJob`, not just a stub).

First real run of this script (2026-09-03) caught a genuine bug: the
router was handing `submit_fn` the raw, untranspiled circuit, and IBM
Runtime rejects non-ISA circuits (gates outside the target backend's
basis) since March 2024. `ibm_fez` rejected `h` outright. Fixed in
`router.py` -- `submit()` now transpiles to each candidate's ISA
immediately before calling `submit_fn`. This is exactly the kind of
failure the fake-backend pytest suite couldn't catch, since it never
exercised real target-conformance validation.
"""

from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

from qiskit_loadbalancer import BackendSelector, BackendRouter, HybridScoring, QueueOnlyScoring


def bell_pair() -> QuantumCircuit:
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


def main():
    print("Connecting to QiskitRuntimeService...")
    service = QiskitRuntimeService()

    circuit = bell_pair()

    print("\n--- Ranking with QueueOnlyScoring ---")
    selector = BackendSelector(service=service, strategy=QueueOnlyScoring())
    ranked = selector.rank(circuit)
    for r in ranked:
        print(f"  {r.backend_name}: {r.score:.4f}")

    print("\n--- Ranking with HybridScoring (real calibration data) ---")
    selector = BackendSelector(service=service, strategy=HybridScoring())
    ranked = selector.rank(circuit)
    for r in ranked:
        print(f"  {r.backend_name}: {r.score:.4f}")

    if not ranked:
        print("No viable backends found — nothing to submit to. Stopping here.")
        return

    print(f"\n--- Submitting via BackendRouter (top pick: {ranked[0].backend_name}) ---")
    router = BackendRouter(selector, max_attempts=2)

    def submit_fn(backend, circ):
        sampler = Sampler(mode=backend)
        return sampler.run([circ])

    job = router.submit(circuit, submit_fn)
    print(f"Job submitted: {job.job_id()}")
    print(f"Job return type: {type(job)}")
    print("NOTE: this job was actually submitted to real hardware/simulator queue.")
    print("Check your IBM Quantum dashboard to confirm it appears and completes.")


if __name__ == "__main__":
    main()
