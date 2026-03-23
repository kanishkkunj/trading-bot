'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import axios from 'axios';

async function fetchStressTestResults() {
  const res = await axios.get((process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/risk/stress-test');
  return res.data || [];
}

export function StressTestResults() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['stress-test-results'],
    queryFn: fetchStressTestResults,
  });

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;
  if (error) return <div className="text-red-500">Failed to load stress test results.</div>;
  if (!data || !data.length) return <div className="text-muted-foreground">No stress test data.</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stress Test Results</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {data.map((item: any, idx: number) => (
            <li key={idx} className="flex justify-between">
              <span>{item.scenario}</span>
              <span className={item.pnl < 0 ? 'text-rose-500' : 'text-emerald-500'}>{item.pnl.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
