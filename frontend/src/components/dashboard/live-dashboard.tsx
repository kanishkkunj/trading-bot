'use client';

import { useMemo } from 'react';
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  LineChart,
  Line,
} from 'recharts';
import { useLiveDataStore } from '@/store/live-data';
import { useLiveWebSocket } from '@/hooks/use-live-websocket';

const formatPct = (v: number) => `${(v * 100).toFixed(2)}%`;
const formatTs = (ts: number) => new Date(ts).toLocaleTimeString();

export function LiveDashboard() {
  useLiveWebSocket(true);
  const { pnlSeries, regime, confidence, risk } = useLiveDataStore();

  const pnlData = useMemo(() => pnlSeries.map((p) => ({ ...p, tsLabel: formatTs(p.ts) })), [pnlSeries]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <Card title="Live P&L" subtitle="Real-time mark-to-market">
          <div className="h-32">
            <ResponsiveContainer>
              <AreaChart data={pnlData} margin={{ left: 0, right: 0, top: 8, bottom: 0 }}>
                <defs>
                  <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="tsLabel" hide />
                <YAxis hide domain={['auto', 'auto']} />
                <Tooltip formatter={(v: any) => v.toFixed(2)} labelFormatter={(l) => l} />
                <Area type="monotone" dataKey="value" stroke="#22c55e" fill="url(#pnlGradient)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="text-sm text-muted-foreground mt-2">
            Points: {pnlData.length}
          </div>
        </Card>

        <Card title="Regime" subtitle="Current + history">
          <div className="flex items-center gap-3">
            <span className="px-3 py-1 rounded-full bg-blue-500/10 text-blue-400 text-sm capitalize">
              {regime.label}
            </span>
          </div>
          <div className="h-24 mt-2">
            <ResponsiveContainer>
              <LineChart data={regime.history.map((p) => ({ ...p, tsLabel: formatTs(p.ts) }))}>
                <XAxis dataKey="tsLabel" hide />
                <YAxis hide domain={[-2, 2]} />
                <Line type="stepAfter" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Model Confidence" subtitle="Mean ± uncertainty">
          <div className="text-2xl font-semibold">{(confidence.mean * 100).toFixed(1)}%</div>
          <div className="text-sm text-muted-foreground">Uncertainty: {(confidence.uncertainty * 100).toFixed(1)}%</div>
          <div className="mt-3 h-2 w-full bg-muted rounded">
            <div
              className="h-2 bg-emerald-500 rounded"
              style={{ width: `${Math.min(confidence.mean * 100, 100)}%` }}
            />
          </div>
        </Card>

        <Card title="Risk" subtitle="VaR / Drawdown / Beta">
          <div className="space-y-1 text-sm">
            <div className="flex justify-between"><span>VaR</span><span>{formatPct(risk.varPct)}</span></div>
            <div className="flex justify-between"><span>Drawdown</span><span>{formatPct(risk.drawdownPct)}</span></div>
            <div className="flex justify-between"><span>Beta</span><span>{risk.beta.toFixed(2)}</span></div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-2">
        <div className="text-sm text-muted-foreground">{subtitle}</div>
        <div className="text-lg font-semibold">{title}</div>
      </div>
      {children}
    </div>
  );
}
