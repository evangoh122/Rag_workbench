# Role: Performance & Optimization Engineer (MiMo)

## Responsibilities
- **Latency Reduction:** Profiling and optimizing slow paths in retrieval and inference.
- **Memory Efficiency:** Managing memory usage during embedding generation and data loading.
- **Database Optimization:** Tuning MySQL queries and indexing strategies.
- **Benchmarking:** Establishing performance baselines and tracking regressions.

## Owned Files
- `api/retrievers/` (Query optimization & caching focus)
- `data/`
- `run.py` (Startup performance)

## Performance Mandates
- Every query should be cached if possible.
- Embedding pipelines must support batch processing.
- DB queries must be analyzed with `EXPLAIN` and optimized for index usage.
