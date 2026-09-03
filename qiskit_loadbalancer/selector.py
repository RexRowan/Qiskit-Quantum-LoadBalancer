"""Backend selection: score a set of candidate backends and rank them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from qiskit import QuantumCircuit

from .scoring import ScoringStrategy, HybridScoring


@dataclass
class BackendScore:
    """A scored candidate backend."""

    backend_name: str
    backend: object
    score: float


class BackendSelector:
    """Ranks a set of candidate backends for a given circuit.

    Parameters
    ----------
    service:
        A `qiskit_ibm_runtime.QiskitRuntimeService` instance, or any object
        exposing a `.backends()` method returning backend objects. Optional
        if you plan to always pass explicit `backends=` to `rank`/`select`.
    strategy:
        A `ScoringStrategy`. Defaults to `HybridScoring()`.
    """

    def __init__(self, service=None, strategy: Optional[ScoringStrategy] = None):
        self.service = service
        self.strategy = strategy or HybridScoring()

    def _candidate_backends(self, backends: Optional[Sequence] = None) -> Sequence:
        if backends is not None:
            return backends
        if self.service is None:
            raise ValueError(
                "No backends provided and no service configured. Pass "
                "backends=[...] or construct BackendSelector(service=...)."
            )
        return self.service.backends(operational=True, simulator=False)

    def rank(
        self,
        circuit: QuantumCircuit,
        backends: Optional[Sequence] = None,
    ) -> List[BackendScore]:
        """Score and rank all viable candidate backends, best first."""
        candidates = self._candidate_backends(backends)
        scored: List[BackendScore] = []
        for backend in candidates:
            s = self.strategy.score(backend, circuit)
            if s is None:
                continue
            scored.append(BackendScore(backend_name=backend.name, backend=backend, score=s))
        scored.sort(key=lambda bs: bs.score, reverse=True)
        return scored

    def select(
        self,
        circuit: QuantumCircuit,
        backends: Optional[Sequence] = None,
    ):
        """Return the single best backend for `circuit`, or None if none fit."""
        ranked = self.rank(circuit, backends=backends)
        return ranked[0].backend if ranked else None
