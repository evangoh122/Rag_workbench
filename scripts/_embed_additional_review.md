Here is the review of the script, grouped by severity.

### CRITICAL

- **`_period_from_accession` is incorrect for 10-Q filings.** The function always returns `YYYY-12-31` (year-end). For a 10-Q filed with accession `0000320193-23-000123`, the middle segment `23` indicates 2023, but the period of report should be a quarter-end date (e.g., `2023-03-31`, `2023-06-30`, `2023-09-30`), not `2023-12-31`. This will store incorrect period metadata for all 10-Q filings.

### MAJOR

- **`_normalize_filings` may silently drop filings.** `latest(n)` returns a `Filings` collection. Calling `list(fresult)` on a `Filings` object may not yield individual `Filing` objects as expected; it depends on the `edgar` library's implementation. If it returns a single `Filing` or an iterator of something else, the logic breaks. The `try/except TypeError` is insufficient to catch all misalignment cases.
- **`dedup_conn` is read-only but used for dedup across the entire run.** If the script runs for a long time, new rows inserted by `write_conn` are not visible to `dedup_conn` (read-only connection sees a snapshot). This can cause duplicate inserts for the same `(ticker, accession)` within the same run if the same filing appears in multiple form queries (e.g., a 10-K that is also classified as 20-F). The DELETE before insert mitigates this, but the dedup check is unreliable.
- **`_is_present` uses `dedup_conn` which is never committed/refreshed.** Even if `write_conn` commits, the read-only connection does not see the new data. This means the same filing could be processed twice in the same run if it appears in two form queries.
- **`_filing_path` uses `acc_clean = accession.replace("-", "")` but the `edgar` library may return accession numbers with or without dashes.** If the library returns `0000320193-23-000123`, the path becomes `.../000032019323000123/primary-document.html`. If the library later returns `000032019323000123` (no dashes), the path changes, causing a re-download and potential duplicate processing. The script does not normalize the accession format consistently.

### MINOR

- **`_period_from_accession` assumes the middle segment is a two-digit year.** Accession numbers like `0000320193-99-123456` would produce `1999-12-31`, which is correct, but accession numbers with a four-digit year segment (e.g., `0000320193-2023-123456`) would produce `202023-12-31` (incorrect). The `edgar` library typically uses two-digit years, but this is not guaranteed.
- **`_ensure_schema` is called inside the `if not args.dry_run` block, but `write_conn` is opened before the loop.** If `_ensure_schema` fails (e.g., table creation error), the script will crash without closing `dedup_conn`. The schema creation should be done before entering the ticker loop, and the connection should be closed in a `finally` block.
- **`gc.collect()` is called after each filing, but the script already uses `del`.** This is unnecessary and may degrade performance. Python's garbage collector will handle cleanup naturally.
- **`write_conn.commit()` is called after each filing, but the script also commits implicitly on `close()`.** This is fine but redundant. The commit after each filing is good for crash-safety, but the final commit on close is unnecessary.
- **`--dry-run` still opens a write connection.** The line `write_conn = duckdb.connect(Config.DB_PATH)` is executed even when `args.dry_run` is True, but it is immediately set to `None` in the `else` branch. This is harmless but confusing. The connection should not be opened at all during dry-run.