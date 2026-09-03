"""Pluggable scoring strategies for ranking IBM Quantum backends.

Each strategy implements `score(backend, circuit) -> float | None`.
Higher scores are better. Returning `None` means the backend is not a
viable candidate for the given circuit (e.g. not enough qubits) and it
will be excluded by `BackendSelector`.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Optional

from qiskit import QuantumCircuit
from qiskit import transpile

from .monitor import CalibrationCache


class ScoringStrategy(ABC):
    """Base class for backend scoring strategies."""

    @abstractmethod
    def score(self, backend, circuit: QuantumCircuit) -> Optional[float]:
        """Return a score for running `circuit` on `backend`, or None if unfit."""
        raise NotImplementedError

    @staticmethod
    def _fits(backend, circuit: QuantumCircuit) -> bool:
        num_qubits = getattr(backend, "num_qubits", None)
        if num_qubits is None:
            config = backend.configuration()
            num_qubits = config.num_qubits
        return num_qubits >= circuit.num_qubits


class QueueOnlyScoring(ScoringStrategy):
    """Rank purely by reported queue depth (fewer pending jobs is better).

    This mirrors `QiskitRuntimeService.least_busy()` but is expressed as
    a strategy so it can be combined with others in `HybridScoring`.

    `backend.status()` is a network call. Pass a `CalibrationCache` if you're
    scoring many circuits in a short window and want to avoid refetching
    queue depth for the same backend on every call.
    """

    def __init__(self, cache: Optional[CalibrationCache] = None):
        self.cache = cache

    def score(self, backend, circuit: QuantumCircuit) -> Optional[float]:
        if not self._fits(backend, circuit):
            return None
        if self.cache is not None:
            status = self.cache.get_or_fetch(backend.name, "status", backend.status)
        else:
            status = backend.status()
        pending = status.pending_jobs
        # Higher score for fewer pending jobs; bounded in (0, 1].
        return 1.0 / (1.0 + pending)


class NoiseAwareScoring(ScoringStrategy):
    """Rank by estimated circuit fidelity after transpiling to this backend.

    Transpiles `circuit` against `backend`'s actual coupling map and basis
    gates, then multiplies per-gate and per-readout error rates (pulled
    from `backend.properties()`) along the transpiled circuit to estimate
    an overall success probability. This is a first-order estimate: it
    treats errors as independent, which overstates fidelity for circuits
    with strong error correlation, but is far more circuit-specific than
    an aggregate "backend quality" score.

    `backend.properties()` is a network call. Pass a `CalibrationCache` if
    you're scoring many circuits in a short window and want to avoid
    refetching calibration data for the same backend on every call —
    calibration data changes far more slowly than queue depth, so a longer
    TTL than `QueueOnlyScoring`'s is usually appropriate.
    """

    def __init__(self, optimization_level: int = 1, cache: Optional[CalibrationCache] = None):
        self.optimization_level = optimization_level
        self.cache = cache

    def score(self, backend, circuit: QuantumCircuit) -> Optional[float]:
        if not self._fits(backend, circuit):
            return None

        if self.cache is not None:
            properties = self.cache.get_or_fetch(backend.name, "properties", backend.properties)
        else:
            properties = backend.properties()
        if properties is None:
            # Simulators / fake backends without calibration data: treat
            # as noiseless so they still rank, just not on this axis.
            return 1.0

        try:
            transpiled = transpile(
                circuit, backend=backend, optimization_level=self.optimization_level
            )
        except Exception:
            return None

        log_fidelity = 0.0
        for instruction in transpiled.data:
            op = instruction.operation
            qubit_indices = [transpiled.find_bit(q).index for q in instruction.qubits]
            if op.name in ("barrier", "delay", "id"):
                continue
            if op.name == "measure":
                for q in qubit_indices:
                    try:
                        err = properties.readout_error(q)
                    except Exception:
                        err = 0.0
                    log_fidelity += math.log(max(1.0 - err, 1e-9))
                continue
            try:
                err = properties.gate_error(op.name, qubit_indices)
            except Exception:
                err = 0.0
            log_fidelity += math.log(max(1.0 - err, 1e-9))

        return math.exp(log_fidelity)


class HybridScoring(ScoringStrategy):
    """Weighted combination of queue pressure and estimated fidelity.

    Both component scores are normalized to comparable ranges before
    combining, so `queue_weight` and `noise_weight` behave as intuitive
    relative priorities rather than needing manual rescaling.

    Pass `queue_cache`/`noise_cache` to avoid refetching `status()`/
    `properties()` per backend on every call — separate caches because
    queue depth and calibration data churn at very different rates (a
    short TTL, e.g. 30s, for queue; a much longer one, e.g. an hour or
    more, for calibration data).
    """

    def __init__(
        self,
        queue_weight: float = 0.4,
        noise_weight: float = 0.6,
        queue_cache: Optional[CalibrationCache] = None,
        noise_cache: Optional[CalibrationCache] = None,
    ):
        if queue_weight < 0 or noise_weight < 0:
            raise ValueError("weights must be non-negative")
        if queue_weight + noise_weight == 0:
            raise ValueError("at least one weight must be positive")
        self.queue_weight = queue_weight
        self.noise_weight = noise_weight
        self._queue_scorer = QueueOnlyScoring(cache=queue_cache)
        self._noise_scorer = NoiseAwareScoring(cache=noise_cache)

    def score(self, backend, circuit: QuantumCircuit) -> Optional[float]:
        queue_score = self._queue_scorer.score(backend, circuit)
        if queue_score is None:
            return None
        noise_score = self._noise_scorer.score(backend, circuit)
        if noise_score is None:
            return None
        return self.queue_weight * queue_score + self.noise_weight * noise_score
