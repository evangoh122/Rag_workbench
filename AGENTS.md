# RAG Workbench Development Guide

## Dependency Management

- Python dependencies live in `pyproject.toml`; exact versions are pinned in
  `uv.lock`.
- Use `uv sync` to create or refresh `.venv`, `uv run <command>` to execute in
  it, and `uv lock` after changing dependencies.
- CI and Docker must use `uv sync --locked` (never `pip install`) so a stale
  lock fails the build. Run `uv lock --check` locally to verify that `uv.lock`
  matches `pyproject.toml`.
- Development-only tools (pytest, pytest-asyncio, httpx, and Ruff) are in the
  `dev` dependency group.
- The former `requirements.txt` and `requirements-dev.txt` files are retired.

The frontend lives in the separate `evangoh-frontend` repository. This
repository is backend/API-only.

## CI Parity

The canonical checks are documented in `README.md` and
`.github/workflows/python.yml`:

```bash
uv sync --locked
uv run ruff check api scripts tests main.py run.py
uv run pytest -m "not spark and not lakebase and not databricks" -q
uv lock --check
```

## Known Issues and Operational Notes

### DuckDB Version Mismatch (Resolved 2026-06-18)

- Local DuckDB 1.5.3 database files were incompatible with the Hugging Face
  image when it capped DuckDB below 1.1.0.
- The symptom was `Serialization Error: Failed to deserialize: expected end of
  object, but found field id: 103` when the deployed app loaded the database.
- The obsolete upper cap was removed from `pyproject.toml`, aligning local and
  deployed DuckDB versions.
- `.venv_duck10` is obsolete. Development and deployment use the main `.venv`
  with DuckDB 1.5.3 or newer.

### Section Extraction TOC Bug (Fixed 2026-06-18)

- `_extract_sections_with_labels()` previously matched table-of-contents entries
  first, causing the coverage guard to fall back to `full_text`.
- It now selects the longest match. `scripts/retag_sections.py` repaired
  existing data.
- Test extraction behavior with representative filing data because TOC entries
  resemble section headers but are much shorter.

### Review Queue Behavior

- An empty `review_decisions` table can be expected when all queries route to
  `AUTO` at confidence 0.85 or higher.
- Narrative-heavy queries are more likely to produce `SAMPLED_REVIEW` or
  `ESCALATE` routes.

### Orphaned Reviewer Verdicts

- Some `reviewer_verdicts` rows may reference decision IDs absent from
  `review_decisions`.
- These originate from `/api/chat/feedback`, which uses the message timestamp
  as the decision ID rather than creating a review-queue decision.
