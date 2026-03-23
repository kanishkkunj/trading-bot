/**
 * RiskManager enforces capital, loss, and position limits.
 */
export interface OpenPosition {
  symbol: string;
  action: 'BUY' | 'SELL';
  entryPrice: number;
  quantity: number;
}

export class RiskManager {
  /** Maximum daily loss allowed (₹) */
  private readonly maxDailyLoss: number;
  /** Maximum capital allocation per trade (₹) */
  private readonly maxCapitalPerTrade: number;
  /** Maximum open positions allowed simultaneously */
  private readonly maxOpenPositions: number;

  public dailyPnL = 0;
  public openPositions: OpenPosition[] = [];

  constructor() {
    this.maxDailyLoss = Number(process.env.MAX_DAILY_LOSS ?? 0);
    this.maxCapitalPerTrade = Number(process.env.MAX_CAPITAL_PER_TRADE ?? 0);
    this.maxOpenPositions = Number(process.env.MAX_OPEN_POSITIONS ?? 0);
  }

  /**
   * Determine whether a trade can be placed under risk constraints.
   */
  public canTrade(action: string, entryPrice: number, quantity: number): boolean {
    if (Number.isNaN(entryPrice) || Number.isNaN(quantity)) return false;
    if (this.dailyPnL <= -Math.abs(this.maxDailyLoss)) {
      return false;
    }
    if (this.openPositions.length >= this.maxOpenPositions) {
      return false;
    }
    if (entryPrice * quantity > this.maxCapitalPerTrade) {
      return false;
    }
    return true;
  }

  /**
   * Record a new open trade.
   */
  public recordTrade(trade: OpenPosition): void {
    this.openPositions.push(trade);
  }

  /**
   * Close a trade and update PnL.
   */
  public closeTrade(symbol: string, exitPrice: number): void {
    const idx = this.openPositions.findIndex((t) => t.symbol === symbol);
    if (idx === -1) return;
    const trade = this.openPositions[idx];
    const direction = trade.action === 'BUY' ? 1 : -1;
    const pnl = direction * (exitPrice - trade.entryPrice) * trade.quantity;
    this.dailyPnL += pnl;
    this.openPositions.splice(idx, 1);
  }

  /**
   * Summary of daily risk state.
   */
  public getDailySummary(): {
    totalTrades: number;
    openPositions: OpenPosition[];
    dailyPnL: number;
    maxLossHit: boolean;
  } {
    return {
      totalTrades: this.openPositions.length,
      openPositions: [...this.openPositions],
      dailyPnL: this.dailyPnL,
      maxLossHit: this.dailyPnL <= -Math.abs(this.maxDailyLoss),
    };
  }
}

export const riskManager = new RiskManager();
