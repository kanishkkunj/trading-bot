'use client';

import { useEffect, useRef } from 'react';
import { useLiveDataStore, Position, Quote, LivePoint } from '@/store/live-data';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/stream';

// Expected message shape: { type: 'pnl'|'position'|'quote'|'risk'|'confidence'|'regime', payload: {...} }
export function useLiveWebSocket(enabled = true) {
  const wsRef = useRef<WebSocket | null>(null);
  const { setPnlPoint, setPosition, setQuote, setRisk, setConfidence, setRegime } = useLiveDataStore();

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let reconnectTimer: NodeJS.Timeout | null = null;

    const connect = () => {
      if (!alive) return;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleMessage(msg, { setPnlPoint, setPosition, setQuote, setRisk, setConfidence, setRegime });
        } catch (err) {
          console.error('ws_parse_error', err);
        }
      };

      ws.onclose = () => {
        if (!alive) return;
        reconnectTimer = setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      alive = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [enabled, setConfidence, setPnlPoint, setPosition, setQuote, setRegime, setRisk]);
}

function handleMessage(
  msg: any,
  handlers: {
    setPnlPoint: (p: LivePoint) => void;
    setPosition: (p: Position) => void;
    setQuote: (q: Quote) => void;
    setRisk: (r: any) => void;
    setConfidence: (c: any) => void;
    setRegime: (label: string, ts: number) => void;
  },
) {
  const { type, payload } = msg || {};
  if (!type) return;
  switch (type) {
    case 'pnl':
      if (payload?.ts && payload?.value !== undefined) handlers.setPnlPoint({ ts: payload.ts, value: payload.value });
      break;
    case 'position':
      if (payload?.symbol) handlers.setPosition(payload as Position);
      break;
    case 'quote':
      if (payload?.symbol) handlers.setQuote(payload as Quote);
      break;
    case 'risk':
      handlers.setRisk(payload || {});
      break;
    case 'confidence':
      handlers.setConfidence(payload || {});
      break;
    case 'regime':
      if (payload?.label && payload?.ts) handlers.setRegime(payload.label, payload.ts);
      break;
    default:
      break;
  }
}
