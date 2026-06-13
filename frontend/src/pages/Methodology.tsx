import React, { useState } from 'react';
import { BookOpen, ChevronDown, ChevronRight } from 'lucide-react';

interface Section {
  id: string;
  title: string;
  content: React.ReactNode;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="bg-[#0f1219] border border-[#202532] rounded-2xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-[#161b24] transition-colors cursor-pointer border-0 bg-transparent"
        onClick={() => setOpen(o => !o)}
      >
        <span className="text-sm font-semibold text-white">{title}</span>
        {open
          ? <ChevronDown size={16} className="text-gray-500" />
          : <ChevronRight size={16} className="text-gray-500" />}
      </button>
      {open && (
        <div className="px-6 pb-6 border-t border-[#202532]">
          {children}
        </div>
      )}
    </div>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-gray-300 leading-relaxed mt-4">{children}</p>;
}

function H({ children }: { children: React.ReactNode }) {
  return <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest mt-5 mb-2">{children}</h4>;
}

function Tag({ children, color = 'blue' }: { children: React.ReactNode; color?: string }) {
  const colors: Record<string, string> = {
    blue:   'bg-blue-500/10 border-blue-500/20 text-blue-300',
    emerald:'bg-emerald-500/10 border-emerald-500/20 text-emerald-300',
    purple: 'bg-purple-500/10 border-purple-500/20 text-purple-300',
    orange: 'bg-orange-500/10 border-orange-500/20 text-orange-300',
    cyan:   'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
  };
  return (
    <span className={`inline-block px-2 py-0.5 text-xs font-mono rounded border ${colors[color] ?? colors.blue} mr-1.5 mb-1`}>
      {children}
    </span>
  );
}

function Table({ rows }: { rows: [string, string][] }) {
  return (
    <div className="mt-4 border border-[#202532] rounded-xl overflow-hidden">
      {rows.map(([k, v], i) => (
        <div key={i} className={`flex items-start gap-4 px-4 py-3 text-sm ${i % 2 === 0 ? 'bg-[#0a0c10]' : ''} ${i > 0 ? 'border-t border-[#202532]/50' : ''}`}>
          <span className="text-gray-400 font-medium w-40 flex-shrink-0">{k}</span>
          <span className="text-gray-300">{v}</span>
        </div>
      ))}
    </div>
  );
}

export default function Methodology() {
  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto">
      <header className="px-4 lg:px-8 py-5 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-sm flex-shrink-0">
        <h1 className="text-xl font-semibold text-white flex items-center gap-3">
          <BookOpen className="text-indigo-400" />
          Methodology
        </h1>
        <p className="text-sm text-gray-400 mt-1">
          How the RAG Workbench ingests, embeds, retrieves, and verifies financial data
        </p>
      </header>

      <div className="flex-1 p-8 space-y-4 max-w-4xl">

        <Section title="1 · Overview">
          <P>
            RAG Workbench is a retrieval-augmented generation system purpose-built for SEC financial
            filings. It combines three complementary retrieval strategies — dense vector search,
            structured XBRL lookup, and knowledge graph traversal — with an LLM synthesis layer and
            a verifier that cross-checks numeric claims against XBRL ground truth before returning
            an answer.
          </P>
          <P>
            The system is designed for <strong className="text-white">auditable, verifiable answers</strong>:
            every response carries source citations, the XBRL fact used for verification, and a
            pass/fail signal so analysts can trace exactly where each number came from.
          </P>
        </Section>

        <Section title="2 · Data Ingestion">
          <H>Source</H>
          <P>
            10-K filings are pulled from SEC EDGAR. The pipeline first tries{' '}
            <Tag>sec-edgar-downloader</Tag>, then falls back to{' '}
            <Tag>edgartools</Tag> (the SEC REST API) — which is the path that works from cloud
            hosts where SEC rate-limits or blocks the downloader's traffic. Each ticker is
            resolved to a CIK before fetching.
          </P>

          <H>Section targeting</H>
          <P>
            Rather than embedding the entire filing (which contains iXBRL boilerplate, repeated
            table headers, and XBRL metadata that degrade retrieval quality), the pipeline targets
            four high-signal sections:
          </P>
          <Table rows={[
            ['Item 1 — Business',    'Strategy, products, markets, competition'],
            ['Item 1A — Risk Factors','Disclosed risks and uncertainties'],
            ['Item 7 — MD&A',        'Management discussion: year-over-year analysis'],
            ['Item 8 — Financials',  'Consolidated statements and notes'],
          ]} />

          <H>Chunking</H>
          <P>
            Sections are split by a custom <Tag>StructureChunker</Tag> rather than a fixed-size
            splitter. Tables are detected (by numeric density and column alignment) and kept{' '}
            <strong className="text-white">intact as single chunks</strong> so financial rows are
            never cut mid-table; narrative text is split semantically by topic similarity. Every
            chunk is tagged with its <Tag>section_type</Tag>, <Tag>content_type</Tag>, and
            provenance (ticker, period, form type). Embeddings are generated in batches of 8.
          </P>
        </Section>

        <Section title="3 · Embedding">
          <H>Model</H>
          <P>
            Embeddings are generated <strong className="text-white">in-process</strong> with{' '}
            <Tag color="purple">sentence-transformers</Tag> running{' '}
            <Tag color="purple">Qwen/Qwen3-Embedding-0.6B</Tag> (1024 dimensions). Running the
            model inside the container means no external inference API — eliminating the rate
            limits, provider-routing failures, and cold starts that plague hosted embedding
            endpoints. The 0.6B variant is chosen deliberately: the 8B Qwen embedder is far more
            memory-hungry and OOMs on the deployment hardware, while 0.6B fits comfortably and
            still delivers strong retrieval quality.
          </P>
          <Table rows={[
            ['Model',      'Qwen3-Embedding-0.6B (sentence-transformers, in-process)'],
            ['Dimensions', '1024'],
            ['Storage',    'DuckDB FLOAT[1024] column'],
            ['Similarity', 'array_distance over L2-normalized vectors (equivalent to cosine ranking)'],
            ['Query input','Instruction-prefixed (Qwen uses an "Instruct: … Query: …" template); documents embedded as-is'],
          ]} />

          <H>Ticker embeddings</H>
          <P>
            Company descriptions from Polygon are separately embedded and stored in{' '}
            <Tag>ticker_embeddings</Tag> to enable semantic company lookup ("find semiconductor
            equipment companies") independently of filing content.
          </P>
        </Section>

        <Section title="4 · Retrieval Strategies">
          <H>Auditable RAG (primary)</H>
          <P>
            The default pipeline combines lexical and semantic retrieval, fuses the rankings, and
            applies a cross-encoder reranker before passing the top chunks to the LLM:
          </P>
          <Table rows={[
            ['Hybrid retrieval', 'BM25 (rank_bm25) + dense vector search over edgar_embeddings, run together'],
            ['RRF fusion',       'Reciprocal Rank Fusion merges the BM25 and vector rankings into one list'],
            ['Reranker',         'Cross-encoder (ms-marco-MiniLM) rescores the fused candidates for final relevance'],
            ['XBRL lookup',      'Exact-match against xbrl_facts for numeric concepts (Revenues, NetIncomeLoss, etc.)'],
            ['Ticker scoping',   'Ticker / period filtering to prevent cross-company contamination'],
          ]} />

          <H>Graph RAG (optional)</H>
          <P>
            When Graph RAG mode is selected, the system extracts named entities from the query and
            matches them against <Tag>graph_triples</Tag> using parameterized{' '}
            <Tag>ILIKE</Tag> substring matching on the subject and object columns. The matching
            triples are passed as additional context to the LLM, enabling relational questions that
            vector search alone cannot answer.
          </P>

          <H>SQL mode</H>
          <P>
            Generates and executes DuckDB SQL directly against structured tables. Useful for
            precise aggregations and period comparisons that are better expressed as queries than
            free-text retrieval.
          </P>
        </Section>

        <Section title="5 · Verification">
          <P>
            After the LLM generates an answer, the verifier cross-checks any numeric claim against
            the XBRL facts table. It returns one of three verdicts:
          </P>
          <Table rows={[
            ['VERIFIED',    'LLM number matches the XBRL fact within tolerance'],
            ['UNVERIFIABLE','No matching XBRL concept found (narrative claim, non-GAAP, etc.)'],
            ['DISCREPANCY', 'LLM number differs from XBRL fact — answer flagged for review'],
          ]} />
          <P>
            Non-GAAP metrics (adjusted EBITDA, non-GAAP EPS) cannot be verified against XBRL and
            are explicitly labeled <Tag color="orange">UNVERIFIABLE</Tag>. The correct behavior for
            the model on non-GAAP questions is to ABSTAIN or clearly label the figure as
            non-GAAP rather than returning an unverified number.
          </P>
        </Section>

        <Section title="6 · Human-in-the-Loop Review">
          <P>
            Answers are routed to one of three tracks based on confidence scoring and trigger
            detection:
          </P>
          <Table rows={[
            ['AUTO',           'High-confidence answers served directly — no human review required'],
            ['SAMPLED REVIEW', 'Random sample for ongoing quality auditing'],
            ['ESCALATE',       'Low confidence, discrepancy detected, or unrecognized concept — queued for analyst review'],
          ]} />
          <P>
            The AUTO tier requires ≥95% human agreement rate over a rolling 100-decision window
            to remain certified. Agreement rate is tracked in{' '}
            <Tag>reviewer_verdicts</Tag> and a drift alert fires if the rate drops below the floor.
          </P>
        </Section>

        <Section title="7 · Evaluation">
          <P>
            The golden evaluation set (<Tag>evals/golden_set.csv</Tag>) contains 50
            semiconductor-focused questions across seven failure modes:
          </P>
          <Table rows={[
            ['baseline',          'Direct XBRL lookup — should match to the cent'],
            ['segment',           'Segment-level revenue — model must not aggregate across segments'],
            ['period_mismatch',   'Model asked for an older period — tests temporal grounding'],
            ['gaap_vs_nongaap',   'Model must distinguish GAAP from non-GAAP and flag unverifiable'],
            ['derived_calculation','Requires arithmetic — model must show the computation'],
            ['abstention_failure','No valid GAAP answer exists — model should abstain, not invent'],
            ['restatement',       'Pre/post restatement numbers — tests awareness of filing history'],
          ]} />
          <P>
            Evaluations are run with <Tag>evals/run_eval.py</Tag> using RAGAS metrics
            (faithfulness, answer relevancy, context precision) plus custom XBRL-match scoring.
          </P>
        </Section>

        <Section title="8 · Security & Configuration">
          <H>DB path validation</H>
          <P>
            The <Tag>DB_PATH</Tag> environment variable is validated via{' '}
            <Tag>Path.is_relative_to()</Tag> to prevent path traversal — database files must
            reside within the project root.
          </P>
          <H>API key handling</H>
          <P>
            All API keys are loaded from <Tag>.env</Tag> via python-dotenv and never logged.
            The provider is selected at runtime via <Tag>CHAT_PROVIDER</Tag>; supported values are{' '}
            <Tag>deepseek</Tag> <Tag>mimo</Tag>.
          </P>
          <H>Rate limiting</H>
          <P>
            A per-IP rate limiter is applied at the middleware layer to prevent abuse of the
            chat endpoints. SEC EDGAR API calls are throttled to ≤10 req/s (150ms delay) to
            comply with EDGAR fair-use policy.
          </P>
        </Section>

      </div>
    </div>
  );
}
