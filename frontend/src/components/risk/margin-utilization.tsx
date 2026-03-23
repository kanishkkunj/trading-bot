'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import axios from 'axios';

async function fetchMarginUtilization() {
  const res = await axios.get((process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/risk/margin-utilization');
  return res.data || {};
}

export function MarginUtilization() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['margin-utilization'],
    queryFn: fetchMarginUtilization,
  });

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;
  if (error) return <div className="text-red-500">Failed to load margin utilization.</div>;
  if (!data) return <div className="text-muted-foreground">No margin data.</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Margin Utilization & Buying Power</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <div className="flex justify-between">
            <span>Margin Used</span>
            <span className="font-mono">{data.margin_used?.toFixed(2) ?? '-'}</span>
          </div>
          <div className="flex justify-between">
            <span>Margin Available</span>
            <span className="font-mono">{data.margin_available?.toFixed(2) ?? '-'}</span>
          </div>
          <div className="flex justify-between">
            <span>Buying Power</span>
            <span className="font-mono">{data.buying_power?.toFixed(2) ?? '-'}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
