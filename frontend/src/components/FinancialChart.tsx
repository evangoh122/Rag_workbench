import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
} from 'recharts';

interface Fact {
  concept?: string;
  label?: string;
  value?: number;
  unit?: string;
  period?: string;
  ticker?: string;
}

interface FinancialChartProps {
  facts?: Fact[];
}

const COLORS = ['var(--color-accent)', 'var(--color-silver)', '#60a5fa', '#34d399', '#fbbf24', '#22d3ee'];

/** Compact currency/number formatter: 1.23B, 456.7M, 12.3K. */
function fmt(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return `${n}`;
}

/** Short period label: prefer the year from an ISO date / period string. */
function periodLabel(p?: string): string {
  if (!p) return '—';
  const m = p.match(/(\d{4})/);
  return m ? m[1] : p;
}

/**
 * Renders XBRL facts as a grouped bar chart (value over period, one series per
 * concept). Falls back to nothing when there isn't enough numeric data to make
 * a meaningful chart, so the text answer + audit trail still stand on their own.
 */
function FinancialChart({ facts }: FinancialChartProps) {
  const numeric = (facts ?? []).filter(
    (f) => typeof f.value === 'number' && isFinite(f.value as number),
  );

  // Need at least 2 distinct data points to be worth a chart.
  if (numeric.length < 2) return null;

  // Pivot: period -> { period, [label]: value }
  const labels = Array.from(
    new Set(numeric.map((f) => f.label || f.concept || 'value')),
  ).slice(0, COLORS.length);

  const byPeriod = new Map<string, Record<string, number | string>>();
  for (const f of numeric) {
    const key = periodLabel(f.period);
    const label = f.label || f.concept || 'value';
    if (!labels.includes(label)) continue;
    const row = byPeriod.get(key) ?? { period: key };
    row[label] = f.value as number;
    byPeriod.set(key, row);
  }

  const data = Array.from(byPeriod.values()).sort((a, b) =>
    String(a.period).localeCompare(String(b.period)),
  );
  if (data.length < 2 && labels.length < 2) return null;

  const unit = numeric.find((f) => f.unit)?.unit || '';

  return (
    <div className="mt-3 p-4 bg-surface border border-border rounded-xl">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-semibold text-secondary uppercase tracking-widest">
          Financials{unit ? ` (${unit})` : ''}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
          <XAxis 
            dataKey="period" 
            tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} 
            axisLine={false}
            tickLine={false}
            dy={8}
          />
          <YAxis 
            tickFormatter={fmt} 
            tick={{ fill: 'var(--color-secondary)', fontSize: 11 }} 
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            formatter={(v) => fmt(Number(v))}
            contentStyle={{ 
              backgroundColor: 'var(--color-surface-elevated)', 
              border: '1px solid var(--color-border)', 
              borderRadius: '8px', 
              color: 'var(--color-primary)',
              boxShadow: 'none'
            }}
            labelStyle={{ color: 'var(--color-secondary)', fontWeight: 600, marginBottom: '4px' }}
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
          />
          {labels.length > 1 && (
            <Legend 
              verticalAlign="top" 
              align="right" 
              wrapperStyle={{ fontSize: 10, color: 'var(--color-secondary)', paddingBottom: '10px' }} 
              iconType="circle"
              iconSize={8}
            />
          )}
          {labels.map((label, i) => (
            <Bar 
              key={label} 
              dataKey={label} 
              fill={COLORS[i % COLORS.length]} 
              radius={[4, 4, 0, 0]} 
              barSize={labels.length > 1 ? 20 : 40}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default FinancialChart;
