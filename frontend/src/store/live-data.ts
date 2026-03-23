import { create } from 'zustand';

export type LivePoint = { ts: number; value: number };
export type Position = { symbol: string; qty: number; avgPrice: number; pnl: number };
export type Quote = { symbol: string; bid: number; ask: number; last: number; ts: number };

export type RiskSnapshot = {
  varPct: number;
  drawdownPct: number;
  beta: number;
};

export type ConfidenceSnapshot = {
  mean: number;
  uncertainty: number;
};

export type RegimeSnapshot = {
  label: string;
  history: LivePoint[];
};

export type LiveDataState = {
  pnlSeries: LivePoint[];
  positions: Record<string, Position>;
  quotes: Record<string, Quote>;
  risk: RiskSnapshot;
  confidence: ConfidenceSnapshot;
  regime: RegimeSnapshot;
  setPnlPoint: (p: LivePoint) => void;
  setPosition: (p: Position) => void;
  setQuote: (q: Quote) => void;
  setRisk: (r: Partial<RiskSnapshot>) => void;
  setConfidence: (c: Partial<ConfidenceSnapshot>) => void;
  setRegime: (label: string, ts: number) => void;
  reset: () => void;
};

const keepLatest = (arr: LivePoint[], max: number) => {
  const next = [...arr];
  if (next.length > max) {
    return next.slice(next.length - max);
  }
  return next;
};

export const useLiveDataStore = create<LiveDataState>((set, get) => ({
  pnlSeries: [],
  positions: {},
  quotes: {},
  risk: { varPct: 0, drawdownPct: 0, beta: 0 },
  confidence: { mean: 0, uncertainty: 0 },
  regime: { label: 'neutral', history: [] },
  setPnlPoint: (p) =>
    set((state) => ({ pnlSeries: keepLatest([...state.pnlSeries, p], 1000) })),
  setPosition: (p) =>
    set((state) => ({ positions: { ...state.positions, [p.symbol]: p } })),
  setQuote: (q) =>
    set((state) => ({ quotes: { ...state.quotes, [q.symbol]: q } })),
  setRisk: (r) => set((state) => ({ risk: { ...state.risk, ...r } })),
  setConfidence: (c) => set((state) => ({ confidence: { ...state.confidence, ...c } })),
  setRegime: (label, ts) =>
    set((state) => ({
      regime: {
        label,
        history: keepLatest([...state.regime.history, { ts, value: labelToNumber(label) }], 500),
      },
    })),
  reset: () =>
    set({
      pnlSeries: [],
      positions: {},
      quotes: {},
      risk: { varPct: 0, drawdownPct: 0, beta: 0 },
      confidence: { mean: 0, uncertainty: 0 },
      regime: { label: 'neutral', history: [] },
    }),
}));

const labelMap: Record<string, number> = {
  bull: 1,
  bear: -1,
  neutral: 0,
};

function labelToNumber(label: string) {
  return labelMap[label] ?? 0;
}
