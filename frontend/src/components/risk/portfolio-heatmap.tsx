'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchCorrelationMatrix } from '@/lib/api/research-analytics';
import { ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts';

type CorrelationMatrixRow = { feature: string } & { [key: string]: number | string };

export function PortfolioHeatmap() {
  const { data, isLoading, error } = useQuery<CorrelationMatrixRow[]>({
    queryKey: ['correlation-matrix'],
    queryFn: fetchCorrelationMatrix,
  });

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;
  if (error) return <div className="text-red-500">Failed to load heatmap.</div>;
  if (!data || !Array.isArray(data) || data.length === 0) return <div className="text-muted-foreground">No correlation data.</div>;

  const features = data.length ? Object.keys(data[0]).filter((k) => k !== 'feature') : [];
  const heatmapData = features.length && Array.isArray(data)
    ? features.map((row, i) =>
        features.map((col, j) => ({ x: i, y: j, value: typeof data[i][col] === 'number' ? data[i][col] : NaN }))
      ).flat()
    : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Portfolio Correlation Heatmap</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-auto">
          {/* HeatMap is not available in recharts. Replace with a custom SVG or another library if needed. */}
          <div className="flex items-center justify-center h-48 text-muted-foreground">
            Heatmap visualization not supported. Please implement with a custom SVG or supported library.
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
