import pytest
from qiskit import QuantumCircuit
from qiskit_ibm_runtime.fake_provider import FakeManilaV2, FakeSherbrooke

from qiskit_loadbalancer.selector import BackendSelector
from qiskit_loadbalancer.router import BackendRouter, RoutingError
from qiskit_loadbalancer.scoring import QueueOnlyScoring


def bell_pair():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


def test_rank_excludes_undersized_backends():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    circuit = QuantumCircuit(10)
    ranked = selector.rank(circuit, backends=[FakeManilaV2()])
    assert ranked == []


def test_rank_orders_by_score_descending():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    ranked = selector.rank(bell_pair(), backends=[FakeManilaV2(), FakeSherbrooke()])
    assert len(ranked) == 2
    assert ranked[0].score >= ranked[1].score


def test_select_returns_best_backend():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    best = selector.select(bell_pair(), backends=[FakeManilaV2(), FakeSherbrooke()])
    assert best is not None


def test_select_returns_none_when_no_backend_fits():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    best = selector.select(QuantumCircuit(200), backends=[FakeManilaV2()])
    assert best is None


def test_selector_requires_backends_or_service():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    with pytest.raises(ValueError):
        selector.rank(bell_pair())


def test_router_submits_to_top_ranked_backend():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    router = BackendRouter(selector)
    calls = []

    def submit_fn(backend, circuit):
        calls.append(backend.name)
        return f"submitted to {backend.name}"

    result = router.submit(bell_pair(), submit_fn, backends=[FakeManilaV2(), FakeSherbrooke()])
    assert result.startswith("submitted to")
    assert len(calls) == 1


def test_router_fails_over_on_error():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    router = BackendRouter(selector, max_attempts=2)
    attempted = []

    def flaky_submit_fn(backend, circuit):
        attempted.append(backend.name)
        if len(attempted) == 1:
            raise RuntimeError("simulated backend outage")
        return "ok"

    result = router.submit(bell_pair(), flaky_submit_fn, backends=[FakeManilaV2(), FakeSherbrooke()])
    assert result == "ok"
    assert len(attempted) == 2


def test_router_raises_when_all_attempts_fail():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    router = BackendRouter(selector, max_attempts=2)

    def always_fails(backend, circuit):
        raise RuntimeError("nope")

    with pytest.raises(RoutingError):
        router.submit(bell_pair(), always_fails, backends=[FakeManilaV2(), FakeSherbrooke()])


def test_router_transpiles_to_isa_before_submit():
    # Regression test: submit_fn must receive an ISA-conformant circuit for
    # the *chosen* backend, not the raw circuit. Bell pair uses 'h', which
    # isn't in FakeManilaV2's/FakeSherbrooke's basis gates -- if router.submit
    # stops transpiling, this catches it the same way ibm_fez did in
    # production (IBMInputValueError on submission).
    selector = BackendSelector(strategy=QueueOnlyScoring())
    router = BackendRouter(selector)
    received = {}

    def submit_fn(backend, circuit):
        received["backend"] = backend
        received["circuit"] = circuit
        return "ok"

    router.submit(bell_pair(), submit_fn, backends=[FakeManilaV2(), FakeSherbrooke()])

    backend = received["backend"]
    circuit = received["circuit"]
    allowed = set(backend.target.operation_names)
    used = {instruction.operation.name for instruction in circuit.data}
    assert used <= allowed, f"circuit used {used - allowed}, not in {backend.name}'s ISA"


def test_router_skips_transpile_when_disabled():
    selector = BackendSelector(strategy=QueueOnlyScoring())
    router = BackendRouter(selector, transpile_before_submit=False)
    circuit = bell_pair()
    received = {}

    def submit_fn(backend, circ):
        received["circuit"] = circ
        return "ok"

    router.submit(circuit, submit_fn, backends=[FakeManilaV2()])
    assert received["circuit"] is circuit
