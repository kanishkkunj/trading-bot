'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchCorrelationMatrix } from '@/lib/api/research-analytics';

export function CorrelationMatrix() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['correlation-matrix'],
    queryFn: fetchCorrelationMatrix,
  });

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;
  if (error) return <div className="text-red-500">Failed to load correlation matrix.</div>;
  if (!data || !data.length) return <div className="text-muted-foreground">No correlation data.</div>;

  const features = data.length ? Object.keys(data[0]).filter((k) => k !== 'feature') : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Correlation Matrix</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-auto">
          <table className="min-w-full text-xs">
            <thead>
              <tr>
                <th className="text-left">Feature</th>
                {features.map((f) => (
                  <th key={f} className="text-right">{f}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row: any) => (
                <tr key={row.feature}>
                  <td className="font-medium">{row.feature}</td>
                  {features.map((f) => (
                    <td key={f} className="text-right">{row[f]?.toFixed(2)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
