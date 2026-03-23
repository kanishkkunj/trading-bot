'use client';

import React, { useState } from 'react';
import { useOrders } from '@/hooks/use-orders';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatCurrency, formatDate } from '@/lib/utils';
import { RefreshCw } from 'lucide-react';

const statusColors: Record<string, 'default' | 'secondary' | 'destructive' | 'success'> = {
  PENDING: 'secondary',
  PLACED: 'default',
  PARTIAL_FILL: 'default',
  FILLED: 'success',
  REJECTED: 'destructive',
  CANCELLED: 'destructive',
  EXPIRED: 'destructive',
};

export default function OrdersPage() {
  const {
    orders,
    total,
    isLoading,
    cancelOrder,
    createOrder,
    runPaperTrader,
    isRunningPaperTrader,
  } = useOrders();
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [form, setForm] = useState({
    symbol: 'RELIANCE.NS',
    side: 'BUY',
    orderType: 'MARKET',
    quantity: 1,
    price: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      const payload: any = {
        symbol: form.symbol.trim(),
        side: form.side,
        order_type: form.orderType,
        quantity: Number(form.quantity),
      };
      if (form.orderType === 'LIMIT') {
        payload.price = form.price ? Number(form.price) : undefined;
        if (!payload.price) {
          throw new Error('Limit price is required for LIMIT orders');
        }
      }
      await createOrder(payload);
      setForm((prev) => ({ ...prev, price: '', quantity: 1 }));
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || err?.message || 'Order failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (orderId: string) => {
    setCancellingId(orderId);
    try {
      await cancelOrder(orderId);
    } finally {
      setCancellingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Orders</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => runPaperTrader(5)}
            disabled={isRunningPaperTrader}
          >
            {isRunningPaperTrader ? 'Running...' : 'Run Paper Trader'}
          </Button>
          <Button
            variant="outline"
            onClick={() => window.location.reload()}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Place Paper Trade</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 md:grid-cols-5" onSubmit={handleSubmit}>
            <div className="md:col-span-2">
              <label className="text-sm font-medium">Symbol</label>
              <Input
                value={form.symbol}
                onChange={(e) => setForm({ ...form, symbol: e.target.value })}
                placeholder="e.g. RELIANCE.NS"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium">Side</label>
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={form.side}
                onChange={(e) => setForm({ ...form, side: e.target.value })}
              >
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium">Type</label>
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                value={form.orderType}
                onChange={(e) => setForm({ ...form, orderType: e.target.value })}
              >
                <option value="MARKET">MARKET</option>
                <option value="LIMIT">LIMIT</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium">Quantity</label>
              <Input
                type="number"
                min={1}
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium">Limit Price (₹)</label>
              <Input
                type="number"
                step="0.01"
                value={form.price}
                onChange={(e) => setForm({ ...form, price: e.target.value })}
                disabled={form.orderType === 'MARKET'}
                placeholder={form.orderType === 'MARKET' ? 'Not needed' : 'Enter price'}
              />
            </div>
            {formError && (
              <div className="md:col-span-5 text-sm text-red-500">{formError}</div>
            )}
            <div className="md:col-span-5 flex justify-end">
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Placing...' : 'Place Order'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>All Orders ({total})</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-12 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : orders.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No orders yet
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Quantity</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Time</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
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
                    <TableCell>{order.order_type}</TableCell>
                    <TableCell>
                      {order.filled_quantity}/{order.quantity}
                    </TableCell>
                    <TableCell>
                      {order.average_price
                        ? formatCurrency(order.average_price)
                        : order.price
                        ? formatCurrency(order.price)
                        : '-'}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusColors[order.status] || 'default'}>
                        {order.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{formatDate(order.created_at)}</TableCell>
                    <TableCell>
                      {(order.status === 'PENDING' || order.status === 'PLACED') && (
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => handleCancel(order.id)}
                          disabled={cancellingId === order.id}
                        >
                          {cancellingId === order.id ? 'Cancelling...' : 'Cancel'}
                        </Button>
                      )}
                    </TableCell>
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
