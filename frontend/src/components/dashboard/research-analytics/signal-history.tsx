'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchSignalHistory } from '@/lib/api/research-analytics';

export function SignalHistory() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['signal-history'],
    queryFn: fetchSignalHistory,
  });

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;
  if (error) return <div className="text-red-500">Failed to load signal history.</div>;
  if (!data || !data.length) return <div className="text-muted-foreground">No signal history data.</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Signal History</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {data.map((item: any, idx: number) => (
            <li key={idx} className="flex justify-between">
              <span>{item.timestamp}</span>
              <span className="capitalize">{item.signal}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
