/**
 * SQLite database layer for Trade records and daily performance metrics.
 * Uses better-sqlite3 (synchronous API) for reliable, embedded persistence.
 */
import BetterSqlite3 from 'better-sqlite3';
import path from 'path';
import fs from 'fs';
import { TradeRecord, PerformanceMetrics } from '../types';

const DB_DIR = path.resolve(process.cwd(), 'data');
const DB_PATH = path.join(DB_DIR, 'tradecraft.db');

/**
 * Singleton SQLite database wrapper.
 * Creates tables on first use; all reads/writes are synchronous.
 */
export class Database {
    private db: BetterSqlite3.Database;

    constructor() {
        if (!fs.existsSync(DB_DIR)) {
            fs.mkdirSync(DB_DIR, { recursive: true });
        }
        this.db = new BetterSqlite3(DB_PATH);
        this.db.pragma('journal_mode = WAL');
        this.createTables();
    }

    /** Create tables if they do not already exist */
    private createTables(): void {
        this.db.exec(`
            CREATE TABLE IF NOT EXISTS trades (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol                  TEXT NOT NULL,
                action                  TEXT NOT NULL,
                entry_price             REAL NOT NULL,
                exit_price              REAL,
                target_price            REAL NOT NULL,
                stop_loss               REAL NOT NULL,
                quantity                INTEGER NOT NULL,
                entry_time              TEXT NOT NULL,
                exit_time               TEXT,
                pnl                     REAL,
                outcome                 TEXT DEFAULT 'OPEN',
                confidence              INTEGER NOT NULL,
                risk_flag               TEXT NOT NULL DEFAULT '',
                reasoning               TEXT NOT NULL DEFAULT '',
                rsi_at_entry            REAL NOT NULL DEFAULT 0,
                ema9_at_entry           REAL NOT NULL DEFAULT 0,
                ema21_at_entry          REAL NOT NULL DEFAULT 0,
                macd_line_at_entry      REAL NOT NULL DEFAULT 0,
                sentiment_at_entry      TEXT NOT NULL DEFAULT 'NEUTRAL',
                sentiment_score_at_entry REAL NOT NULL DEFAULT 0,
                nse_announcement_flag   INTEGER NOT NULL DEFAULT 0,
                failure_cause           TEXT,
                lesson                  TEXT,
                created_at              TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS daily_metrics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT UNIQUE NOT NULL,
                total_trades    INTEGER NOT NULL DEFAULT 0,
                wins            INTEGER NOT NULL DEFAULT 0,
                losses          INTEGER NOT NULL DEFAULT 0,
                win_rate        REAL NOT NULL DEFAULT 0,
                total_pnl       REAL NOT NULL DEFAULT 0,
                gross_profit    REAL NOT NULL DEFAULT 0,
                gross_loss      REAL NOT NULL DEFAULT 0,
                profit_factor   REAL NOT NULL DEFAULT 0,
                sharpe_ratio    REAL NOT NULL DEFAULT 0,
                max_drawdown    REAL NOT NULL DEFAULT 0,
                brier_score     REAL NOT NULL DEFAULT 0,
                avg_confidence  REAL NOT NULL DEFAULT 0,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP
            );
        `);
    }

    /**
     * Insert a new trade record.
     * @param trade Trade data without id
     * @returns Auto-incremented row id
     */
    public insertTrade(trade: Omit<TradeRecord, 'id'>): number {
        const stmt = this.db.prepare(`
            INSERT INTO trades (
                symbol, action, entry_price, exit_price, target_price, stop_loss, quantity,
                entry_time, exit_time, pnl, outcome, confidence, risk_flag, reasoning,
                rsi_at_entry, ema9_at_entry, ema21_at_entry, macd_line_at_entry,
                sentiment_at_entry, sentiment_score_at_entry, nse_announcement_flag,
                failure_cause, lesson
            ) VALUES (
                @symbol, @action, @entry_price, @exit_price, @target_price, @stop_loss, @quantity,
                @entry_time, @exit_time, @pnl, @outcome, @confidence, @risk_flag, @reasoning,
                @rsi_at_entry, @ema9_at_entry, @ema21_at_entry, @macd_line_at_entry,
                @sentiment_at_entry, @sentiment_score_at_entry, @nse_announcement_flag,
                @failure_cause, @lesson
            )
        `);

        const result = stmt.run({
            ...trade,
            outcome: trade.outcome ?? 'OPEN',
            exit_price: trade.exit_price ?? null,
            exit_time: trade.exit_time ?? null,
            pnl: trade.pnl ?? null,
            failure_cause: trade.failure_cause ?? null,
            lesson: trade.lesson ?? null,
            nse_announcement_flag: trade.nse_announcement_flag ? 1 : 0,
        });

        return result.lastInsertRowid as number;
    }

    /**
     * Close an open trade by recording exit price and computing PnL.
     * Sets outcome to WIN / LOSS / BREAKEVEN.
     * @param id Trade row id
     * @param exit_price Price at which the trade was closed
     * @param exit_time ISO timestamp of close
     */
    public closeTrade(id: number, exit_price: number, exit_time: string): void {
        const trade = this.getTradeById(id);
        if (!trade) throw new Error(`Trade id ${id} not found`);

        const rawPnl =
            trade.action === 'BUY'
                ? (exit_price - trade.entry_price) * trade.quantity
                : (trade.entry_price - exit_price) * trade.quantity;

        const pnl = Math.round(rawPnl * 100) / 100;
        const outcome: TradeRecord['outcome'] =
            pnl > 0 ? 'WIN' : pnl < 0 ? 'LOSS' : 'BREAKEVEN';

        this.db
            .prepare(
                `UPDATE trades SET exit_price = ?, exit_time = ?, pnl = ?, outcome = ?
                 WHERE id = ?`,
            )
            .run(exit_price, exit_time, pnl, outcome, id);
    }

    /**
     * Attach a failure classification and lesson to a closed trade.
     * @param id Trade row id
     * @param failure_cause Classification key
     * @param lesson One-sentence lesson string
     */
    public updateTradeLesson(id: number, failure_cause: string, lesson: string): void {
        this.db
            .prepare(`UPDATE trades SET failure_cause = ?, lesson = ? WHERE id = ?`)
            .run(failure_cause, lesson, id);
    }

    /**
     * Retrieve all trades that are still OPEN.
     */
    public getOpenTrades(): TradeRecord[] {
        return this.db
            .prepare(`SELECT * FROM trades WHERE outcome = 'OPEN' ORDER BY created_at DESC`)
            .all() as TradeRecord[];
    }

    /**
     * Retrieve a single trade by its id.
     * @param id Trade row id
     */
    public getTradeById(id: number): TradeRecord | null {
        const row = this.db
            .prepare(`SELECT * FROM trades WHERE id = ?`)
            .get(id) as TradeRecord | undefined;
        return row ?? null;
    }

    /**
     * Retrieve the N most recent trades (any outcome).
     * @param limit Maximum number of rows to return
     */
    public getRecentTrades(limit: number): TradeRecord[] {
        return this.db
            .prepare(`SELECT * FROM trades ORDER BY created_at DESC LIMIT ?`)
            .all(limit) as TradeRecord[];
    }

    /**
     * Retrieve all trades entered today (UTC date).
     */
    public getTodaysTrades(): TradeRecord[] {
        const today = new Date().toISOString().slice(0, 10);
        return this.db
            .prepare(
                `SELECT * FROM trades WHERE substr(entry_time, 1, 10) = ? ORDER BY entry_time ASC`,
            )
            .all(today) as TradeRecord[];
    }

    /**
     * Upsert daily performance metrics for a given date.
     * @param metrics Fully computed PerformanceMetrics object
     */
    public saveDailyMetrics(metrics: PerformanceMetrics): void {
        this.db
            .prepare(`
                INSERT INTO daily_metrics (
                    date, total_trades, wins, losses, win_rate, total_pnl,
                    gross_profit, gross_loss, profit_factor, sharpe_ratio,
                    max_drawdown, brier_score, avg_confidence
                ) VALUES (
                    @date, @totalTrades, @wins, @losses, @winRate, @totalPnl,
                    @grossProfit, @grossLoss, @profitFactor, @sharpeRatio,
                    @maxDrawdown, @brierScore, @avgConfidence
                )
                ON CONFLICT(date) DO UPDATE SET
                    total_trades   = excluded.total_trades,
                    wins           = excluded.wins,
                    losses         = excluded.losses,
                    win_rate       = excluded.win_rate,
                    total_pnl      = excluded.total_pnl,
                    gross_profit   = excluded.gross_profit,
                    gross_loss     = excluded.gross_loss,
                    profit_factor  = excluded.profit_factor,
                    sharpe_ratio   = excluded.sharpe_ratio,
                    max_drawdown   = excluded.max_drawdown,
                    brier_score    = excluded.brier_score,
                    avg_confidence = excluded.avg_confidence
            `)
            .run({
                date: metrics.date,
                totalTrades: metrics.totalTrades,
                wins: metrics.wins,
                losses: metrics.losses,
                winRate: metrics.winRate,
                totalPnl: metrics.totalPnl,
                grossProfit: metrics.grossProfit,
                grossLoss: metrics.grossLoss,
                profitFactor: metrics.profitFactor,
                sharpeRatio: metrics.sharpeRatio,
                maxDrawdown: metrics.maxDrawdown,
                brierScore: metrics.brierScore,
                avgConfidence: metrics.avgConfidence,
            });
    }

    /**
     * Retrieve daily metrics history for the last N days.
     * @param days Number of recent days to return
     */
    public getMetricsHistory(days: number): PerformanceMetrics[] {
        const rows = this.db
            .prepare(
                `SELECT * FROM daily_metrics ORDER BY date DESC LIMIT ?`,
            )
            .all(days) as Array<Record<string, unknown>>;

        return rows.map((r) => ({
            date: String(r.date),
            totalTrades: Number(r.total_trades),
            openTrades: 0,
            wins: Number(r.wins),
            losses: Number(r.losses),
            winRate: Number(r.win_rate),
            totalPnl: Number(r.total_pnl),
            grossProfit: Number(r.gross_profit),
            grossLoss: Number(r.gross_loss),
            profitFactor: Number(r.profit_factor),
            sharpeRatio: Number(r.sharpe_ratio),
            maxDrawdown: Number(r.max_drawdown),
            currentDrawdown: 0,
            maxDrawdownBreached: Number(r.max_drawdown) > 0.08,
            brierScore: Number(r.brier_score),
            avgConfidence: Number(r.avg_confidence),
            avgWinPnl: 0,
            avgLossPnl: 0,
        }));
    }
}

/** Singleton database instance */
export const db = new Database();
