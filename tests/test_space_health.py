"""Publish health gate: the OLD container mid-swap must not count as success."""
from scripts.space_health import evaluate_stats, wait_for_new_corpus


def _stats(chunks=1000, companies=14, model="Qwen/Qwen3-Embedding-0.6B", dmin=1024, dmax=1024, variants=1):
    return {
        "data": {"filing_chunks": chunks, "companies_with_chunks": companies,
                 "embedding_dim_min": dmin, "embedding_dim_max": dmax,
                 "embedding_dim_variants": variants},
        "config": {"embedding_model": model, "embedding_dim": 1024},
    }


def test_new_corpus_passes():
    assert evaluate_stats(_stats(), 1000, 14)[0] is True


def test_old_container_with_fewer_chunks_fails():
    assert evaluate_stats(_stats(chunks=900), 1000, 14)[0] is False


def test_other_gates_fail():
    for bad in (_stats(model="other"), _stats(dmin=768), _stats(dmax=768),
                _stats(variants=2), _stats(companies=11), _stats(companies=13)):
        assert evaluate_stats(bad, 1000, 14)[0] is False
    assert evaluate_stats({"data": {"error": "x"}}, 1000, 14)[0] is False
    assert evaluate_stats({}, 1000, 14)[0] is False


def test_wait_old_then_new_succeeds_and_never_ready_fails():
    seq = iter([_stats(chunks=900), OSError("down"), _stats()])
    t = [0.0]
    sleep = lambda s: t.__setitem__(0, t[0] + s)  # noqa: E731
    ok = wait_for_new_corpus(lambda: _next(seq),
                             1000, 14, sleep=sleep, clock=lambda: t[0], log=lambda *a: None)
    assert ok is True

    t[0] = 0.0
    calls = []
    def old():
        calls.append(1)
        return _stats(chunks=900)
    assert wait_for_new_corpus(old, 1000, 14, timeout_s=100, sleep=sleep,
                               clock=lambda: t[0], log=lambda *a: None) is False
    assert len(calls) == 5


def _next(it):
    v = next(it)
    if isinstance(v, Exception):
        raise v
    return v


def test_company_floor_gate_alone_fails():
    # counts match exactly, but 11 < MIN_COMPANIES (12)
    assert evaluate_stats(_stats(companies=11), 1000, 11)[0] is False
    assert evaluate_stats(_stats(companies=12), 1000, 12)[0] is True


def test_retryable_failures_do_not_crash_polling():
    import http.client
    seq = iter([["not", "an", "object"], http.client.IncompleteRead(b""), ConnectionResetError(),
                TimeoutError(), None, _stats()])
    t = [0.0]
    sleep = lambda s: t.__setitem__(0, t[0] + s)  # noqa: E731
    assert wait_for_new_corpus(lambda: _next(seq), 1000, 14, sleep=sleep,
                               clock=lambda: t[0], log=lambda *a: None) is True
