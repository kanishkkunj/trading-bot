'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import axios from 'axios';

const COLORS = ['#34d399', '#fbbf24', '#60a5fa', '#f87171', '#a78bfa', '#f472b6', '#facc15', '#38bdf8'];

async function fetchExposureBySector() {
  const res = await axios.get((process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/risk/exposure-sector');
  return res.data || [];
}

export function ExposureBySector() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['exposure-by-sector'],
    queryFn: fetchExposureBySector,
  });

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;
  if (error) return <div className="text-red-500">Failed to load sector exposure.</div>;
  if (!data || !data.length) return <div className="text-muted-foreground">No sector exposure data.</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Exposure by Sector/Factor</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie data={data} dataKey="exposure" nameKey="sector" cx="50%" cy="50%" outerRadius={100} label>
              {data.map((entry: any, idx: number) => (
                <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(v: number) => v.toFixed(2)} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
