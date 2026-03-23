'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/use-auth';
import { StrategyList } from '@/components/strategies/strategy-list';
import { StrategyControls } from '@/components/strategies/strategy-controls';
import { BacktestPreview } from '@/components/strategies/backtest-preview';

export default function StrategiesPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading || !isAuthenticated) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Strategies</h1>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-4">
          <StrategyList />
        </div>
        <div className="space-y-4">
          <StrategyControls />
          <BacktestPreview />
        </div>
      </div>
    </div>
  );
}
