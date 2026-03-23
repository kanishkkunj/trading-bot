'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { backtestApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { formatCurrency, formatPercentage } from '@/lib/utils';
import { Loader2, Play } from 'lucide-react';

export default function BacktestPage() {
  const [symbol, setSymbol] = useState('RELIANCE.NS');
  const [days, setDays] = useState(365);
  const [result, setResult] = useState<any>(null);

  const backtestMutation = useMutation({
    mutationFn: () => backtestApi.quickBacktest(symbol, days),
    onSuccess: (response) => {
      setResult(response.data);
    },
  });

  const handleRunBacktest = () => {
    backtestMutation.mutate();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Backtest</h1>

      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="symbol">Symbol</Label>
              <Input
                id="symbol"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="RELIANCE.NS"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="days">Days</Label>
              <Input
                id="days"
                type="number"
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                min={30}
                max={3650}
              />
            </div>
            <div className="flex items-end">
              <Button
                onClick={handleRunBacktest}
                disabled={backtestMutation.isPending}
                className="w-full"
              >
                {backtestMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Run Backtest
                  </>
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Results - {result.symbol}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-4">
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Total Return</p>
                <p
                  className={`text-2xl font-bold ${
                    result.metrics.total_return_pct >= 0
                      ? 'text-green-500'
                      : 'text-red-500'
                  }`}
                >
                  {formatPercentage(result.metrics.total_return_pct)}
                </p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Total Trades</p>
                <p className="text-2xl font-bold">{result.metrics.total_trades}</p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Win Rate</p>
                <p className="text-2xl font-bold">
                  {formatPercentage(result.metrics.win_rate_pct)}
                </p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Max Drawdown</p>
                <p className="text-2xl font-bold text-red-500">
                  {formatPercentage(-result.metrics.max_drawdown_pct)}
                </p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Sharpe Ratio</p>
                <p className="text-2xl font-bold">
                  {result.metrics.sharpe_ratio.toFixed(2)}
                </p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Profit Factor</p>
                <p className="text-2xl font-bold">
                  {result.metrics.profit_factor.toFixed(2)}
                </p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Initial Capital</p>
                <p className="text-2xl font-bold">
                  {formatCurrency(result.metrics.initial_capital)}
                </p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Final Equity</p>
                <p className="text-2xl font-bold">
                  {formatCurrency(result.metrics.final_equity)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
