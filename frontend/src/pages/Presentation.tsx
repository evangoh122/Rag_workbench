import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Play, Pause, Award, BarChart3 } from 'lucide-react';

interface Slide {
  id: number;
  title: string;
  subtitle?: string;
  category: string;
  content: React.ReactNode;
}

export default function Presentation() {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  
  const slides: Slide[] = [
    {
      id: 1,
      category: "Cover",
      title: "Show Your Work",
      subtitle: "Auditable AI for Financial Filings",
      content: (
        <div className="flex flex-col items-center justify-center h-full text-center px-4 relative">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-emerald-500/5 rounded-full blur-3xl pointer-events-none" />
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-green-600 flex items-center justify-center font-mono font-extrabold text-white text-2xl shadow-[0_0_24px_rgba(46,139,87,0.25)] mb-8">
            E
          </div>
          <h1 className="text-5xl md:text-6xl font-black tracking-tight text-white mb-4">
            Show Your Work
          </h1>
          <p className="text-2xl md:text-3xl text-emerald-400 font-light tracking-wide mb-12">
            Auditable AI for Financial Filings
          </p>
          <div className="text-sm font-mono text-secondary space-y-1 border-t border-border/40 pt-6 max-w-sm w-full">
            <div>Technical Architecture Overview</div>
            <div>Evan Goh &bull; June 2026</div>
          </div>
        </div>
      )
    },
    {
      id: 2,
      category: "Agenda",
      title: "Presentation Overview",
      content: (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center h-full">
          <div>
            <h3 className="text-xl font-bold text-emerald-400 mb-4 font-mono">Structural Roadmap</h3>
            <p className="text-secondary text-sm leading-relaxed mb-6">
              A comprehensive view of the components designed to bridge the trust gap between generative language models and quantitative corporate financial audits.
            </p>
            <div className="w-full h-1 bg-border/40 rounded overflow-hidden">
              <div className="w-1/4 h-full bg-accent" />
            </div>
          </div>
          <div className="space-y-3 font-mono text-xs text-secondary max-h-[350px] overflow-y-auto pr-2">
            <div className="flex gap-4 p-2.5 rounded-lg border border-border bg-surface/50">
              <span className="text-accent">01</span>
              <span className="text-primary font-sans font-semibold">Executive Summary</span>
            </div>
            <div className="flex gap-4 p-2.5 rounded-lg border border-border bg-surface/50">
              <span className="text-accent">02</span>
              <span className="text-primary font-sans font-semibold">Target Personas & JTBD Matrix</span>
            </div>
            <div className="flex gap-4 p-2.5 rounded-lg border border-border bg-surface/50">
              <span className="text-accent">03</span>
              <span className="text-primary font-sans font-semibold">6-Layer Extraction Validation</span>
            </div>
            <div className="flex gap-4 p-2.5 rounded-lg border border-border bg-surface/50">
              <span className="text-accent">04</span>
              <span className="text-primary font-sans font-semibold">5 Sequential Flow Checkpoints</span>
            </div>
            <div className="flex gap-4 p-2.5 rounded-lg border border-border bg-surface/50">
              <span className="text-accent">05</span>
              <span className="text-primary font-sans font-semibold">Human-in-the-Loop & Drift Alerts</span>
            </div>
            <div className="flex gap-4 p-2.5 rounded-lg border border-border bg-surface/50">
              <span className="text-accent">06</span>
              <span className="text-primary font-sans font-semibold">Singapore MAS FEAT & US SR 11-7 Compliance</span>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 3,
      category: "Executive Summary",
      title: "Executive Summary",
      content: (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-full text-xs">
          <div className="space-y-4">
            <div className="glass-sm p-4">
              <h4 className="text-accent font-semibold text-sm mb-1.5 font-mono">The Situation</h4>
              <p className="text-secondary leading-relaxed">
                Reviewing corporate financial disclosures is a tedious, highly manual process. Analysts spend significant time cross-checking figures and citations across thousands of pages.
              </p>
            </div>
            <div className="glass-sm p-4">
              <h4 className="text-red-400 font-semibold text-sm mb-1.5 font-mono">The Complication</h4>
              <p className="text-secondary leading-relaxed">
                Generative AI tools (LLMs) used to review filings act as "black boxes." They offer no direct audit trail, frequently confuse dimensions, and lack deterministic grounding, risking massive hallucinated errors.
              </p>
            </div>
          </div>
          
          <div className="glass-sm p-4 flex flex-col justify-between">
            <div>
              <h4 className="text-accent font-semibold text-sm mb-3 font-mono">The Auditable Solution</h4>
              <p className="text-secondary leading-relaxed mb-4">
                An end-to-end framework combining hybrid search (semantic + BM25), deterministic cross-referencing against SEC XBRL facts, confidence-based queue routing, and real-time drift alerts.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
              <div className="border border-border/40 p-2 rounded bg-surface/30">
                <div className="text-emerald-400 font-bold">RRF Hybrid</div>
                <div className="text-secondary">BM25 + Semantic</div>
              </div>
              <div className="border border-border/40 p-2 rounded bg-surface/30">
                <div className="text-emerald-400 font-bold">XBRL Gounded</div>
                <div className="text-secondary">SEC facts aligned</div>
              </div>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 4,
      category: "Problem Definition",
      title: "The Trust Gap",
      content: (
        <div className="flex flex-col justify-center h-full max-w-2xl mx-auto text-center space-y-6">
          <Award size={48} className="text-accent mx-auto animate-pulse" />
          <h3 className="text-xl md:text-2xl font-bold text-primary tracking-tight">
            Financial analysis requires absolute precision. Confident guesses are liabilities.
          </h3>
          <p className="text-secondary text-sm leading-relaxed">
            Traditional AI models fail because they decouple text generation from source data tables. To build a system that credit analysts, risk professionals, and compliance auditors can trust, we must force the AI to prove its calculations and show its work at every node of execution.
          </p>
        </div>
      )
    },
    {
      id: 5,
      category: "User Personas",
      title: "Impacted User Personas",
      content: (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 h-full text-xs">
          <div className="glass-sm p-4 flex flex-col justify-between">
            <div>
              <div className="font-bold text-accent mb-1">Mary M.</div>
              <div className="text-[10px] text-secondary font-mono mb-3">Compliance Officer</div>
              <p className="text-secondary/80 font-light">Requires full evidence repeatability, unalterable audit logs, and compliance dashboards.</p>
            </div>
            <div className="text-[10px] font-mono text-emerald-400 mt-2">Needs Audit Trails</div>
          </div>
          <div className="glass-sm p-4 flex flex-col justify-between">
            <div>
              <div className="font-bold text-accent mb-1">Derek T.</div>
              <div className="text-[10px] text-secondary font-mono mb-3">Equity Research</div>
              <p className="text-secondary/80 font-light">Seeks quick comparative disclosures across periods with direct click-to-paragraph citations.</p>
            </div>
            <div className="text-[10px] font-mono text-emerald-400 mt-2">Needs Context Links</div>
          </div>
          <div className="glass-sm p-4 flex flex-col justify-between">
            <div>
              <div className="font-bold text-accent mb-1">Nayara N.</div>
              <div className="text-[10px] text-secondary font-mono mb-3">Credit Analyst</div>
              <p className="text-secondary/80 font-light">Evaluates exposures at default. Demands absolute math checks grounded directly on corporate numbers.</p>
            </div>
            <div className="text-[10px] font-mono text-emerald-400 mt-2">Needs Numeric Check</div>
          </div>
          <div className="glass-sm p-4 flex flex-col justify-between">
            <div>
              <div className="font-bold text-accent mb-1">Robert Q.</div>
              <div className="text-[10px] text-secondary font-mono mb-3">Relationship Manager</div>
              <p className="text-secondary/80 font-light">Needs rapid, error-free risk summaries to prepare client-ready insights before executive briefs.</p>
            </div>
            <div className="text-[10px] font-mono text-emerald-400 mt-2">Needs Speed & Accuracy</div>
          </div>
        </div>
      )
    },
    {
      id: 6,
      category: "Jobs to be Done",
      title: "Jobs to be Done (JTBD) Matrix",
      content: (
        <div className="overflow-x-auto h-full max-h-[360px] text-[11px]">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-border bg-surface/40 font-mono">
                <th className="p-2.5 font-bold uppercase text-accent">Persona</th>
                <th className="p-2.5 font-bold uppercase text-accent">Motivation</th>
                <th className="p-2.5 font-bold uppercase text-accent">Outcome Sought</th>
                <th className="p-2.5 font-bold uppercase text-accent">Emotional Job</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 text-secondary">
              <tr>
                <td className="p-2.5 font-semibold text-primary">Compliance</td>
                <td className="p-2.5">Post-deployment audits of system outputs</td>
                <td className="p-2.5 font-mono text-[10px] text-emerald-300">Unalterable audit logs</td>
                <td className="p-2.5">Confidence that AI models won't introduce liability</td>
              </tr>
              <tr>
                <td className="p-2.5 font-semibold text-primary">Equity Analyst</td>
                <td className="p-2.5">deadline-driven filing searches</td>
                <td className="p-2.5 font-mono text-[10px] text-emerald-300">Click-through source citations</td>
                <td className="p-2.5">Credibility when publishing analyst opinions</td>
              </tr>
              <tr>
                <td className="p-2.5 font-semibold text-primary">Credit Risk</td>
                <td className="p-2.5">Assessing borrower default risk</td>
                <td className="p-2.5 font-mono text-[10px] text-emerald-300">XBRL verified numbers</td>
                <td className="p-2.5">Certainty that quantitative facts are not hallucinated</td>
              </tr>
              <tr>
                <td className="p-2.5 font-semibold text-primary">Relationship Mgr</td>
                <td className="p-2.5">Pre-meeting client briefs</td>
                <td className="p-2.5 font-mono text-[10px] text-emerald-300">Clean, ready-to-share summaries</td>
                <td className="p-2.5">Feeling fully prepared and informed for meetings</td>
              </tr>
            </tbody>
          </table>
        </div>
      )
    },
    {
      id: 7,
      category: "Extraction Validation",
      title: "6-Layer Extraction Validation",
      content: (
        <div className="overflow-x-auto h-full max-h-[365px] text-[10.5px]">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-border bg-surface/50 font-mono">
                <th className="p-2 font-bold uppercase text-accent">Layer</th>
                <th className="p-2 font-bold uppercase text-accent">Objective</th>
                <th className="p-2 font-bold uppercase text-accent">Mechanism</th>
                <th className="p-2 font-bold uppercase text-accent">Mitigated Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 text-secondary">
              <tr>
                <td className="p-2 font-semibold text-primary">1. Structural Check</td>
                <td className="p-2">Schema formatting</td>
                <td className="p-2">Type-validation & scale-confusion flags (e.g. &lt; $10k checks)</td>
                <td className="p-2">Data type pipeline crashes</td>
              </tr>
              <tr>
                <td className="p-2 font-semibold text-primary">2. Semantic Integrity</td>
                <td className="p-2">Financial identity consistency</td>
                <td className="p-2">Double-check basic identities (Assets = Liabilities + Equity)</td>
                <td className="p-2">LLM math hallucinations</td>
              </tr>
              <tr>
                <td className="p-2 font-semibold text-primary">3. XBRL Validation</td>
                <td className="p-2">Ground-truth alignment</td>
                <td className="p-2">Compare numbers with SEC Company Facts API (within 1% tolerance)</td>
                <td className="p-2">Quantitative source drift</td>
              </tr>
              <tr>
                <td className="p-2 font-semibold text-primary">4. NLI Verification</td>
                <td className="p-2">Text-to-number checks</td>
                <td className="p-2">Use NLI (DeBERTa) to check text statements against numbers</td>
                <td className="p-2">Contradictory summary claims</td>
              </tr>
              <tr>
                <td className="p-2 font-semibold text-primary">5. External Check</td>
                <td className="p-2">Market confirmation</td>
                <td className="p-2">Cross-check metrics with Polygon.io and auditor logs</td>
                <td className="p-2">Incorrect restatements</td>
              </tr>
              <tr>
                <td className="p-2 font-semibold text-primary">6. Routing Layer</td>
                <td className="p-2">HITL Governance</td>
                <td className="p-2">Route to Auto-Approve, Sampled Review, or Escalate queues</td>
                <td className="p-2">Liability of edge cases</td>
              </tr>
            </tbody>
          </table>
        </div>
      )
    },
    {
      id: 8,
      category: "Execution Checkpoints",
      title: "5 Sequential Checkpoints for Traceability",
      content: (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 h-full text-xs font-mono">
          <div className="border border-border/40 p-3 rounded-xl bg-surface/20 flex flex-col justify-between">
            <div>
              <div className="text-emerald-400 font-bold mb-1">01</div>
              <div className="text-primary font-sans font-bold text-xs mb-1.5">Provenance</div>
              <p className="text-secondary/70 text-[10px] font-sans">Tag every field at extraction with source type (XBRL, narrative, etc.)</p>
            </div>
            <span className="text-[9px] text-accent mt-3">Linear Track</span>
          </div>
          <div className="border border-border/40 p-3 rounded-xl bg-surface/20 flex flex-col justify-between">
            <div>
              <div className="text-emerald-400 font-bold mb-1">02</div>
              <div className="text-primary font-sans font-bold text-xs mb-1.5">Lineage Node</div>
              <p className="text-secondary/70 text-[10px] font-sans">LangGraph terminal node seals metadata, chunk IDs, and model parameters</p>
            </div>
            <span className="text-[9px] text-accent mt-3">Run Sealed</span>
          </div>
          <div className="border border-border/40 p-3 rounded-xl bg-surface/20 flex flex-col justify-between">
            <div>
              <div className="text-emerald-400 font-bold mb-1">03</div>
              <div className="text-primary font-sans font-bold text-xs mb-1.5">Audit Trail</div>
              <p className="text-secondary/70 text-[10px] font-sans">Write to dedicated SQL audit, review decision, and calibration tables</p>
            </div>
            <span className="text-[9px] text-accent mt-3">Persisted DB</span>
          </div>
          <div className="border border-border/40 p-3 rounded-xl bg-surface/20 flex flex-col justify-between">
            <div>
              <div className="text-emerald-400 font-bold mb-1">04</div>
              <div className="text-primary font-sans font-bold text-xs mb-1.5">Attribution</div>
              <p className="text-secondary/70 text-[10px] font-sans">Associate answer snippets with clickable URLs and raw source text</p>
            </div>
            <span className="text-[9px] text-accent mt-3">Explainability</span>
          </div>
          <div className="border border-border/40 p-3 rounded-xl bg-surface/20 flex flex-col justify-between">
            <div>
              <div className="text-emerald-400 font-bold mb-1">05</div>
              <div className="text-primary font-sans font-bold text-xs mb-1.5">API Visibility</div>
              <p className="text-secondary/70 text-[10px] font-sans">Expose audit histories securely through REST endpoints for monitoring</p>
            </div>
            <span className="text-[9px] text-accent mt-3">Compliance Gate</span>
          </div>
        </div>
      )
    },
    {
      id: 9,
      category: "Governance & Monitoring",
      title: "Human-in-the-Loop & Drift Monitoring",
      content: (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-full text-xs">
          <div className="space-y-4">
            <div className="glass-sm p-4">
              <h4 className="text-accent font-bold mb-1.5 font-mono">1. Risk-Tiered Routing</h4>
              <p className="text-secondary">
                Outputs are scored dynamically based on validation results and automatically routed into **Auto-Approve**, **Sampled Review**, or **Escalate** queues for analyst verification.
              </p>
            </div>
            <div className="glass-sm p-4">
              <h4 className="text-accent font-bold mb-1.5 font-mono">2. Interactive Review Queue</h4>
              <p className="text-secondary">
                A dedicated interface logs analyst verdicts (Agree/Disagree) and tracks user sentiments, feeding corrections back into the pipeline.
              </p>
            </div>
          </div>
          <div className="space-y-4">
            <div className="glass-sm p-4">
              <h4 className="text-accent font-bold mb-1.5 font-mono">3. Automated Calibration</h4>
              <p className="text-secondary">
                The database captures human feedback to calibrate baseline models and adjust dynamic threshold parameters, demonstrating supervision to regulators.
              </p>
            </div>
            <div className="glass-sm p-4">
              <h4 className="text-accent font-bold mb-1.5 font-mono">4. Real-Time Drift Alerts</h4>
              <p className="text-secondary">
                Frontend dashboard widgets actively monitor agreement rate trends and concept drift, triggering alerts to model managers if quality falls.
              </p>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 10,
      category: "Compliance",
      title: "Compliance Guidelines Alignment",
      content: (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-full text-xs">
          <div className="glass-sm p-5 flex flex-col justify-between">
            <div>
              <h4 className="text-emerald-400 font-bold mb-3 font-mono flex items-center gap-1.5">
                🇸🇬 Singapore MAS FEAT & Veritas
              </h4>
              <ul className="space-y-2.5 text-secondary">
                <li>
                  <strong className="text-primary font-mono">Fairness:</strong> Defined as out-of-scope (research/audit only, not a credit-approval decision engine).
                </li>
                <li>
                  <strong className="text-primary font-mono">Ethics:</strong> Strictly enforces validation checks and returns refutals when evidence criteria fail.
                </li>
                <li>
                  <strong className="text-primary font-mono">Accountability:</strong> Records prompt versions, LLM model states, and analyst approvals in immutable DB storage.
                </li>
                <li>
                  <strong className="text-primary font-mono">Transparency:</strong> Shows clear evidence nodes and direct click-through highlights.
                </li>
              </ul>
            </div>
            <span className="text-[10px] text-muted font-mono mt-4">MAS Veritas Framework Aligned</span>
          </div>

          <div className="glass-sm p-5 flex flex-col justify-between">
            <div>
              <h4 className="text-emerald-400 font-bold mb-3 font-mono flex items-center gap-1.5">
                🇺🇸 US SR 11-7 Model Risk Management
              </h4>
              <ul className="space-y-2.5 text-secondary">
                <li>
                  <strong className="text-primary font-mono">Model Inventory:</strong> Catalogues versions, training configurations, and data cuts for each LLM and embedder.
                </li>
                <li>
                  <strong className="text-primary font-mono">Validation Dashboard:</strong> Captures and graphs metrics for citation accuracy and NLI verification logs.
                </li>
                <li>
                  <strong className="text-primary font-mono">Effective Challenge:</strong> Executes automated verification flows independent of the LLM parser.
                </li>
                <li>
                  <strong className="text-primary font-mono">Governance:</strong> Incorporates explicit analyst sign-off requirements and visible disclaimer banners.
                </li>
              </ul>
            </div>
            <span className="text-[10px] text-muted font-mono mt-4">Federal Reserve SR 11-7 Aligned</span>
          </div>
        </div>
      )
    },
    {
      id: 11,
      category: "Business Case",
      title: "Business Case & Operational ROI",
      content: (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-full items-center">
          <div className="glass-sm p-6 text-center border-l-2 border-accent">
            <h4 className="text-sm font-semibold text-secondary font-mono mb-2">Efficiency Gain</h4>
            <div className="text-3xl font-extrabold text-white mb-2 tabular-nums">15x</div>
            <p className="text-xs text-secondary/80">Average audit time per filing reduced from 15-30 mins to 1-2 mins.</p>
          </div>
          <div className="glass-sm p-6 text-center border-l-2 border-accent">
            <h4 className="text-sm font-semibold text-secondary font-mono mb-2">Answer Verifiability</h4>
            <div className="text-3xl font-extrabold text-white mb-2 tabular-nums">100%</div>
            <p className="text-xs text-secondary/80">Citations matched to exact database index records and XBRL IDs.</p>
          </div>
          <div className="glass-sm p-6 text-center border-l-2 border-accent">
            <h4 className="text-sm font-semibold text-secondary font-mono mb-2">Audit Compliance</h4>
            <div className="text-3xl font-extrabold text-white mb-2 tabular-nums">FEAT</div>
            <p className="text-xs text-secondary/80">Fully aligned logs prepared for regulatory disclosure and reviews.</p>
          </div>
        </div>
      )
    },
    {
      id: 12,
      category: "Architecture",
      title: "Technical Architecture Pipeline",
      content: (
        <div className="flex flex-col justify-between h-full text-xs">
          <div className="relative">
            {/* Timeline-style layout */}
            <div className="absolute left-4 top-2 bottom-2 w-0.5 bg-border/40" />
            <div className="space-y-4 ml-10">
              <div className="relative">
                <div className="absolute -left-[30px] w-4 h-4 rounded-full bg-accent border-4 border-background flex items-center justify-center" />
                <h4 className="font-bold text-primary">1. Sourcing & layout-aware chunking</h4>
                <p className="text-secondary text-[11px]">Downloads filings from SEC EDGAR, splitting text and accounting tables cleanly.</p>
              </div>
              <div className="relative">
                <div className="absolute -left-[30px] w-4 h-4 rounded-full bg-accent border-4 border-background flex items-center justify-center" />
                <h4 className="font-bold text-primary">2. Local Simulation & Indexing</h4>
                <p className="text-secondary text-[11px]">Embeds text with Qwen 0.6B, and seeds a local DuckDB vector + relational database.</p>
              </div>
              <div className="relative">
                <div className="absolute -left-[30px] w-4 h-4 rounded-full bg-accent border-4 border-background flex items-center justify-center" />
                <h4 className="font-bold text-primary">3. Hybrid Retrieval & Rerank</h4>
                <p className="text-secondary text-[11px]">Merges semantic similarity search and BM25 keywords via RRF, filtered by a reranker.</p>
              </div>
              <div className="relative">
                <div className="absolute -left-[30px] w-4 h-4 rounded-full bg-accent border-4 border-background flex items-center justify-center" />
                <h4 className="font-bold text-primary">4. LLM Synthesis & Verification</h4>
                <p className="text-secondary text-[11px]">LangGraph feeds chunks to LLM, queries graph subgraphs, and applies XBRL verification.</p>
              </div>
            </div>
          </div>
        </div>
      )
    }
  ];

  // Auto-play timer
  useEffect(() => {
    let interval: any = null;
    if (isPlaying) {
      interval = setInterval(() => {
        setCurrentSlide((prev) => (prev + 1) % slides.length);
      }, 5000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isPlaying, slides.length]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        setIsPlaying(false);
        setCurrentSlide((prev) => (prev + 1) % slides.length);
      } else if (e.key === 'ArrowLeft') {
        setIsPlaying(false);
        setCurrentSlide((prev) => (prev - 1 + slides.length) % slides.length);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [slides.length]);

  return (
    <div className="flex-1 flex flex-col h-full bg-background animate-in fade-in duration-200 overflow-hidden">
      {/* Header */}
      <header className="px-3 md:px-4 lg:px-8 py-3 md:py-4 glass-header z-10 flex-shrink-0 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-base md:text-lg font-semibold text-primary flex items-center gap-2">
            <BarChart3 className="text-accent animate-pulse" size={18} />
            Show Your Work Presentation
          </h1>
          <p className="text-xs text-secondary mt-0.5">Interactive architecture deck & regulatory compliance analysis.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="flex items-center justify-center w-8 h-8 rounded-lg bg-surface hover:bg-surface-elevated text-secondary hover:text-primary transition-all border border-border cursor-pointer"
            title={isPlaying ? "Pause autoplay" : "Start autoplay"}
          >
            {isPlaying ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <div className="text-xs font-mono text-secondary px-3 py-1.5 bg-surface border border-border rounded-lg tabular-nums">
            {currentSlide + 1} / {slides.length}
          </div>
        </div>
      </header>

      {/* Main Slide Panel */}
      <div className="flex-1 min-h-0 flex flex-col items-center justify-center p-6 relative">
        <div className="w-full max-w-4xl h-[420px] md:h-[480px] bg-surface/30 border border-border/80 rounded-2xl p-6 md:p-10 flex flex-col justify-between relative shadow-[0_12px_40px_rgba(0,0,0,0.5)] overflow-hidden">
          
          {/* Category kicker */}
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] font-mono font-bold tracking-widest text-accent uppercase bg-accent/8 border border-accent/15 px-2.5 py-0.5 rounded-full">
              {slides[currentSlide].category}
            </span>
            <span className="text-[10px] font-mono text-muted">
              EG.AUDITABLE.RAG
            </span>
          </div>

          {/* Slide Body */}
          <div className="flex-1 min-h-0 py-2">
            {slides[currentSlide].id !== 1 && (
              <h2 className="text-xl md:text-2xl font-black text-primary tracking-tight mb-5 border-b border-border/30 pb-2">
                {slides[currentSlide].title}
              </h2>
            )}
            <div className="h-full max-h-[300px] md:max-h-[360px] relative">
              {slides[currentSlide].content}
            </div>
          </div>

          {/* Slide Footer */}
          <div className="flex items-center justify-between border-t border-border/20 pt-4 mt-4 text-[10px] font-mono text-secondary/60">
            <span>Evan Goh &bull; Auditable AI</span>
            <span>RAG WORKBENCH</span>
          </div>
        </div>

        {/* Slide controller bar */}
        <div className="flex items-center gap-4 mt-6">
          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentSlide((prev) => (prev - 1 + slides.length) % slides.length);
            }}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-surface hover:bg-surface-elevated border border-border text-secondary hover:text-primary transition-all text-xs font-semibold cursor-pointer active:scale-95 select-none"
          >
            <ChevronLeft size={14} />
            Previous
          </button>
          
          <div className="flex gap-1.5">
            {slides.map((_, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setIsPlaying(false);
                  setCurrentSlide(idx);
                }}
                className={`w-2.5 h-2.5 rounded-full transition-all duration-300 border-0 cursor-pointer ${
                  idx === currentSlide
                    ? 'bg-accent scale-110 shadow-[0_0_8px_rgba(46,139,87,0.8)]'
                    : 'bg-border/60 hover:bg-secondary'
                }`}
                title={`Go to slide ${idx + 1}`}
              />
            ))}
          </div>

          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentSlide((prev) => (prev + 1) % slides.length);
            }}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-surface hover:bg-surface-elevated border border-border text-secondary hover:text-primary transition-all text-xs font-semibold cursor-pointer active:scale-95 select-none"
          >
            Next
            <ChevronRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
