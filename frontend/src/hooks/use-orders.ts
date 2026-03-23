'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ordersApi, paperApi } from '@/lib/api';

export function useOrders() {
  const queryClient = useQueryClient();

  const ordersQuery = useQuery({
    queryKey: ['orders'],
    queryFn: async () => {
      const response = await ordersApi.getOrders();
      return response.data;
    },
  });

  const createOrderMutation = useMutation({
    mutationFn: ordersApi.createOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['positions'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio-summary'] });
      queryClient.invalidateQueries({ queryKey: ['pnl'] });
    },
  });

  const cancelOrderMutation = useMutation({
    mutationFn: (id: string) => ordersApi.cancelOrder(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });

  const runPaperTraderMutation = useMutation({
    mutationFn: (top_k: number = 5) => paperApi.runPaperTrader(top_k),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['signals'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio-summary'] });
      queryClient.invalidateQueries({ queryKey: ['positions'] });
      queryClient.invalidateQueries({ queryKey: ['pnl'] });
    },
  });

  return {
    orders: ordersQuery.data?.orders || [],
    total: ordersQuery.data?.total || 0,
    isLoading: ordersQuery.isLoading,
    error: ordersQuery.error,
    createOrder: createOrderMutation.mutateAsync,
    cancelOrder: cancelOrderMutation.mutateAsync,
    runPaperTrader: runPaperTraderMutation.mutateAsync,
    isRunningPaperTrader: runPaperTraderMutation.isPending,
  };
}
