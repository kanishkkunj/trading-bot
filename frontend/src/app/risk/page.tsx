import { RiskReports } from '@/components/risk/risk-reports';
'use client';

import { useQuery } from '@tanstack/react-query';
import { riskApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PortfolioHeatmap } from '@/components/risk/portfolio-heatmap';
import { ExposureBySector } from '@/components/risk/exposure-by-sector';
import { StressTestResults } from '@/components/risk/stress-test-results';
import { MarginUtilization } from '@/components/risk/margin-utilization';
import { AlertConfiguration } from '@/components/risk/alert-configuration';
import { KillSwitch } from '@/components/risk/kill-switch';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, Shield, TrendingDown } from 'lucide-react';

export default function RiskPage() {
  const { data: status, isLoading } = useQuery({
    queryKey: ['risk-status'],
    queryFn: async () => {
      const response = await riskApi.getStatus();
      return response.data;
    },
  });

  const { data: limits } = useQuery({
    queryKey: ['risk-limits'],
    queryFn: async () => {
      const response = await riskApi.getLimits();
      return response.data;
    },
  });

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Risk Management</h1>

      {/* Real-Time Risk Dashboard */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <PortfolioHeatmap />
        <ExposureBySector />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <StressTestResults />
        <MarginUtilization />
      </div>

      {/* Alert Configuration & Kill Switch */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AlertConfiguration />
        <KillSwitch />
      </div>

      {/* Status Overview */}
      <div className="grid gap-4 md:grid-cols-3">

      {/* Risk Reporting */}
      <div className="mt-8">
        <RiskReports />
      </div>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Shield className="h-4 w-4" />
              Risk Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge
              variant={status?.kill_switch_active ? 'destructive' : 'success'}
              className="text-lg"
            >
              {status?.kill_switch_active ? 'KILL SWITCH ACTIVE' : 'HEALTHY'}
            </Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingDown className="h-4 w-4" />
              Daily Loss
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatPercentage(status?.daily_loss_pct || 0)}
            </div>
            <p className="text-sm text-muted-foreground">
              Limit: {formatPercentage(status?.daily_loss_limit || 2)}%
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              Positions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {status?.current_positions} / {status?.max_positions}
            </div>
            <p className="text-sm text-muted-foreground">Open positions</p>
          </CardContent>
        </Card>
      </div>

      {/* Circuit Breakers */}
      <Card>
        <CardHeader>
          <CardTitle>Circuit Breakers</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            {status?.circuit_breakers &&
              Object.entries(status.circuit_breakers).map(([name, triggered]) => (
                <div
                  key={name}
                  className={`p-4 rounded-lg ${
                    triggered ? 'bg-red-500/20 text-red-500' : 'bg-green-500/20 text-green-500'
                  }`}
                >
                  <p className="font-medium capitalize">{name.replace('_', ' ')}</p>
                  <p className="text-sm">{triggered ? 'TRIGGERED' : 'OK'}</p>
                </div>
              ))}
          </div>
        </CardContent>
      </Card>

      {/* Risk Limits */}
      <Card>
        <CardHeader>
          <CardTitle>Risk Limits Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {limits &&
              Object.entries(limits).map(([key, value]) => (
                <div key={key} className="p-4 bg-muted rounded-lg">
                  <p className="text-sm text-muted-foreground capitalize">
                    {key.replace(/_/g, ' ')}
                  </p>
                  <p className="text-lg font-medium">
                    {typeof value === 'number' ? value.toFixed(2) : String(value)}
                  </p>
                </div>
              ))}
          </div>
        </CardContent>
      </Card>

      {/* Kill Switch */}
      <Card>
        <CardHeader>
          <CardTitle className="text-destructive">Emergency Kill Switch</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground mb-4">
            Activating the kill switch will immediately cancel all open orders and prevent
            new orders from being placed. Use this in case of emergency.
          </p>
          <Button variant="destructive" size="lg">
            ACTIVATE KILL SWITCH
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function formatPercentage(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}
