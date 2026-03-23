/**
 * PerformanceTracker computes aggregated trading metrics from a set of trade records.
 * Metrics include win rate, PnL, Sharpe ratio, max drawdown, and Brier score.
 */
import { TradeRecord, PerformanceMetrics } from '../types';
import { db } from '../db/database';

const MAX_DRAWDOWN_THRESHOLD = 0.08; // 8%

/**
 * Computes trading KPIs from a list of trade records.
 */
export class PerformanceTracker {
    /**
     * Compute full performance metrics from a list of trade records.
     * Only closed trades (outcome !== 'OPEN') are included in calculations.
     * @param trades Array of all trade records (open + closed)
     * @returns Fully populated PerformanceMetrics object
     */
    public calculateMetrics(trades: TradeRecord[]): PerformanceMetrics {
        const openTrades = trades.filter((t) => t.outcome === 'OPEN');
        const closed = trades.filter((t) => t.outcome && t.outcome !== 'OPEN');

        const wins = closed.filter((t) => t.outcome === 'WIN');
        const losses = closed.filter((t) => t.outcome === 'LOSS');

        const totalTrades = closed.length;
        const winRate = totalTrades > 0 ? (wins.length / totalTrades) * 100 : 0;

        const grossProfit = wins.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
        const grossLoss = Math.abs(losses.reduce((sum, t) => sum + (t.pnl ?? 0), 0));
        const totalPnl = closed.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
        const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : 0;

        const avgWinPnl = wins.length > 0 ? grossProfit / wins.length : 0;
        const avgLossPnl = losses.length > 0 ? -(grossLoss / losses.length) : 0;

        const avgConfidence =
            closed.length > 0
                ? closed.reduce((sum, t) => sum + t.confidence, 0) / closed.length
                : 0;

        // Sharpe ratio from sorted daily PnL
        const sharpeRatio = this.calcSharpe(closed);

        // Max drawdown: largest peak-to-trough drop in cumulative PnL
        const { maxDrawdown, currentDrawdown } = this.calcDrawdown(closed);

        // Brier score: calibration of confidence vs actual outcome
        const brierScore = this.calcBrier(closed);

        return {
            totalTrades,
            openTrades: openTrades.length,
            wins: wins.length,
            losses: losses.length,
            winRate: Math.round(winRate * 100) / 100,
            totalPnl: Math.round(totalPnl * 100) / 100,
            grossProfit: Math.round(grossProfit * 100) / 100,
            grossLoss: Math.round(grossLoss * 100) / 100,
            profitFactor: Math.round(profitFactor * 1000) / 1000,
            sharpeRatio: Math.round(sharpeRatio * 1000) / 1000,
            maxDrawdown: Math.round(maxDrawdown * 10000) / 10000,
            currentDrawdown: Math.round(currentDrawdown * 10000) / 10000,
            maxDrawdownBreached: maxDrawdown > MAX_DRAWDOWN_THRESHOLD,
            brierScore: Math.round(brierScore * 10000) / 10000,
            avgConfidence: Math.round(avgConfidence * 100) / 100,
            avgWinPnl: Math.round(avgWinPnl * 100) / 100,
            avgLossPnl: Math.round(avgLossPnl * 100) / 100,
            date: new Date().toISOString().slice(0, 10),
        };
    }

    /**
     * Check whether today's trades have breached the 8% max drawdown limit.
     * @returns true if the current drawdown exceeds the threshold
     */
    public isDrawdownBreached(): boolean {
        try {
            const todaysTrades = db.getTodaysTrades();
            const metrics = this.calculateMetrics(todaysTrades);
            return metrics.maxDrawdownBreached;
        } catch {
            return false;
        }
    }

    /**
     * Build a Telegram-ready summary string from computed metrics.
     * @param metrics Pre-computed metrics for the session
     * @returns Formatted multi-line summary string
     */
    public getDailySummaryText(metrics: PerformanceMetrics): string {
        const pnlSign = metrics.totalPnl >= 0 ? '+' : '';
        const drawdownPct = (metrics.maxDrawdown * 100).toFixed(1);
        return (
            `📊 Daily Summary — ${metrics.date}\n` +
            `Trades: ${metrics.totalTrades} | W: ${metrics.wins} L: ${metrics.losses} | Win Rate: ${metrics.winRate.toFixed(1)}%\n` +
            `PnL: ₹${pnlSign}${metrics.totalPnl.toLocaleString('en-IN')} | Profit Factor: ${metrics.profitFactor.toFixed(2)}\n` +
            `Sharpe: ${metrics.sharpeRatio.toFixed(2)} | Max Drawdown: ${drawdownPct}%\n` +
            `Brier Score: ${metrics.brierScore.toFixed(2)} (calibration)`
        );
    }

    // ──────────────────────────────────────────────────────────────────────────
    // Private helpers
    // ──────────────────────────────────────────────────────────────────────────

    /** Annualised Sharpe ratio from per-trade PnL returns */
    private calcSharpe(closed: TradeRecord[]): number {
        if (closed.length < 2) return 0;
        const returns = closed.map((t) => t.pnl ?? 0);
        const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
        const variance =
            returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
        const stdDev = Math.sqrt(variance);
        if (stdDev === 0) return 0;
        return (mean / stdDev) * Math.sqrt(252);
    }

    /** Compute max and current drawdown from cumulative PnL curve */
    private calcDrawdown(closed: TradeRecord[]): {
        maxDrawdown: number;
        currentDrawdown: number;
    } {
        if (closed.length === 0) return { maxDrawdown: 0, currentDrawdown: 0 };

        let peak = 0;
        let runningPnl = 0;
        let maxDrawdown = 0;

        for (const t of closed) {
            runningPnl += t.pnl ?? 0;
            if (runningPnl > peak) peak = runningPnl;
            if (peak > 0) {
                const dd = (peak - runningPnl) / peak;
                if (dd > maxDrawdown) maxDrawdown = dd;
            }
        }

        const currentDrawdown = peak > 0 ? (peak - runningPnl) / peak : 0;
        return { maxDrawdown, currentDrawdown };
    }

    /**
     * Brier score measures confidence calibration.
     * Score of 0 = perfect; 1 = worst possible.
     * confidence is on a 1-10 scale; normalise to 0-1 before scoring.
     */
    private calcBrier(closed: TradeRecord[]): number {
        if (closed.length === 0) return 0;
        let total = 0;
        for (const t of closed) {
            const p = Math.min(10, Math.max(1, t.confidence)) / 10;
            const o = t.outcome === 'WIN' ? 1 : 0;
            total += Math.pow(p - o, 2);
        }
        return total / closed.length;
    }
}

/** Singleton performance tracker instance */
export const performanceTracker = new PerformanceTracker();
