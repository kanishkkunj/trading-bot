'use client';

import { useLiveDataStore } from '@/store/live-data';

export function PositionsTable() {
  const { positions } = useLiveDataStore();
  const rows = Object.values(positions);

  if (!rows.length) {
    return <EmptyState message="No open positions" />;
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-2">
        <div className="text-sm text-muted-foreground">Live positions</div>
        <div className="text-lg font-semibold">Positions</div>
      </div>
      <div className="overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="text-muted-foreground">
            <tr>
              <th className="text-left py-2 pr-4">Symbol</th>
              <th className="text-right py-2 pr-4">Qty</th>
              <th className="text-right py-2 pr-4">Avg Price</th>
              <th className="text-right py-2 pr-4">PnL</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.symbol} className="border-t border-border/50">
                <td className="py-2 pr-4 font-medium">{row.symbol}</td>
                <td className="py-2 pr-4 text-right">{row.qty}</td>
                <td className="py-2 pr-4 text-right">{row.avgPrice.toFixed(2)}</td>
                <td className={`py-2 pr-4 text-right ${row.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {row.pnl.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border/60 bg-card p-6 text-sm text-muted-foreground text-center">
      {message}
    </div>
  );
}
