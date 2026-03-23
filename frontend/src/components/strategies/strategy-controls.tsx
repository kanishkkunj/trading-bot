'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { startStrategy, stopStrategy } from '@/lib/api/strategies';

export function StrategyControls() {
  const [strategyId, setStrategyId] = useState('');
  const queryClient = useQueryClient();

  const startMut = useMutation({
    mutationFn: () => startStrategy(strategyId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategies'] }),
  });

  const stopMut = useMutation({
    mutationFn: () => stopStrategy(strategyId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategies'] }),
  });

  return (
    <Card title="Controls" subtitle="Start or stop a strategy">
      <div className="space-y-3">
        <input
          className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
          placeholder="Strategy ID"
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value)}
        />
        <div className="flex gap-2">
          <button
            className="px-3 py-2 rounded bg-emerald-600 text-white text-sm disabled:opacity-50"
            onClick={() => startMut.mutate()}
            disabled={!strategyId || startMut.isPending}
          >
            Start
          </button>
          <button
            className="px-3 py-2 rounded bg-rose-600 text-white text-sm disabled:opacity-50"
            onClick={() => stopMut.mutate()}
            disabled={!strategyId || stopMut.isPending}
          >
            Stop
          </button>
        </div>
        {(startMut.isError || stopMut.isError) && (
          <div className="text-xs text-rose-400">Action failed</div>
        )}
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
