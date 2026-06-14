import { useEffect, useRef, useState } from 'react';
import './Landing.css';

/**
 * Marketing landing page (app front door). Re-skin of the brand mockup,
 * wired to the app's real @theme tokens via Landing.css. `onEnter` drops the
 * user into the workbench (chat view).
 */
export default function Landing({ onEnter }: { onEnter: () => void }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [openSrc, setOpenSrc] = useState<string | null>(null);

  // Scroll reveal via IntersectionObserver (no scroll-frame listeners).
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const els = Array.from(root.querySelectorAll<HTMLElement>('.reveal'));
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !('IntersectionObserver' in window)) {
      els.forEach((e) => e.classList.add('in'));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) {
            en.target.classList.add('in');
            io.unobserve(en.target);
          }
        });
      },
      { threshold: 0.16 },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, []);

  const toggleSrc = (id: string) => setOpenSrc((cur) => (cur === id ? null : id));
  const check = (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M5 12.5l4.5 4.5L19 7.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );

  return (
    <div className="lp" ref={rootRef}>
      {/* NAV */}
      <header className="nav">
        <div className="wrap nav-inner">
          <a className="brand" href="#top">
            <span className="mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none"><path d="M5 12.5l4.5 4.5L19 7.5" stroke="#0A0A0A" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </span>
            Auditable Filing-QA
          </a>
          <nav className="nav-links">
            <a href="#how">How it works</a>
            <a href="#features">Capabilities</a>
            <a href="#graph">Evidence Graph</a>
            <a href="#coverage">Coverage</a>
          </nav>
          <div className="nav-cta">
            <button className="signin" onClick={onEnter}>Sign in</button>
            <button className="btn btn-primary" onClick={onEnter}>Try a query</button>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section className="hero" id="top">
        <div className="wrap hero-grid">
          <div className="reveal">
            <span className="eyebrow">SEC filing intelligence</span>
            <h1>Every answer traces back to the filing.</h1>
            <p className="lede">Ask questions about 10-K filings and get answers with clickable citations and figures checked against XBRL.</p>
            <div className="cta-row">
              <button className="btn btn-primary" onClick={onEnter}>Try a query</button>
              <a className="btn btn-ghost" href="#how">See the audit trail</a>
            </div>
          </div>

          <div className="answer-card reveal" aria-label="Example answer">
            <div className="ac-q">
              <span className="role">Q</span>
              <span>How did Micron&rsquo;s revenue change year over year?</span>
            </div>
            <div className="ac-divider" />

            <div className="ac-label">Direct answer</div>
            <p className="ac-answer">Micron reported revenue of <b>$15.54B</b> in fiscal 2023, down <b>49%</b> from <b>$30.76B</b> in fiscal 2022.</p>

            <span className="badge">{check} Verified against XBRL</span>

            <p className="ac-means"><strong>What this means.</strong> Revenue nearly halved as memory prices fell sharply through the 2023 downcycle.</p>

            <div className="chips">
              <button className="chip" onClick={() => toggleSrc('rev23')}>10-K FY2023 &middot; Item 7</button>
              <button className="chip" onClick={() => toggleSrc('rev22')}>10-K FY2022 &middot; Item 8</button>
            </div>

            <div className={`source-pop${openSrc === 'rev23' ? ' open' : ''}`}>
              <div className="src-meta">10-K FY2023 &middot; Item 7 &middot; MD&amp;A</div>
              &ldquo;Total revenue for fiscal 2023 was $15.54 billion, a decrease of 49% compared to fiscal 2022, primarily due to declines in average selling prices for DRAM and NAND.&rdquo;
            </div>
            <div className={`source-pop${openSrc === 'rev22' ? ' open' : ''}`}>
              <div className="src-meta">10-K FY2022 &middot; Item 8 &middot; Financial Statements</div>
              &ldquo;Total revenue for fiscal 2022 was $30.76 billion, an increase of 11% compared to fiscal 2021.&rdquo;
            </div>

            <div className="ac-hint">
              <svg viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              Click a citation to open the exact source text
            </div>
          </div>
        </div>
      </section>

      {/* COVERAGE */}
      <div className="coverage" id="coverage">
        <div className="wrap reveal">
          <p className="cap">Reads filings from leading semiconductor companies</p>
          <div className="logos">
            <img src="https://cdn.simpleicons.org/nvidia/ffffff" alt="NVIDIA" loading="lazy" />
            <img src="https://cdn.simpleicons.org/amd/ffffff" alt="AMD" loading="lazy" />
            <img src="https://cdn.simpleicons.org/intel/ffffff" alt="Intel" loading="lazy" />
            <img src="https://cdn.simpleicons.org/qualcomm/ffffff" alt="Qualcomm" loading="lazy" />
            <img src="https://cdn.simpleicons.org/broadcom/ffffff" alt="Broadcom" loading="lazy" />
            <img src="https://cdn.simpleicons.org/arm/ffffff" alt="Arm" loading="lazy" />
          </div>
        </div>
      </div>

      {/* HOW IT WORKS */}
      <section id="how">
        <div className="wrap">
          <div className="sec-head reveal">
            <span className="eyebrow">How it works</span>
            <h2 style={{ marginTop: 14 }}>Built so you can check the work, not just read it.</h2>
            <p>Retrieval, calculation, and verification each leave a trail you can follow back to the original 10-K.</p>
          </div>

          <div className="steps reveal">
            <div className="step">
              <span className="num">01</span>
              <div>
                <h3>Ask in plain language</h3>
                <p>Type a question about a company. No query syntax, no ticker codes, no spreadsheet hunting.</p>
              </div>
              <span className="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M21 12a8 8 0 11-3.2-6.4M21 5v4h-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
            </div>
            <div className="step">
              <span className="num">02</span>
              <div>
                <h3>Retrieve and cite</h3>
                <p>Hybrid search pulls the relevant filing passages and attaches a citation to every claim in the answer.</p>
              </div>
              <span className="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M4 5h16M4 12h16M4 19h10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg></span>
            </div>
            <div className="step">
              <span className="num">03</span>
              <div>
                <h3>Verify and route</h3>
                <p>Numbers are cross-checked against XBRL. Low-confidence answers escalate to a human reviewer instead of guessing.</p>
              </div>
              <span className="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M12 3l8 4v5c0 4.4-3.1 7.7-8 9-4.9-1.3-8-4.6-8-9V7l8-4z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /><path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES (BENTO) */}
      <section id="features" style={{ paddingTop: 24 }}>
        <div className="wrap">
          <div className="sec-head reveal">
            <h2>What makes an answer auditable.</h2>
            <p>Five things separate a citation you can trust from a confident guess.</p>
          </div>

          <div className="bento">
            <div className="cell span2 reveal">
              <div className="kicker">Click-through evidence</div>
              <h3>Every citation opens the source text</h3>
              <p>Click a citation and read the exact passage it came from, with the filing, section, and period attached. Nothing is paraphrased away from its origin.</p>
              <div className="cite-demo">
                <span className="from">10-K FY2023 &middot; Item 1A</span>
                <span className="arrow" aria-hidden="true">&rarr;</span>
                <span className="to">&ldquo;Our business is subject to highly cyclical memory market conditions&hellip;&rdquo;</span>
              </div>
            </div>

            <div className="cell glow reveal">
              <div className="kicker">Evidence Graph</div>
              <h3>See how facts connect</h3>
              <p>Entities and figures are linked in a graph. Click an edge to jump to the filing text behind it.</p>
              <svg className="nodemotif" viewBox="0 0 240 116" fill="none" aria-hidden="true">
                <line x1="58" y1="58" x2="150" y2="30" stroke="#4ADE80" strokeWidth="1.6" />
                <line x1="58" y1="58" x2="150" y2="86" stroke="rgba(255,255,255,.18)" strokeWidth="1.6" />
                <line x1="150" y1="30" x2="210" y2="58" stroke="rgba(255,255,255,.18)" strokeWidth="1.6" />
                <circle cx="58" cy="58" r="14" fill="#1D4ED8" />
                <circle cx="150" cy="30" r="11" fill="#7c3aed" />
                <circle cx="150" cy="86" r="11" fill="#059669" />
                <circle cx="210" cy="58" r="9" fill="#4b5563" />
              </svg>
            </div>

            <div className="cell accent reveal">
              <div className="kicker">Numbers checked</div>
              <h3>Verified against XBRL</h3>
              <p>Every figure is reconciled to the company&rsquo;s structured XBRL data, so a stated number matches what was actually filed.</p>
              <span className="badge" style={{ marginTop: 16 }}>{check} Verified against XBRL</span>
            </div>

            <div className="cell reveal">
              <div className="kicker">Three-layer answers</div>
              <h3>Answer, meaning, next step</h3>
              <ul className="mini-list">
                <li><span className="dot">&bull;</span> The direct, cited answer</li>
                <li><span className="dot">&bull;</span> What it means in plain English</li>
                <li><span className="dot">&bull;</span> Suggested follow-up questions</li>
              </ul>
            </div>

            <div className="cell reveal">
              <div className="kicker">Knows its limits</div>
              <h3>Confidence and human review</h3>
              <p>When evidence is thin or numbers do not reconcile, the answer is flagged and routed to a reviewer rather than presented as fact.</p>
            </div>
          </div>
        </div>
      </section>

      {/* EVIDENCE GRAPH SPOTLIGHT */}
      <section className="spot" id="graph">
        <div className="wrap spot-grid">
          <div className="reveal">
            <span className="eyebrow">Evidence Graph</span>
            <h2 style={{ marginTop: 14 }}>Follow the thread from claim to source.</h2>
            <p style={{ marginTop: 16, color: 'var(--ink-soft)', fontSize: 18, maxWidth: '46ch' }}>
              Each answer is backed by a small graph of the entities, metrics, and filings it drew on. Select any connection to open the passage that supports it, so a reviewer can confirm a number in seconds instead of re-reading the report.
            </p>
            <div className="cta-row" style={{ marginTop: 26, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <button className="btn btn-primary" onClick={onEnter}>Try a query</button>
            </div>
          </div>

          <div className="panel reveal">
            <svg viewBox="0 0 420 230" width="100%" height="auto" role="img" aria-label="Evidence graph linking Micron to revenue and a 10-K filing">
              <line x1="90" y1="115" x2="240" y2="60" stroke="#4ADE80" strokeWidth="2" />
              <line x1="240" y1="60" x2="350" y2="120" stroke="rgba(255,255,255,.16)" strokeWidth="1.6" />
              <line x1="90" y1="115" x2="230" y2="175" stroke="rgba(255,255,255,.16)" strokeWidth="1.6" />
              <line x1="230" y1="175" x2="350" y2="120" stroke="rgba(255,255,255,.16)" strokeWidth="1.6" />
              <g fontFamily="Inter, sans-serif" fontSize="12" fontWeight="600">
                <circle cx="90" cy="115" r="30" fill="#1D4ED8" />
                <text x="90" y="119" textAnchor="middle" fill="#FFFFFF">Micron</text>
                <circle cx="240" cy="60" r="26" fill="#7c3aed" />
                <text x="240" y="64" textAnchor="middle" fill="#FFFFFF">Revenue</text>
                <circle cx="230" cy="175" r="26" fill="#059669" />
                <text x="230" y="179" textAnchor="middle" fill="#FFFFFF">XBRL</text>
                <circle cx="350" cy="120" r="30" fill="#4b5563" />
                <text x="350" y="116" textAnchor="middle" fill="#FFFFFF">10-K</text>
                <text x="350" y="130" textAnchor="middle" fill="#FFFFFF" fontSize="10">FY2023</text>
              </g>
            </svg>
            <div className="gcap">
              <svg viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              The green edge is the cited fact. Selecting it opens Item 7 of the FY2023 filing.
            </div>
            <div className="legend">
              <span><i style={{ background: '#1D4ED8' }} /> Company</span>
              <span><i style={{ background: '#7c3aed' }} /> Metric</span>
              <span><i style={{ background: '#059669' }} /> XBRL fact</span>
              <span><i style={{ background: '#4b5563' }} /> Filing</span>
            </div>
          </div>
        </div>
      </section>

      {/* QUOTE */}
      <section className="quote-sec">
        <div className="wrap reveal">
          <p className="quote">&ldquo;I stopped re-reading 10-Ks to check a single figure. I <span className="hl">click the citation</span> and the source is right there.&rdquo;</p>
          <div className="attrib">
            <span className="who">Priya Raghunathan</span>
            <span className="what">Equity Research Analyst, Stillwater Capital</span>
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section id="try" style={{ paddingTop: 24 }}>
        <div className="wrap">
          <div className="cta-band reveal">
            <h2>Ask a filing a question.</h2>
            <p>See the answer, the citation, and the XBRL check side by side on your first query.</p>
            <div className="cta-row">
              <button className="btn btn-primary" onClick={onEnter}>Try a query</button>
              <a className="btn btn-ghost" href="#how">See the audit trail</a>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer>
        <div className="wrap">
          <div className="foot-grid">
            <div>
              <a className="brand" href="#top">
                <span className="mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M5 12.5l4.5 4.5L19 7.5" stroke="#0A0A0A" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
                Auditable Filing-QA
              </a>
              <p className="foot-note" style={{ marginTop: 14 }}>Question answering over SEC filings, with citations and XBRL verification built in.</p>
            </div>
            <div className="foot-links">
              <div className="foot-col">
                <h4>Product</h4>
                <a href="#how">How it works</a>
                <a href="#features">Capabilities</a>
                <a href="#graph">Evidence Graph</a>
                <a href="#coverage">Coverage</a>
              </div>
              <div className="foot-col">
                <h4>Resources</h4>
                <a href="#">Documentation</a>
                <a href="#">Methodology</a>
                <a href="#">Changelog</a>
              </div>
              <div className="foot-col">
                <h4>Company</h4>
                <a href="#">About</a>
                <a href="#">Contact</a>
                <a href="#">Privacy</a>
              </div>
            </div>
          </div>
          <div className="foot-bottom">
            <span>&copy; 2026 Auditable Filing-QA</span>
            <span>Not investment advice. Filing data is for research and analysis.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
