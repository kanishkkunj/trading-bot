'use client';

import { useEffect, useMemo, useState } from 'react';

type AdvisoryPayload = {
  success: boolean;
  degraded: boolean;
  simulation_id?: string;
  symbol?: string;
  status?: string;
  advisory?: {
    scenario_bias: string;
    tail_risk_score: number;
    narrative_confidence: number;
    summary: string;
  };
};

const TRADE_API_URL = process.env.NEXT_PUBLIC_TRADE_API_URL || 'http://localhost:3001';

function getBiasTone(bias: string | undefined): string {
  const normalized = String(bias || 'neutral').toLowerCase();
  if (normalized === 'risk_off') return 'text-red-500';
  if (normalized === 'risk_on') return 'text-green-500';
  return 'text-amber-500';
}

export function MiroFishAdvisoryCard() {
  const [data, setData] = useState<AdvisoryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const fetchAdvisory = async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(`${TRADE_API_URL}/api/mirofish/advisory?symbol=NIFTY`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch advisory: ${response.status}`);
        }

        const payload = (await response.json()) as AdvisoryPayload;
        if (mounted) {
          setData(payload);
        }
      } catch (err) {
        if (mounted) {
          const message = err instanceof Error ? err.message : 'Failed to fetch advisory';
          setError(message);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    fetchAdvisory();
    const interval = window.setInterval(fetchAdvisory, 60_000);

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const tailRiskPct = useMemo(() => {
    const score = Number(data?.advisory?.tail_risk_score ?? 0.5);
    return `${(score * 100).toFixed(1)}%`;
  }, [data]);

  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-2">
        <div className="text-sm text-muted-foreground">MiroFish Scenario Layer</div>
        <div className="text-lg font-semibold">Advisory Snapshot</div>
      </div>

      {loading && <div className="text-sm text-muted-foreground">Loading advisory...</div>}

      {!loading && error && (
        <div className="text-sm text-red-500">
          {error}
        </div>
      )}

      {!loading && !error && (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span>Status</span>
            <span className={data?.degraded ? 'text-amber-500' : 'text-green-500'}>
              {data?.status || 'unknown'}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Bias</span>
            <span className={getBiasTone(data?.advisory?.scenario_bias)}>
              {data?.advisory?.scenario_bias || 'neutral'}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Tail Risk</span>
            <span>{tailRiskPct}</span>
          </div>
          <div className="flex justify-between">
            <span>Narrative Confidence</span>
            <span>{((data?.advisory?.narrative_confidence ?? 0) * 100).toFixed(1)}%</span>
          </div>
          <div className="pt-2 text-xs text-muted-foreground">
            {data?.advisory?.summary || 'No advisory summary available.'}
          </div>
        </div>
      )}
    </div>
  );
}
