import type { CoachStep } from './CoachMarks';

// Versioned keys so a materially-changed tour can re-show to returning users.
// Bumped to v2 when the landing tour grew the deck + contact steps and the chat
// tour's navigation step was rewritten against the real nav groups.
export const CHAT_TOUR_KEY = 'rw_tour_chat_v2';
export const LANDING_TOUR_KEY = 'rw_tour_landing_v2';
export const OVERVIEW_TOUR_KEY = 'rw_tour_overview_v1';
export const HAZEWATCH_TOUR_KEY = 'rw_tour_hazewatch_v1';

/** Guided tour for the RAG Workbench overview page (/projects/rag-workbench). */
export const OVERVIEW_TOUR: CoachStep[] = [
  {
    title: 'RAG Workbench — the overview',
    body: 'What this project is: the business case, the approach to auditable answers, and how to jump into the live app. Skip anytime.',
    placement: 'auto',
  },
  {
    selector: '[data-tour="launch"]',
    title: 'Launch the live app',
    body: 'Open the working demo to question SEC filings yourself and see the full audit trail behind each answer.',
  },
  {
    selector: '[data-tour="methodology"]',
    title: 'Prefer the details first?',
    body: 'Read the technical methodology — how retrieval, XBRL grounding, and verification fit together — before diving in.',
  },
  {
    selector: '[data-tour="business-case"]',
    title: 'Why it matters',
    body: 'The section that states the problem plainly: what breaks when a confident answer cannot show its evidence, and why regulated teams need the audit trail before the speed.',
  },
];

/** Guided tour for the /rag workbench (runs on the empty chat state). */
export const CHAT_TOUR: CoachStep[] = [
  {
    title: 'Welcome to RAG Workbench',
    body: 'A quick 5-step tour of how to question SEC filings and inspect the evidence behind every answer. You can skip anytime.',
    placement: 'auto',
  },
  {
    selector: '[data-tour="nav"]',
    title: 'Navigate the workbench',
    body: 'Two groups. For Users: the coverage list, chat, pipeline traceability and the methodology. Audit & Diagnostics: the knowledge graph, audit log, metrics, system overview, results and the answer study. On mobile, open this with the menu button.',
  },
  {
    selector: '[data-tour="composer"]',
    title: 'Ask in plain English',
    body: 'Type a question about a covered company’s SEC filing — e.g. revenue, margins, or risks — and the system retrieves, grounds, and verifies the answer.',
  },
  {
    selector: '[data-tour="suggestions"]',
    title: 'Or start from an example',
    body: 'Not sure where to begin? Tap a sample question to see a full audited answer.',
  },
  {
    selector: '[data-tour="pipeline"]',
    title: 'Watch the audit pipeline',
    body: 'Each answer flows through retrieval → extraction → math → verification. Every step is traceable, so you can inspect the evidence instead of trusting a black box.',
  },
];

/** Guided tour for the portfolio landing page. */
export const LANDING_TOUR: CoachStep[] = [
  {
    title: 'Welcome — the 30-second version',
    body: 'Three projects sit on this page, one of them a live app. This tour points at where each one lives and how to move through them. Skip anytime.',
    placement: 'auto',
  },
  {
    selector: '[data-tour="hero-cta"]',
    title: 'Start with the work',
    body: 'This scrolls straight to the three project cards — nothing is buried behind it.',
  },
  {
    selector: '[data-tour="project-deck"]',
    title: 'Three projects, one deck',
    body: 'RAG Workbench (auditable SEC-filing research), Haze Watch (the climate-risk app, live on this domain) and Quant Platform (open source). The front card is the active one: click it to open its story, or move the deck with the arrows, the dots, a swipe, or the arrow keys.',
  },
  {
    selector: '[data-tour="contact"]',
    title: 'That is the tour',
    body: 'If any of it is relevant to what you are hiring for, the links are right here — LinkedIn, GitHub and email.',
  },
];

/** Guided tour for the Haze Watch case-study page (/projects/haze-watch). */
export const HAZEWATCH_TOUR: CoachStep[] = [
  {
    title: 'Haze Watch — the case study',
    body: 'Four steps: what the app does, the data behind it, how a hazard becomes a credit signal, and where to open it. Skip anytime.',
    placement: 'auto',
  },
  {
    selector: '[data-tour="app-cta"]',
    title: 'Open the app',
    body: 'The app runs on this domain at /haze-watch — same tab, no separate host. It answers from precomputed public-safe outputs, with a deterministic fallback when no model key is configured.',
  },
  {
    selector: '[data-tour="historical-data"]',
    title: 'The data behind it',
    body: 'A 25-year fire record (MODIS 2000+, VIIRS 2012+), 85 years of reanalysis weather (ERA5 1940+) and aerosol depth (CAMS 2022+) — assembled into a versioned history store, with each source’s current state listed in this section.',
  },
  {
    selector: '[data-tour="how-it-works"]',
    title: 'Hazard → exposure → cash flow',
    body: 'Real environmental data joined to concession geography, then auditable stress scenarios over the same numbers a credit memo would cite. Hazard scores are labelled baselines, never probabilities of default.',
  },
];
