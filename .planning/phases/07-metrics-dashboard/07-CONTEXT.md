# Phase 7: Metrics Dashboard - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

A developer-facing metrics dashboard that surfaces pipeline health (rolling human-agreement rate, routing distribution, escalation rate, unrecognized-concept count) so the AUTO tier can be certified for production use. This is a read-only display layer — no decisions, no mutations, no review workflow (that's Phase 8). The dashboard wires `eval_metrics.py` dataclasses to a new FastAPI endpoint and renders them in a new React view following the approved UI-SPEC.

</domain>

<decisions>
## Implementation Decisions

### Review Data Persistence
- **D-01:** Review decisions are stored in a **SQLite table** (`review_decisions`). The existing `api/db/database.py` SQLAlchemy setup is the pattern to follow — add a `ReviewDecision` model alongside existing models. Schema must capture at minimum: `decision_id`, `route` (AUTO/SAMPLED_REVIEW/ESCALATE), `human_agreed` (bool), `reviewed_at` (timestamp), `window_tag` (optional grouping key).
- **D-02:** The SQLite database is **seeded with synthetic review data** (≥ 50 records) so the dashboard renders non-trivial metrics during development. Seed data should cover AUTO-tier decisions with a mix of agreed/disagreed outcomes, giving an agreement rate in the 90–97% range (deliberately spanning the 95% certification threshold) plus a realistic routing distribution and a small number of unrecognized-concept events.

### Claude's Discretion
- **App navigation:** Use a **view-toggle pattern** (not react-router). Phase 7 adds one new view (Dashboard); Phase 8 will add another (Review Queue). Extend the existing sidebar with navigation links that toggle a `view` state variable in the root component, mirroring how `mode` toggles SQL/RAG. React-router is overkill for a 2-view developer tool and would require restructuring `main.tsx` and `App.tsx`.
- **Rolling window definition:** Window = **last 500 decisions** (count-based, matching the UI-SPEC example `window_size: 500`). Expose as a module-level constant in the metrics service or a config env var (`METRICS_WINDOW_SIZE`, default 500). The endpoint always returns `window_size` in the response body per the UI-SPEC shape.
- **Test coverage:** Backend API unit tests only — test the `GET /api/metrics/dashboard` endpoint for: (a) happy path with seeded data, (b) empty-table response (all nulls). No frontend component tests — this is an internal developer tool with low polish requirements per the UI-SPEC accessibility minimums note.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### UI Design Contract (primary spec for Phase 7)
- `.planning/phases/07-metrics-dashboard/07-UI-SPEC.md` — Approved design contract: 5 components (CertificationBanner, MetricCard, RoutingDistributionBar, DashboardHeader, Dashboard), color tokens, spacing, typography, API response shape, interaction contract, copywriting contract, accessibility minimums. ALL visual decisions are locked here — do not deviate.

### Backend — Existing Metrics Layer
- `api/services/eval_metrics.py` — AgreementMetrics, RoutingMetrics, ValidationMetrics dataclasses. The `/api/metrics/dashboard` endpoint computes from these; do not duplicate logic.
- `api/services/calibrator.py` — PRODUCTION_AGREEMENT_BAR = 0.95 is the certification threshold (mirrors eval_metrics.py). This constant drives the CertificationBanner state.

### Backend — FastAPI Wiring Pattern
- `api/main.py` — App entry point; the new `metrics` router MUST be registered here with `app.include_router(metrics.router)`.
- `api/routes/chat.py` — Canonical pattern for new route modules: `APIRouter(prefix="/api/...", tags=["..."])`, thin handlers that call service layer, `HTTPException(status_code=500)` on service failure.

### Database — SQLite Setup Pattern
- `api/db/database.py` — SQLAlchemy engine/session setup. New `ReviewDecision` model and `review_decisions` table follow this pattern. Seeding script also uses this session.

### Frontend — Existing Patterns
- `frontend/src/App.tsx` — View-toggle pattern (mode state, sidebar nav buttons with active class). Dashboard extension follows this exact pattern.
- `frontend/src/App.css` — CSS variables (--bg-color, --sidebar-color, --card-color, --border-color, --text-primary, --text-secondary, --accent-color). Dashboard components MUST use these variables — no hardcoded hex values except the new semantic tokens declared in UI-SPEC (routing-mid: #6366f1, destructive: #ef4444, amber: #f59e0b).

### Requirements
- `.planning/REQUIREMENTS.md` §Metrics Dashboard — REQ-MD-01 (rolling agreement rate), REQ-MD-02 (escalation rate, routing distribution, unrecognized-concept count), REQ-MD-03 (no production promotion until >95%).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lucide-react` icons: Already installed (^1.17.0). UI-SPEC calls for CheckCircle, XCircle, Clock, AlertTriangle, RefreshCcw — all available without adding packages.
- CSS variable system in `App.css`: 7 root variables fully cover the dashboard's color needs (plus 3 new semantic extensions from UI-SPEC).
- `eval_metrics.py` dataclasses: `AgreementMetrics.agreement_rate`, `AgreementMetrics.meets_production_bar`, `RoutingMetrics.escalation_rate`, `RoutingMetrics.auto_rate`, `RoutingMetrics.sampled_review_rate` — all computed properties, no new math needed.

### Established Patterns
- **Sidebar nav toggle**: `App.tsx` uses `mode` state + `className={mode-btn ${mode === 'x' ? 'active' : ''}}` pattern. Dashboard navigation follows this exactly with a `view` state.
- **FastAPI router**: Each route file creates an `APIRouter`, registers handlers, and is mounted in `main.py`. New `api/routes/metrics.py` follows this pattern.
- **SQLAlchemy session**: `api/db/database.py` provides session factory. New model and queries use same `SessionLocal` pattern.

### Integration Points
- New file: `api/routes/metrics.py` — `GET /api/metrics/dashboard` handler
- `api/main.py`: +1 line `app.include_router(metrics.router)`
- New file: `api/models/review_decision.py` — SQLAlchemy `ReviewDecision` model (or add to existing models file)
- New migration/seeding: script to create `review_decisions` table and insert seed data
- `frontend/src/App.tsx`: Add `view` state, Dashboard nav link in sidebar, conditional rendering of `<Dashboard />` vs existing chat UI
- New files: `frontend/src/components/Dashboard.tsx`, `CertificationBanner.tsx`, `MetricCard.tsx`, `RoutingDistributionBar.tsx`, `DashboardHeader.tsx`

</code_context>

<specifics>
## Specific Ideas

- **Implementor is Gemini** — CONTEXT.md and UI-SPEC.md are the primary handoff artifacts. Plans must be self-contained enough for Gemini to execute without further clarification from Claude.
- **Certification threshold is 95%** — hardwired in both `eval_metrics.PRODUCTION_AGREEMENT_BAR` and `calibrator.PRODUCTION_AGREEMENT_BAR`. The CertificationBanner compares `agreement.agreement_rate >= 0.95` and the UI-SPEC copywriting contract has the exact banner text — copy verbatim.
- **Seed data agreement rate should span the threshold** — include some seeds where rate < 95% and some where rate ≥ 95% so both CertificationBanner states are testable during development.
- **The `/api/metrics/dashboard` response shape is locked** in the UI-SPEC API Contract section — do not deviate. All fields may be null; frontend must null-guard every field.

</specifics>

<deferred>
## Deferred Ideas

- **Real review-decision writes from the review queue** — Phase 8 owns the HITL loop. Phase 7 only reads from (and seeds) the `review_decisions` table. Phase 8 will add the write path (reviewer agree/disagree logging).
- **WebSocket / real-time updates** — Dashboard polls every 60 seconds per the UI-SPEC interaction contract. Live streaming is out of scope.
- **Export to CSV/PDF** — Read-only display only. No export in Phase 7.
- **Review Queue nav link in sidebar** — UI-SPEC notes "(Phase 8 adds: 'Review Queue' link)". Phase 7 only adds the Dashboard link.

</deferred>

---

*Phase: 07-metrics-dashboard*
*Context gathered: 2026-06-08*
