from qiskit import QuantumCircuit
from qiskit_ibm_runtime.fake_provider import FakeManilaV2

from qiskit_loadbalancer.scoring import QueueOnlyScoring, NoiseAwareScoring
from qiskit_loadbalancer.monitor import CalibrationCache


def bell_pair():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


def test_queue_scoring_uses_cache_and_avoids_refetch():
    backend = FakeManilaV2()
    calls = {"n": 0}
    real_status = backend.status

    def counting_status():
        calls["n"] += 1
        return real_status()

    backend.status = counting_status
    cache = CalibrationCache(ttl_seconds=60)
    scorer = QueueOnlyScoring(cache=cache)

    circuit = bell_pair()
    s1 = scorer.score(backend, circuit)
    s2 = scorer.score(backend, circuit)

    assert s1 == s2
    assert calls["n"] == 1  # second call served from cache


def test_noise_scoring_uses_cache_and_avoids_refetch():
    backend = FakeManilaV2()
    calls = {"n": 0}
    real_properties = backend.properties

    def counting_properties():
        calls["n"] += 1
        return real_properties()

    backend.properties = counting_properties
    cache = CalibrationCache(ttl_seconds=60)
    scorer = NoiseAwareScoring(cache=cache)

    circuit = bell_pair()
    s1 = scorer.score(backend, circuit)
    s2 = scorer.score(backend, circuit)

    assert s1 == s2
    assert calls["n"] == 1


def test_cache_invalidate_forces_refetch():
    backend = FakeManilaV2()
    calls = {"n": 0}
    real_status = backend.status

    def counting_status():
        calls["n"] += 1
        return real_status()

    backend.status = counting_status
    cache = CalibrationCache(ttl_seconds=60)
    scorer = QueueOnlyScoring(cache=cache)
    circuit = bell_pair()

    scorer.score(backend, circuit)
    cache.invalidate(backend.name)
    scorer.score(backend, circuit)

    assert calls["n"] == 2
