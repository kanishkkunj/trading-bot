'use client';

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip } from 'recharts';
import { runBacktest } from '@/lib/api/strategies';

export function BacktestPreview() {
  const [params, setParams] = useState('');
  const [equity, setEquity] = useState<{ ts: string; equity: number }[]>([]);
  const mut = useMutation({
    mutationFn: () => runBacktest(params),
    onSuccess: (data) => setEquity(data?.equity_curve ?? []),
  });

  return (
    <Card title="Backtest Preview" subtitle="Test parameters before deployment">
      <div className="space-y-3">
        <textarea
          className="w-full rounded border border-border bg-background px-3 py-2 text-sm h-28"
          placeholder='Params JSON, e.g. {"lookback":100,"threshold":0.2}'
          value={params}
          onChange={(e) => setParams(e.target.value)}
        />
        <button
          className="px-3 py-2 rounded bg-blue-600 text-white text-sm disabled:opacity-50"
          onClick={() => mut.mutate()}
          disabled={mut.isPending}
        >
          Run Backtest
        </button>
        {mut.isError && <div className="text-xs text-rose-400">Backtest failed</div>}
        <div className="h-48">
          <ResponsiveContainer>
            <LineChart data={equity}>
              <XAxis dataKey="ts" hide />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip formatter={(v: any) => Number(v).toFixed(2)} />
              <Line type="monotone" dataKey="equity" stroke="#22c55e" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </Card>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
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
