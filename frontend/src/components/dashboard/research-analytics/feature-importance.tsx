'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchFeatureImportance } from '@/lib/api/research-analytics';

export function FeatureImportance() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['feature-importance'],
    queryFn: fetchFeatureImportance,
  });

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;
  if (error) return <div className="text-red-500">Failed to load feature importance.</div>;
  if (!data || !data.length) return <div className="text-muted-foreground">No feature importance data.</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Feature Importance</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {data.map((item: any) => (
            <li key={item.feature} className="flex justify-between">
              <span>{item.feature}</span>
              <span className="font-mono">{item.importance.toFixed(4)}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
