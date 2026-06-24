import { useEffect, useState } from 'react';
import { Check, ChevronRight, Loader2, Sparkles, LayoutGrid } from 'lucide-react';
import {
  getConjointAttributes,
  saveConjointPrefs,
  type Role,
  type ConjointPrefs,
} from '../api/conjoint';

interface Props {
  /** Called once the user picks an arm (and a role, for treatment). */
  onChosen: (prefs: ConjointPrefs) => void;
}

type Phase = 'choose' | 'role';

const primaryBtn =
  'inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-accent/15 border border-accent/30 text-accent font-medium text-[13px] hover:bg-accent/25 transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
const ghostBtn =
  'inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-surface-elevated border border-border text-muted text-[13px] hover:text-secondary transition-colors disabled:opacity-50';

/**
 * Entry chooser for the standard (control) vs role-based (treatment) experience.
 * Self-selected assignment — the chosen arm + role are saved locally and drive
 * personalization for the session.
 */
export default function ConjointGate({ onChosen }: Props) {
  const [phase, setPhase] = useState<Phase>('choose');
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getConjointAttributes()
      .then((d) => !cancelled && setRoles(d.roles))
      .catch(() => {/* roles optional; treatment can still proceed role-less */})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const chooseControl = () => {
    const prefs: ConjointPrefs = { arm: 'control', role: null };
    saveConjointPrefs(prefs);
    onChosen(prefs);
  };

  const confirmTreatment = () => {
    const prefs: ConjointPrefs = { arm: 'treatment', role: selectedRole, answer_basis: 'role_based' };
    saveConjointPrefs(prefs);
    onChosen(prefs);
  };

  if (phase === 'choose') {
    return (
      <div>
        <h3 className="text-[16px] font-semibold text-primary m-0">How would you like to use the assistant?</h3>
        <p className="text-[12px] text-muted mt-1 mb-4">
          You can use the standard experience, or personalize answers to your professional role.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            onClick={chooseControl}
            className="text-left p-4 rounded-xl border border-border bg-surface-elevated hover:border-accent/40 hover:bg-accent/5 transition-colors"
          >
            <LayoutGrid size={18} className="text-secondary mb-2" />
            <div className="text-[14px] font-semibold text-secondary">Standard app</div>
            <p className="text-[12px] text-muted mt-1 mb-0">The default experience — same answers for everyone.</p>
          </button>
          <button
            onClick={() => setPhase('role')}
            className="text-left p-4 rounded-xl border border-accent/30 bg-accent/10 hover:border-accent/60 transition-colors"
          >
            <Sparkles size={18} className="text-accent mb-2" />
            <div className="text-[14px] font-semibold text-secondary">Personalize by role</div>
            <p className="text-[12px] text-muted mt-1 mb-0">Tailor answers to how your role works with filings.</p>
          </button>
        </div>
      </div>
    );
  }

  // phase === 'role'
  return (
    <div>
      <h3 className="text-[16px] font-semibold text-primary m-0">Which best describes your role?</h3>
      <p className="text-[12px] text-muted mt-1 mb-4">Answers will be tuned to this role's priorities.</p>
      {loading ? (
        <div className="flex items-center gap-2 text-muted text-[13px] py-6">
          <Loader2 size={16} className="animate-spin" /> Loading roles…
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {roles.map((r) => {
            const active = selectedRole === r.key;
            return (
              <button
                key={r.key}
                onClick={() => setSelectedRole(active ? null : r.key)}
                className={`text-left p-3.5 rounded-xl border transition-colors ${
                  active ? 'border-accent/60 bg-accent/10' : 'border-border bg-surface-elevated hover:border-accent/30'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-semibold text-secondary">{r.name}</span>
                  {active && <Check size={15} className="text-accent" />}
                </div>
                <p className="text-[11px] text-muted mt-1 mb-0">{r.situation}</p>
              </button>
            );
          })}
        </div>
      )}
      <div className="flex items-center gap-2.5 mt-4">
        <button onClick={confirmTreatment} disabled={!selectedRole} className={primaryBtn}>
          <ChevronRight size={15} /> Continue
        </button>
        <button onClick={() => setPhase('choose')} className={ghostBtn}>
          Back
        </button>
      </div>
    </div>
  );
}
