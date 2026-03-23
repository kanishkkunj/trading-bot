export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
  last_login?: string;
}

export interface Order {
  id: string;
  user_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: 'MARKET' | 'LIMIT' | 'STOP_LOSS' | 'STOP_LOSS_MARKET';
  quantity: number;
  filled_quantity: number;
  price?: number;
  trigger_price?: number;
  average_price?: number;
  status: 'PENDING' | 'PLACED' | 'PARTIAL_FILL' | 'FILLED' | 'REJECTED' | 'CANCELLED' | 'EXPIRED';
  status_message?: string;
  broker_order_id?: string;
  broker: string;
  strategy_id?: string;
  signal_id?: string;
  created_at: string;
  updated_at: string;
  placed_at?: string;
  filled_at?: string;
}

export interface Position {
  id: string;
  user_id: string;
  symbol: string;
  quantity: number;
  average_entry_price: number;
  current_price?: number;
  last_price_update?: string;
  realized_pnl: number;
  unrealized_pnl: number;
  is_open: boolean;
  opened_at: string;
  closed_at?: string;
  updated_at: string;
  market_value: number;
  cost_basis: number;
}

export interface Signal {
  id: string;
  symbol: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  suggested_quantity?: number;
  suggested_price?: number;
  model_version: string;
  features_used?: string;
  status: 'PENDING' | 'EXECUTED' | 'EXPIRED' | 'REJECTED';
  status_reason?: string;
  order_id?: string;
  created_at: string;
  valid_until?: string;
  executed_at?: string;
}

export interface Candle {
  symbol: string;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface PortfolioSummary {
  total_positions: number;
  open_positions: number;
  total_market_value: number;
  total_cost_basis: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  total_pnl: number;
}

export interface PnL {
  daily_pnl: number;
  daily_pnl_pct: number;
  total_pnl: number;
  total_pnl_pct: number;
  max_drawdown: number;
  sharpe_ratio?: number;
}

export interface BacktestResult {
  status: string;
  symbol: string;
  start_date: string;
  end_date: string;
  metrics: {
    initial_capital: number;
    final_equity: number;
    total_return_pct: number;
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate_pct: number;
    max_drawdown_pct: number;
    sharpe_ratio: number;
    profit_factor: number;
  };
}

export interface RiskStatus {
  status: string;
  daily_loss_limit: number;
  current_daily_loss: number;
  daily_loss_pct: number;
  max_positions: number;
  current_positions: number;
  kill_switch_active: boolean;
  circuit_breakers: {
    slippage: boolean;
    rejection_rate: boolean;
    drawdown: boolean;
  };
}

export interface StrategyConfig {
  id: string;
  name: string;
  description?: string;
  version: string;
  parameters: Record<string, any>;
  is_active: boolean;
  is_default: boolean;
  model_version?: string;
  symbols: string[];
  created_at: string;
  updated_at: string;
}
