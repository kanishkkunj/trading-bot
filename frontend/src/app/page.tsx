'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/use-auth';
import { DashboardStats } from '@/components/dashboard/stats';
import { RecentOrders } from '@/components/dashboard/recent-orders';
import { PortfolioSummary } from '@/components/dashboard/portfolio-summary';
import { MarketOverview } from '@/components/dashboard/market-overview';
import { LiveDashboard } from '@/components/dashboard/live-dashboard';
import { PositionsTable } from '@/components/dashboard/positions-table';
import { MarketTape } from '@/components/dashboard/market-tape';
import { ExecutionQualityReport } from '@/components/dashboard/execution-quality/execution-quality-report';
import { FeatureImportance } from '@/components/dashboard/research-analytics/feature-importance';
import { CorrelationMatrix } from '@/components/dashboard/research-analytics/correlation-matrix';
import { RegimeTransitions } from '@/components/dashboard/research-analytics/regime-transitions';
import { SignalHistory } from '@/components/dashboard/research-analytics/signal-history';
import { MiroFishAdvisoryCard } from '@/components/dashboard/mirofish-advisory-card';

export default function DashboardPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-2">
          <span className="px-3 py-1 text-sm bg-green-500/20 text-green-500 rounded-full">
            Paper Trading
          </span>
        </div>
      </div>

      <LiveDashboard />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <DashboardStats />
        </div>
        <MiroFishAdvisoryCard />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <PositionsTable />
        <MarketTape />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <PortfolioSummary />
        <MarketOverview />
      </div>

      <RecentOrders />
      <ExecutionQualityReport />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <FeatureImportance />
        <CorrelationMatrix />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RegimeTransitions />
        <SignalHistory />
      </div>
    </div>
  );
}
