import type { CoachStep } from './CoachMarks';

// Versioned keys so a materially-changed tour can re-show to returning users.
export const CHAT_TOUR_KEY = 'rw_tour_chat_v1';
export const LANDING_TOUR_KEY = 'rw_tour_landing_v1';
export const OVERVIEW_TOUR_KEY = 'rw_tour_overview_v1';

/** Guided tour for the RAG Workbench product-overview page (/rag-overview). */
export const OVERVIEW_TOUR: CoachStep[] = [
  {
    title: 'RAG Workbench — the overview',
    body: 'A quick look at what this project is: the business case, the approach to auditable answers, and how to jump into the live app. Skip anytime.',
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
    body: 'The business case and the problem it solves: eliminating hallucinations in filing analysis with answers anchored to the source.',
  },
];

/** Guided tour for the /rag chat workbench (runs on the empty chat state). */
export const CHAT_TOUR: CoachStep[] = [
  {
    title: 'Welcome to RAG Workbench',
    body: "A quick 5-step tour of how to question SEC filings and inspect the evidence behind every answer. You can skip anytime.",
    placement: 'auto',
  },
  {
    selector: '[data-tour="nav"]',
    title: 'Navigate the workbench',
    body: 'Switch between the chat, knowledge graph, audit log, and the diagnostics dashboards here. On mobile, open this with the menu button.',
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
    title: "Welcome — here's the quick version",
    body: 'A 3-step orientation to this portfolio and the RAG Workbench demo. Skip anytime.',
    placement: 'auto',
  },
  {
    selector: '[data-tour="hero-cta"]',
    title: 'Start with the profile',
    body: 'A short walkthrough of who I am and how I work across data, AI, and product.',
  },
  {
    selector: '[data-tour="project-card"]',
    title: 'Open the RAG Workbench',
    body: 'The featured project: an auditable SEC-filing research assistant. Tap the card to launch the live demo.',
  },
];
