'use client';

import { useLiveDataStore } from '@/store/live-data';

export function MarketTape() {
  const { quotes } = useLiveDataStore();
  const rows = Object.values(quotes);

  if (!rows.length) {
    return <EmptyState message="No live quotes" />;
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-2">
        <div className="text-sm text-muted-foreground">Live market data</div>
        <div className="text-lg font-semibold">Market Tape</div>
      </div>
      <div className="overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="text-muted-foreground">
            <tr>
              <th className="text-left py-2 pr-4">Symbol</th>
              <th className="text-right py-2 pr-4">Bid</th>
              <th className="text-right py-2 pr-4">Ask</th>
              <th className="text-right py-2 pr-4">Last</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.symbol} className="border-t border-border/50">
                <td className="py-2 pr-4 font-medium">{row.symbol}</td>
                <td className="py-2 pr-4 text-right">{row.bid?.toFixed(2) ?? '-'}</td>
                <td className="py-2 pr-4 text-right">{row.ask?.toFixed(2) ?? '-'}</td>
                <td className="py-2 pr-4 text-right">{row.last?.toFixed(2) ?? '-'}</td>
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
