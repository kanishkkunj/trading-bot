'use client';

import { useQuery } from '@tanstack/react-query';
import { Strategy } from '@/types/strategy';
import { fetchStrategies } from '@/lib/api/strategies';

export function StrategyList() {
  const { data, isLoading, isError } = useQuery<Strategy[]>({ queryKey: ['strategies'], queryFn: fetchStrategies });

  if (isLoading) return <Card title="Strategies" subtitle="Loading..." />;
  if (isError || !data) return <Card title="Strategies" subtitle="Failed to load" />;

  return (
    <Card title="Strategies" subtitle="Start/stop and monitor">
      <div className="space-y-2">
        {data.map((s) => (
          <div key={s.id} className="border border-border/60 rounded-lg p-3 flex items-center justify-between">
            <div>
              <div className="font-semibold">{s.name}</div>
              <div className="text-xs text-muted-foreground">v{s.version} · {s.description ?? 'No description'}</div>
              <div className="text-xs text-muted-foreground">Symbols: {s.symbols?.join(', ') ?? '—'}</div>
            </div>
            <StatusPill active={s.is_active} />
          </div>
        ))}
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

function StatusPill({ active }: { active: boolean }) {
  return (
    <span
      className={`px-3 py-1 text-xs rounded-full ${active ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'}`}
    >
      {active ? 'Active' : 'Inactive'}
    </span>
  );
}
