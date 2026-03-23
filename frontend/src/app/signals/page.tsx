'use client';

import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useOrders } from '@/hooks/use-orders';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatDate, formatPercentage } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

export default function SignalsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['signals'],
    queryFn: async () => {
      const response = await api.get('/signals/');
      return response.data;
    },
  });

  const { runPaperTrader, isRunningPaperTrader } = useOrders();

  const signals = data?.signals || [];

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Trading Signals</h1>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Recent Signals</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => runPaperTrader(5)}
              disabled={isRunningPaperTrader}
            >
              {isRunningPaperTrader ? 'Running...' : 'Run Paper Trader'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-12 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : signals.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No signals generated yet
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {signals.map((signal: any) => (
                  <TableRow key={signal.id}>
                    <TableCell className="font-medium">{signal.symbol}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        {signal.action === 'BUY' && (
                          <TrendingUp className="h-4 w-4 text-green-500" />
                        )}
                        {signal.action === 'SELL' && (
                          <TrendingDown className="h-4 w-4 text-red-500" />
                        )}
                        {signal.action === 'HOLD' && (
                          <Minus className="h-4 w-4 text-gray-500" />
                        )}
                        <span
                          className={
                            signal.action === 'BUY'
                              ? 'text-green-500'
                              : signal.action === 'SELL'
                              ? 'text-red-500'
                              : 'text-gray-500'
                          }
                        >
                          {signal.action}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary"
                            style={{ width: `${signal.confidence * 100}%` }}
                          />
                        </div>
                        <span className="text-sm">
                          {formatPercentage(signal.confidence * 100)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>{signal.model_version}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          signal.status === 'EXECUTED'
                            ? 'success'
                            : signal.status === 'PENDING'
                            ? 'secondary'
                            : 'default'
                        }
                      >
                        {signal.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatDate(signal.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
