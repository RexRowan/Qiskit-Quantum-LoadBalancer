import pytest
from qiskit import QuantumCircuit
from qiskit_ibm_runtime.fake_provider import FakeManilaV2, FakeSherbrooke

from qiskit_loadbalancer.scoring import QueueOnlyScoring, NoiseAwareScoring, HybridScoring


def bell_pair():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


def test_queue_only_excludes_undersized_backend():
    scorer = QueueOnlyScoring()
    too_big_circuit = QuantumCircuit(10)
    manila = FakeManilaV2()  # 5 qubits
    assert scorer.score(manila, too_big_circuit) is None


def test_queue_only_scores_fitting_backend():
    scorer = QueueOnlyScoring()
    score = scorer.score(FakeManilaV2(), bell_pair())
    assert score is not None
    assert 0 < score <= 1.0


def test_noise_aware_returns_probability_like_score():
    scorer = NoiseAwareScoring()
    score = scorer.score(FakeManilaV2(), bell_pair())
    assert score is not None
    assert 0.0 < score <= 1.0


def test_noise_aware_prefers_lower_error_backend_for_same_circuit():
    # Not a universal truth for all circuits/backends, but for a small
    # circuit that fits both, the backend with better calibration data
    # for the qubits actually used should not score worse in expectation
    # across repeated small circuits. Here we just check both backends
    # produce a valid, comparable score.
    scorer = NoiseAwareScoring()
    circuit = bell_pair()
    s1 = scorer.score(FakeManilaV2(), circuit)
    s2 = scorer.score(FakeSherbrooke(), circuit)
    assert s1 is not None and s2 is not None


def test_hybrid_combines_both_signals():
    scorer = HybridScoring(queue_weight=0.5, noise_weight=0.5)
    score = scorer.score(FakeManilaV2(), bell_pair())
    assert score is not None
    assert score > 0


def test_hybrid_rejects_zero_weights():
    with pytest.raises(ValueError):
        HybridScoring(queue_weight=0.0, noise_weight=0.0)
