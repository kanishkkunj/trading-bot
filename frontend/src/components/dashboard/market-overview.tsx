'use client';

import { useQuery } from '@tanstack/react-query';
import { marketApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatCurrency, formatPercentage } from '@/lib/utils';
import { TrendingUp, TrendingDown } from 'lucide-react';

export function MarketOverview() {
  const { data, isLoading } = useQuery({
    queryKey: ['nifty50'],
    queryFn: async () => {
      const response = await marketApi.getNifty50();
      return response.data;
    },
  });

  const topStocks = data?.slice(0, 5) || [];

  return (
    <Card className="h-[400px]">
      <CardHeader>
        <CardTitle>Market Overview</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-muted rounded animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {topStocks.map((stock: any) => (
              <div
                key={stock.symbol}
                className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
              >
                <div>
                  <p className="font-medium">{stock.symbol.replace('.NS', '')}</p>
                  <p className="text-sm text-muted-foreground">
                    {formatCurrency(stock.last_price)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {stock.change >= 0 ? (
                    <TrendingUp className="h-4 w-4 text-green-500" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-red-500" />
                  )}
                  <span
                    className={
                      stock.change >= 0 ? 'text-green-500' : 'text-red-500'
                    }
                  >
                    {formatPercentage(stock.change_percent)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
