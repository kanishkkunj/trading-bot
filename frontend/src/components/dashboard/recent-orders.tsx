'use client';

import Link from 'next/link';
import { useOrders } from '@/hooks/use-orders';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatCurrency, formatDate } from '@/lib/utils';
import { ArrowRight } from 'lucide-react';

const statusColors: Record<string, 'default' | 'secondary' | 'destructive' | 'success'> = {
  PENDING: 'secondary',
  PLACED: 'default',
  PARTIAL_FILL: 'default',
  FILLED: 'success',
  REJECTED: 'destructive',
  CANCELLED: 'destructive',
  EXPIRED: 'destructive',
};

export function RecentOrders() {
  const { orders, isLoading } = useOrders();

  const recentOrders = orders.slice(0, 5);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Recent Orders</CardTitle>
        <Link href="/orders">
          <Button variant="ghost" size="sm">
            View All
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-muted rounded animate-pulse" />
            ))}
          </div>
        ) : recentOrders.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No orders yet. Place your first order to get started.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Side</TableHead>
                <TableHead>Quantity</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentOrders.map((order) => (
                <TableRow key={order.id}>
                  <TableCell className="font-medium">{order.symbol}</TableCell>
                  <TableCell>
                    <span
                      className={
                        order.side === 'BUY' ? 'text-green-500' : 'text-red-500'
                      }
                    >
                      {order.side}
                    </span>
                  </TableCell>
                  <TableCell>{order.quantity}</TableCell>
                  <TableCell>
                    {order.average_price
                      ? formatCurrency(order.average_price)
                      : '-'}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusColors[order.status] || 'default'}>
                      {order.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{formatDate(order.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
