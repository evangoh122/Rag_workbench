# RAG Workbench UI/UX Framework

## Design read

Reading this as a dense B2B research workbench for analysts, with a sober evidence-first language, leaning toward the existing React + Tailwind foundation and targeted evolution rather than a new component library.

- `DESIGN_VARIANCE: 4` because repeated workflows should feel predictable.
- `MOTION_INTENSITY: 3` because motion should explain state changes, not decorate analysis.
- `VISUAL_DENSITY: 7` because citations, metrics, tables, and pipeline state must remain visible.

## Product principles

1. Evidence before ornament. Citations, filing periods, retrieval status, and confidence outrank decorative chrome.
2. One primary action per view. Secondary actions use quiet buttons or links.
3. Progressive disclosure. Show the answer and its provenance first; place graph triples, raw traces, and debug details behind explicit disclosure controls.
4. Stable analyst workspace. Preserve routes, navigation labels, form names, and current workflows.
5. Every state is designed. Loading, empty, partial, stale, error, and success states need specific language and visual treatment.

## Visual foundation

Use a single dark graphite theme for this pass. Keep violet as the existing brand accent, but remove blue and indigo substitutes and avoid glow as a default surface treatment.

| Token | Value | Use |
| --- | --- | --- |
| Canvas | `#0A0C10` | App background |
| Surface | `#11141A` | Sidebar, headers, persistent regions |
| Surface raised | `#171B23` | Menus, dialogs, selected regions |
| Surface hover | `#1D222C` | Hover and pressed feedback |
| Text primary | `#F3F5F7` | Headings and primary values |
| Text secondary | `#A8B0BC` | Body copy and labels |
| Text muted | `#747D8B` | Metadata and disabled text |
| Border | `#2A303B` | Standard separators |
| Border subtle | `#1D222B` | Dense row separators |
| Accent foreground | `#A99DF8` | Active navigation, links, icons, and focus; 8.26:1 on canvas and 7.79:1 on surface |
| Accent foreground hover | `#C1B8FA` | Hovered violet text and icons; 10.72:1 on canvas and 10.10:1 on surface |
| Accent fill | `#6D5BD0` | Solid primary CTA and user-message backgrounds; 5.18:1 with white |
| Accent fill hover | `#7563D2` | Hovered solid action backgrounds; 4.70:1 with white |
| Accent wash | `rgba(109,91,208,.14)` | Selected backgrounds only |
| Positive | `#43D19E` | Verified, bullish, successful |
| Negative | `#FF727F` | Failed, bearish, destructive |
| Warning | `#F2B84B` | Partial, stale, needs review |
| Info | `#76A9FA` | Informational state only, never CTA |

Rules:

- Violet is the only brand/action accent across the product. Use the bright foreground tokens for violet text and icons on graphite; use the darker fill tokens only behind white text in solid CTAs and user messages.
- Keep idle control borders graphite. On focus, move the border to the bright violet foreground token with only a restrained 1px halo; do not use a default glow.
- Enabled primary actions use the solid accent fill with white text. Disabled actions remain fully opaque and legible, using a desaturated graphite fill, slate border, and muted label so they cannot be mistaken for an active CTA.
- Green, red, amber, and blue are semantic only and always paired with text or an icon.
- Use solid surfaces and separators by default. Reserve blur for the mobile overlay and modal backdrop.
- Use one radius rule: 12px containers, 8px inputs and buttons, full pills only for compact status chips.
- Use shadows only for floating layers. Content panels rely on borders and spacing.

## Typography and spacing

- Keep a system sans stack for performance; put `Geist` first only if it is self-hosted later.
- Page title: 24px/32px, 650 weight. Section title: 16px/24px, 600. Body: 14px/22px. Metadata: 12px/18px.
- Use the mono stack only for filing IDs, tickers, numeric data, query traces, and code.
- Preserve tabular numerals for all financial values.
- Base spacing unit is 4px. Prefer 8, 12, 16, 24, and 32px. Avoid one-off spacing values.
- Keep readable prose at 68 characters; allow tables and graphs to use the full workspace width.

## App shell

- Sidebar width: 248px desktop, 288px overlay on mobile. Group navigation by workflow, not implementation detail.
- Active navigation uses an accent wash, left indicator, and high-contrast label. Hover alone must not be the only cue.
- Desktop header height: 56px. Keep view title, current company/context, and at most two actions on one row.
- Main content uses a maximum reading width for prose while tables, charts, and graph views can expand.
- Preserve all current route paths and navigation labels in this pass.

## Chat and research workflow

- Make the composer the visual anchor: fixed at the bottom, clear focus ring, concise placeholder, keyboard hint outside the input.
- Replace the decorative six-dot pipeline with a compact labeled stepper that exposes current state and a text alternative.
- Assistant responses should be wider than user prompts. Use a quiet surface for answers and the accent only for the user message or active state.
- Response order: answer, key figures, citations, confidence/review state, then expandable trace and graph evidence.
- Suggested questions should be compact action rows, not equal promotional cards.
- Present Retrieve, Ground, and Verify as one numbered sequence with aligned label and description columns; stack each label above its description on narrow screens rather than splitting the steps into promotional cards.
- Loading should use a response-shaped skeleton plus a plain-language status such as `Retrieving filing sections`.
- Errors remain inline with retry and preserve the original query.

## Data, charts, and review surfaces

- Tables keep clearly separated headers, right-align numeric columns, show units in headers, and provide visible sort direction. Use sticky headers only inside a deliberately bounded vertical scroll region.
- Use zebra striping only when row density requires it. Otherwise use subtle row separators and a stronger hover state.
- Never communicate positive/negative values through color alone. Add signs, labels, or icons.
- Charts use violet for the primary series and neutral gray for comparison. Reserve green/red for gain/loss semantics.
- Review states map consistently: auto accepted = positive, sampled review = warning, escalated = negative, pending = neutral.
- Empty states explain what data is absent and provide the next valid action.

## Interaction and accessibility

- All interactive controls need visible `:focus-visible` treatment using a 2px accent ring with 2px offset.
- Minimum target size is 44x44px on touch devices.
- Buttons use a small 1px downward translation or `scale(.98)` on press.
- Tooltips supplement visible labels; they never carry essential information alone.
- Honor `prefers-reduced-motion`. Limit transitions to 120-180ms for hover/focus and 200-240ms for panels.
- Maintain WCAG AA contrast, keyboard navigation, logical heading order, and announced live status for retrieval progress.

## Focused implementation scope

This is not a full rewrite. The first pass should touch only shared styling and the highest-frequency workflow:

1. Recalibrate tokens and shared primitives in `frontend/src/index.css`.
2. Simplify the shell and navigation hierarchy in `frontend/src/App.tsx` without changing routes or labels.
3. Improve the chat header, pipeline state, empty state, messages, and composer in `frontend/src/views/ChatView.tsx`.
4. Apply the same table and focus rules to the reusable data table if changes remain small.

Do not add a new UI framework, change API behavior, rewrite product copy broadly, or expose any API key to Vite. `XIAOMI_OPENAI_API_KEY`, `MIMO_API_KEY`, and all other provider keys remain server-side environment values.

## Acceptance checks

- One accent color is used for actions and selection throughout the touched surfaces.
- No default purple glow or blur remains on ordinary cards.
- Shell and chat remain usable at 375px, 768px, 1280px, and 1440px.
- Loading, empty, error, disabled, hover, active, and focus-visible states are present.
- Navigation, routes, analytics hooks, API contracts, and input names are unchanged.
- `npm run build` and `npm run lint` pass.
