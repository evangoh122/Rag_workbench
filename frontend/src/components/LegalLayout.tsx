import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, FileText } from 'lucide-react';
import { DisclaimerFooter } from './Disclaimer';

/**
 * Shared shell + prose primitives for the static legal pages (Privacy, Terms).
 * Mirrors the full-screen chrome of RagOverview (sticky header, max-w main,
 * disclaimer strip + footer) and the typographic scale of Methodology, so the
 * legal pages feel native to the rest of the app rather than bolted on.
 */

const CONTACT_EMAIL = 'evangohsg@gmail.com';

type OtherDoc = { label: string; path: string };

export default function LegalLayout({
  title,
  subtitle,
  updated,
  icon,
  otherDoc,
  children,
}: {
  title: string;
  subtitle: string;
  updated: string;
  icon?: React.ReactNode;
  otherDoc: OtherDoc;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background text-primary font-sans selection:bg-accent/20 selection:text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-border/40 bg-surface/20 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-secondary hover:text-primary transition-colors bg-transparent border-0 cursor-pointer font-medium text-sm"
          >
            <ArrowLeft size={16} />
            Back to Portfolio
          </button>
          <button
            onClick={() => navigate(otherDoc.path)}
            className="flex items-center gap-1.5 text-secondary hover:text-primary transition-colors bg-transparent border-0 cursor-pointer text-sm"
          >
            <FileText size={15} className="text-secondary/70" />
            <span>{otherDoc.label}</span>
          </button>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 w-full max-w-3xl mx-auto px-6 py-12">
        <div className="flex items-center gap-3">
          <span className="text-emerald-400">{icon ?? <ShieldCheck />}</span>
          <h1 className="text-2xl font-semibold text-primary tracking-tight m-0">{title}</h1>
        </div>
        <p className="text-sm text-secondary mt-2">{subtitle}</p>
        <p className="text-xs text-secondary/50 mt-1 font-mono">Last updated: {updated}</p>

        <div className="mt-8 space-y-7">{children}</div>

        <p className="mt-12 text-[11px] text-secondary/40 leading-relaxed">
          This page is provided for transparency about a personal, non-commercial research
          project and does not constitute legal advice. If anything here is unclear, contact{' '}
          <a href={`mailto:${CONTACT_EMAIL}`} className="text-secondary/60 hover:text-primary underline underline-offset-2">
            {CONTACT_EMAIL}
          </a>.
        </p>
      </main>

      <DisclaimerFooter className="mt-auto" />
      <footer className="border-t border-border/40 bg-surface/10 py-8 text-center text-xs text-secondary/50">
        <div className="max-w-3xl mx-auto px-6">
          <span>&copy; {new Date().getFullYear()} Evan Goh. All rights reserved.</span>
        </div>
      </footer>
    </div>
  );
}

/* ---- prose primitives (shared by Privacy + Terms) ---- */

export function Section({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold text-primary tracking-tight m-0">
        <span className="text-secondary/40 font-mono mr-2">{n}</span>
        {title}
      </h2>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

export function P({ children }: { children: React.ReactNode }) {
  return <p className="text-[14px] text-secondary leading-relaxed m-0">{children}</p>;
}

export function H({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs font-bold text-secondary/60 uppercase tracking-widest mt-5 mb-0">
      {children}
    </h3>
  );
}

export function UL({ children }: { children: React.ReactNode }) {
  return <ul className="mt-1 space-y-1.5 pl-0 list-none">{children}</ul>;
}

export function LI({ children }: { children: React.ReactNode }) {
  return (
    <li className="text-[14px] text-secondary leading-relaxed pl-4 relative">
      <span className="absolute left-0 top-[9px] w-1 h-1 rounded-full bg-emerald-500/60" />
      {children}
    </li>
  );
}

export function B({ children }: { children: React.ReactNode }) {
  return <strong className="text-primary font-semibold">{children}</strong>;
}

export function Mail() {
  return (
    <a href={`mailto:${CONTACT_EMAIL}`} className="text-emerald-400/90 hover:text-emerald-300 underline underline-offset-2">
      {CONTACT_EMAIL}
    </a>
  );
}
