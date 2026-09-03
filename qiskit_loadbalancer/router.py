"""Job routing: submit to the best backend, failing over on error."""

from __future__ import annotations

from typing import List, Optional, Sequence

from qiskit import QuantumCircuit

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
    """

    def __init__(self, selector: BackendSelector, max_attempts: int = 3):
        self.selector = selector
        self.max_attempts = max_attempts

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
                return submit_fn(candidate.backend, circuit)
            except Exception as exc:  # noqa: BLE001 - deliberately broad, we retry
                last_error = exc
                continue

        raise RoutingError(attempts=attempts, last_error=last_error)
