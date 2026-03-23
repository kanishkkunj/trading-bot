'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchRegimeTransitions } from '@/lib/api/research-analytics';

export function RegimeTransitions() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['regime-transitions'],
    queryFn: fetchRegimeTransitions,
  });

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;
  if (error) return <div className="text-red-500">Failed to load regime transitions.</div>;
  if (!data || !data.length) return <div className="text-muted-foreground">No regime transition data.</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Regime Transitions</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {data.map((item: any, idx: number) => (
            <li key={idx} className="flex justify-between">
              <span>{item.timestamp}</span>
              <span className="capitalize">{item.from} → {item.to}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
