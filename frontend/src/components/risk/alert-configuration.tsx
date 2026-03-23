'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import axios from 'axios';

async function fetchAlertConfig() {
  const res = await axios.get((process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/risk/alert-config');
  return res.data || {};
}

async function updateAlertConfig(config: any) {
  await axios.post((process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/risk/alert-config', config);
}

export function AlertConfiguration() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['alert-config'],
    queryFn: fetchAlertConfig,
  });
  const mutation = useMutation({
    mutationFn: updateAlertConfig,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-config'] }),
  });
  const [form, setForm] = useState<any>(data || {});

  // Update form state when data loads
  React.useEffect(() => {
    setForm(data || {});
  }, [data]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutation.mutate(form);
  }

  if (isLoading) return <div className="h-32 animate-pulse bg-muted rounded" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Alert Configuration</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-1">Max Daily Loss (%)</label>
            <Input name="max_daily_loss" type="number" value={form.max_daily_loss || ''} onChange={handleChange} />
          </div>
          <div>
            <label className="block text-sm mb-1">Max Position Size</label>
            <Input name="max_position_size" type="number" value={form.max_position_size || ''} onChange={handleChange} />
          </div>
          <div>
            <label className="block text-sm mb-1">Notification Email</label>
            <Input name="notification_email" type="email" value={form.notification_email || ''} onChange={handleChange} />
          </div>
          <div>
            <label className="block text-sm mb-1">Enable SMS Alerts</label>
            <Input name="enable_sms" type="checkbox" checked={!!form.enable_sms} onChange={e => setForm({ ...form, enable_sms: e.target.checked })} />
          </div>
          <Button type="submit" disabled={mutation.status === 'pending'}>
            Save Configuration
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
