'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import axios from 'axios';

async function fetchRiskReport(dateRange: { start: string; end: string }) {
  const res = await axios.get((process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/risk/report', { params: dateRange });
  return res.data || [];
}

export function RiskReports() {
  const [range, setRange] = useState({ start: '', end: '' });
  const [enabled, setEnabled] = useState(false);
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['risk-report', range],
    queryFn: () => fetchRiskReport(range),
    enabled,
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setEnabled(true);
    refetch();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk Reports</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex gap-2 mb-4">
          <input type="date" value={range.start} onChange={e => setRange({ ...range, start: e.target.value })} className="border rounded px-2 py-1" />
          <input type="date" value={range.end} onChange={e => setRange({ ...range, end: e.target.value })} className="border rounded px-2 py-1" />
          <Button type="submit">Generate</Button>
        </form>
        {isLoading ? (
          <div className="h-32 animate-pulse bg-muted rounded" />
        ) : data && data.length ? (
          <ul className="space-y-2">
            {data.map((item: any, idx: number) => (
              <li key={idx} className="flex justify-between">
                <span>{item.date}</span>
                <span className="font-mono">{item.summary}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-muted-foreground">No report data.</div>
        )}
      </CardContent>
    </Card>
  );
}
