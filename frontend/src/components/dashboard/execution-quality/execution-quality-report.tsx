'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { fetchExecutionQuality } from '@/lib/api/execution-quality';

export function ExecutionQualityReport() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['execution-quality'],
    queryFn: fetchExecutionQuality,
  });

  if (isLoading) {
    return <div className="h-32 animate-pulse bg-muted rounded" />;
  }
  if (error) {
    return <div className="text-red-500">Failed to load execution quality data.</div>;
  }
  if (!data || !data.length) {
    return <div className="text-muted-foreground">No execution quality data available.</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Execution Quality Report</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Order ID</TableHead>
              <TableHead>Symbol</TableHead>
              <TableHead>Side</TableHead>
              <TableHead>Qty</TableHead>
              <TableHead>Requested Price</TableHead>
              <TableHead>Fill Price</TableHead>
              <TableHead>Slippage</TableHead>
              <TableHead>Fill Rate</TableHead>
              <TableHead>Market Impact</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row: any) => (
              <TableRow key={row.order_id}>
                <TableCell>{row.order_id}</TableCell>
                <TableCell>{row.symbol}</TableCell>
                <TableCell>{row.side}</TableCell>
                <TableCell>{row.quantity}</TableCell>
                <TableCell>{row.requested_price?.toFixed(2)}</TableCell>
                <TableCell>{row.fill_price?.toFixed(2)}</TableCell>
                <TableCell className={row.slippage >= 0 ? 'text-rose-500' : 'text-emerald-500'}>
                  {row.slippage?.toFixed(2)}
                </TableCell>
                <TableCell>{(row.fill_rate * 100).toFixed(1)}%</TableCell>
                <TableCell>{row.market_impact?.toFixed(2)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
