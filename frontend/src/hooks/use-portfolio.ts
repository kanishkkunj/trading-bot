'use client';

import { useQuery } from '@tanstack/react-query';
import { portfolioApi } from '@/lib/api';

export function usePortfolio() {
  const positionsQuery = useQuery({
    queryKey: ['positions'],
    queryFn: async () => {
      const response = await portfolioApi.getPositions();
      return response.data;
    },
  });

  const summaryQuery = useQuery({
    queryKey: ['portfolio-summary'],
    queryFn: async () => {
      const response = await portfolioApi.getSummary();
      return response.data;
    },
  });

  const pnlQuery = useQuery({
    queryKey: ['pnl'],
    queryFn: async () => {
      const response = await portfolioApi.getPnL();
      return response.data;
    },
  });

  return {
    positions: positionsQuery.data || [],
    summary: summaryQuery.data,
    pnl: pnlQuery.data,
    isLoading: positionsQuery.isLoading || summaryQuery.isLoading || pnlQuery.isLoading,
    error: positionsQuery.error || summaryQuery.error || pnlQuery.error,
  };
}
