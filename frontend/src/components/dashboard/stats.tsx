'use client';

import { usePortfolio } from '@/hooks/use-portfolio';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatCurrency, formatPercentage } from '@/lib/utils';
import { TrendingUp, TrendingDown, Wallet, Activity, Banknote } from 'lucide-react';

export function DashboardStats() {
  const { summary, pnl, isLoading } = usePortfolio();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i} className="animate-pulse">
            <CardHeader className="pb-2">
              <div className="h-4 w-24 bg-muted rounded" />
            </CardHeader>
            <CardContent>
              <div className="h-8 w-32 bg-muted rounded" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const stats = [
    {
      title: 'Initial Capital',
      value: formatCurrency(pnl?.initial_capital || 0),
      icon: Wallet,
    },
    {
      title: 'Equity (Cash + Positions)',
      value: formatCurrency(pnl?.equity || 0),
      icon: Banknote,
      trend: pnl?.cash || 0,
      positive: true,
    },
    {
      title: 'Cash Available',
      value: formatCurrency(pnl?.cash || 0),
      icon: Wallet,
      trend: pnl?.long_exposure ? -pnl.long_exposure : 0,
      positive: true,
    },
    {
      title: 'Open Positions',
      value: summary?.open_positions?.toString() || '0',
      icon: Activity,
    },
    {
      title: 'Total P&L',
      value: formatCurrency(summary?.total_pnl || 0),
      icon: summary?.total_pnl && summary.total_pnl >= 0 ? TrendingUp : TrendingDown,
      trend: summary?.total_pnl || 0,
      positive: summary?.total_pnl ? summary.total_pnl >= 0 : true,
    },
    {
      title: 'Total P&L %',
      value: `${(pnl?.total_pnl_pct ?? 0).toFixed(2)}%`,
      icon: summary?.total_pnl && summary.total_pnl >= 0 ? TrendingUp : TrendingDown,
      trend: pnl?.total_pnl_pct || 0,
      positive: (pnl?.total_pnl_pct || 0) >= 0,
    },
    {
      title: 'Realized P&L',
      value: formatCurrency(summary?.total_realized_pnl || 0),
      icon: summary?.total_realized_pnl && summary.total_realized_pnl >= 0 ? TrendingUp : TrendingDown,
      trend: summary?.total_realized_pnl || 0,
      positive: summary?.total_realized_pnl ? summary.total_realized_pnl >= 0 : true,
    },
    {
      title: 'Unrealized P&L',
      value: formatCurrency(summary?.total_unrealized_pnl || 0),
      icon: summary?.total_unrealized_pnl && summary.total_unrealized_pnl >= 0 ? TrendingUp : TrendingDown,
      trend: summary?.total_unrealized_pnl || 0,
      positive: summary?.total_unrealized_pnl ? summary.total_unrealized_pnl >= 0 : true,
    },
    {
      title: 'Daily P&L',
      value: formatCurrency(pnl?.daily_pnl || 0),
      icon: pnl?.daily_pnl && pnl.daily_pnl >= 0 ? TrendingUp : TrendingDown,
      trend: pnl?.daily_pnl || 0,
      positive: pnl?.daily_pnl ? pnl.daily_pnl >= 0 : true,
    },
    {
      title: 'Daily P&L %',
      value: `${(pnl?.daily_pnl_pct ?? 0).toFixed(2)}%`,
      icon: pnl?.daily_pnl && pnl.daily_pnl >= 0 ? TrendingUp : TrendingDown,
      trend: pnl?.daily_pnl_pct || 0,
      positive: (pnl?.daily_pnl_pct || 0) >= 0,
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat, index) => {
        const Icon = stat.icon;
        return (
          <Card key={index}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
              <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              {stat.trend !== undefined && (
                <p
                  className={`text-xs ${
                    stat.positive ? 'text-green-500' : 'text-red-500'
                  }`}
                >
                  {stat.positive ? '+' : ''}
                  {formatCurrency(stat.trend)}
                </p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
