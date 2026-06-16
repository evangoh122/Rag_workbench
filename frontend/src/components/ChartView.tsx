import React, { useState, useMemo } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';
import type { ChartSpec } from '../api/chat';

const ACCENT = '#2E8B57';
const AXIS = '#888888';
const GRID = 'rgba(255,255,255,0.06)';

function fmtUSD(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

interface TooltipBoxProps {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
  formatter: (v: number) => string;
}

const TooltipBox: React.FC<TooltipBoxProps> = ({ active, payload, label, formatter }) => {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="glass-sm px-3 py-2 text-xs">
      <div className="text-secondary">{label}</div>
      <div className="text-primary font-semibold tabular-nums">{formatter(payload[0].value)}</div>
    </div>
  );
};

type ViewMode = 'annual' | 'quarterly';

const ChartView: React.FC<{ chart: ChartSpec }> = ({ chart }) => {
  const [mode, setMode] = useState<ViewMode>('annual');
  const isPct = chart.unit === '%';
  const fmt = (v: number) => (isPct ? `${v.toFixed(1)}%` : fmtUSD(v));

  const hasQuarterly = chart.quarterly && chart.quarterly.length > 0;

  const chartData = useMemo(() => {
    if (mode === 'quarterly' && hasQuarterly) {
      return chart.quarterly;
    }
    return chart.annual || chart.data;
  }, [mode, chart, hasQuarterly]);

  return (
    <div className="fintech-card p-4 mt-3">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-primary">{chart.title}</h4>
        <div className="flex items-center gap-2">
          {hasQuarterly && (
            <div className="flex items-center bg-surface-elevated rounded-lg border border-border p-0.5">
              <button
                onClick={() => setMode('annual')}
                className={`px-2.5 py-1 text-[10px] font-medium rounded-md transition-colors ${
                  mode === 'annual'
                    ? 'bg-accent/20 text-accent'
                    : 'text-secondary hover:text-primary'
                }`}
              >
                Annual
              </button>
              <button
                onClick={() => setMode('quarterly')}
                className={`px-2.5 py-1 text-[10px] font-medium rounded-md transition-colors ${
                  mode === 'quarterly'
                    ? 'bg-accent/20 text-accent'
                    : 'text-secondary hover:text-primary'
                }`}
              >
                Quarterly
              </button>
            </div>
          )}
          <span className="text-[10px] uppercase tracking-wide text-accent border border-accent/30 bg-accent/10 rounded-full px-2 py-0.5">
            XBRL-derived
          </span>
        </div>
      </div>
      <div style={{ width: '100%', height: 240 }}>
        {mode === 'quarterly' && (!chart.quarterly || chart.quarterly.length === 0) ? (
          <div className="flex items-center justify-center h-full text-secondary text-sm">
            No quarterly data available for this metric
          </div>
        ) : (
          <ResponsiveContainer>
            {chart.type === 'bar' ? (
              <BarChart data={chartData} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis 
                  dataKey="period" 
                  stroke={AXIS} 
                  fontSize={11} 
                  tickLine={false}
                  interval={mode === 'quarterly' ? 3 : 0}
                />
                <YAxis stroke={AXIS} fontSize={11} tickLine={false} width={52}
                       tickFormatter={fmt} />
                <Tooltip content={<TooltipBox formatter={fmt} />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                <Bar dataKey="value" fill={ACCENT} radius={[4, 4, 0, 0]} />
              </BarChart>
            ) : (
              <LineChart data={chartData} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis 
                  dataKey="period" 
                  stroke={AXIS} 
                  fontSize={11} 
                  tickLine={false}
                  interval={mode === 'quarterly' ? 3 : 0}
                />
                <YAxis stroke={AXIS} fontSize={11} tickLine={false} width={52}
                       tickFormatter={fmt} />
                <Tooltip content={<TooltipBox formatter={fmt} />} cursor={{ stroke: 'rgba(255,255,255,0.12)' }} />
                <Line type="monotone" dataKey="value" stroke={ACCENT} strokeWidth={2}
                      dot={{ r: mode === 'quarterly' ? 1.5 : 3, fill: ACCENT }} activeDot={{ r: 5 }} />
              </LineChart>
            )}
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};

export default ChartView;
