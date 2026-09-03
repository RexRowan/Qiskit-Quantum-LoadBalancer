"""Job routing: submit to the best backend, failing over on error."""

from __future__ import annotations

from typing import List, Optional, Sequence

from qiskit import QuantumCircuit, transpile

from .selector import BackendSelector


class RoutingError(RuntimeError):
    """Raised when a circuit could not be submitted to any candidate backend."""

    def __init__(self, attempts: List[str], last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"All {len(attempts)} candidate backend(s) failed: {attempts}. "
            f"Last error: {last_error!r}"
        )


class BackendRouter:
    """Submits a job to the best-ranked backend, retrying the next-best on failure.

    `submit_fn` receives `(backend, circuit)` and must return whatever the
    caller wants back (e.g. a `RuntimeJob`, or the result of `sampler.run`).
    Keeping submission itself pluggable avoids hard-coding a specific
    Runtime primitive (Sampler vs Estimator) into the router.

    IBM Runtime primitives require ISA circuits -- the exact basis gates and
    coupling map of the target backend -- since March 2024. Which backend
    ends up being tried isn't known until rank time, so `submit()` transpiles
    the circuit to each candidate's ISA immediately before calling
    `submit_fn`, rather than leaving that to the caller (who can't know the
    target ahead of time either). Set `transpile_before_submit=False` if you
    already have per-backend ISA circuits and want to hand them off yourself.
    """

    def __init__(
        self,
        selector: BackendSelector,
        max_attempts: int = 3,
        transpile_before_submit: bool = True,
        optimization_level: int = 1,
    ):
        self.selector = selector
        self.max_attempts = max_attempts
        self.transpile_before_submit = transpile_before_submit
        self.optimization_level = optimization_level

    def submit(
        self,
        circuit: QuantumCircuit,
        submit_fn,
        backends: Optional[Sequence] = None,
    ):
        ranked = self.selector.rank(circuit, backends=backends)
        if not ranked:
            raise RoutingError(attempts=[], last_error=ValueError("no viable backends"))

        attempts: List[str] = []
        last_error: Optional[Exception] = None
        for candidate in ranked[: self.max_attempts]:
            attempts.append(candidate.backend_name)
            try:
                if self.transpile_before_submit:
                    isa_circuit = transpile(
                        circuit,
                        backend=candidate.backend,
                        optimization_level=self.optimization_level,
                    )
                else:
                    isa_circuit = circuit
                return submit_fn(candidate.backend, isa_circuit)
            except Exception as exc:  # noqa: BLE001 - deliberately broad, we retry
                last_error = exc
                continue

        raise RoutingError(attempts=attempts, last_error=last_error)
