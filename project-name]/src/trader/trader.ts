/**
 * Trader orchestrates decision gating, risk checks, and order execution.
 */
import { RiskManager } from '../risk/riskManager';
import { noNewTrades } from '../squareOff/autoSquareOff';
import { shouldExecute } from '../filters/confidenceGate';
import { DecisionLogger } from '../logger/decisionLogger';
import { DhanClient } from '../dhan/dhanClient';
import { db } from '../db/database';
import { knowledgeBase } from '../compound/knowledgeBase';
import { performanceTracker } from '../compound/performanceTracker';
import {
  MarketDataPayload,
  ClaudeTradeDecision,
  LogEntry,
  TradeOrder,
  ExecutionResult,
  ResearchBrief,
} from '../types';

/**
 * Trader ties parsed Claude decisions to execution and logging.
 */
export class Trader {
  constructor(
    private readonly riskManager: RiskManager,
    private readonly decisionLogger: DecisionLogger,
    private readonly dhanClient: DhanClient,
  ) {}

  /**
   * Process a parsed trading decision: confidence gate → risk check → Dhan execution → logging.
   * Optionally integrates sentiment research brief for enhanced decision validation.
   * @param marketData Current market data for the symbol
   * @param decision Claude's trading decision
   * @param researchBrief Optional sentiment research brief (overrides confidence if needed)
   */
  public async processTradingSignal(
    marketData: MarketDataPayload,
    decision: ClaudeTradeDecision,
    researchBrief?: ResearchBrief,
  ): Promise<ExecutionResult> {
    try {
      if (marketData.symbol !== decision.symbol) {
        const mismatch: ExecutionResult = {
          executed: false,
          rejection_reason: 'Symbol mismatch between market data and decision',
          decision,
        };
        await this.logDecision(decision, mismatch);
        return mismatch;
      }

      // ── Compound: Check daily drawdown limit before any trade ──────────────
      if (performanceTracker.isDrawdownBreached()) {
        console.warn('[TRADER] Max drawdown limit reached — holding');
        const hold: ExecutionResult = {
          executed: false,
          rejection_reason: 'Max drawdown limit reached',
          decision,
        };
        await this.logDecision(decision, hold);
        return hold;
      }

      // ── Compound: Query past lessons from Pinecone ─────────────────────────
      if (researchBrief) {
        try {
          const setupText = knowledgeBase.buildCurrentSetupText(marketData, researchBrief);
          const pastLessons = await knowledgeBase.querySimilarLessons(setupText);
          const strongWarnings = pastLessons.filter(
            (l) =>
              (l.similarity_score ?? 0) > 0.85 &&
              l.failure_cause === pastLessons[0]?.failure_cause,
          );
          if (strongWarnings.length >= 2) {
            const previousConfidence = decision.confidence;
            decision.confidence = Math.max(1, decision.confidence - 2);
            console.warn(
              `[TRADER] ${strongWarnings.length} past lessons warn about this setup ` +
              `(${strongWarnings[0].failure_cause}) — confidence reduced from ` +
              `${previousConfidence} to ${decision.confidence}`,
            );
          }
        } catch (err) {
          // Never block trade on knowledge base errors
          console.error('[TRADER] past lessons query error:', (err as Error).message);
        }
      }

      // Apply research brief validation (sentiment & NSE check)
      if (researchBrief) {
        decision = this.applyResearchBrief(decision, researchBrief);

        if (researchBrief.nseAnnouncementFlag) {
          // eslint-disable-next-line no-console
          console.warn('[TRADER] NSE announcement detected - holding for safety');
          const nseHold: ExecutionResult = {
            executed: false,
            rejection_reason: 'NSE announcement detected - holding for safety',
            decision,
          };
          await this.logDecision(decision, nseHold);
          return nseHold;
        }
      }

      if (noNewTrades) {
        const cutoff: ExecutionResult = {
          executed: false,
          rejection_reason: 'No new trades after 2:45 PM IST',
          decision,
        };
        await this.logDecision(decision, cutoff);
        return cutoff;
      }

      if (!shouldExecute(decision)) {
        const rejected: ExecutionResult = {
          executed: false,
          rejection_reason: 'Confidence gate rejected',
          decision,
        };
        await this.logDecision(decision, rejected);
        return rejected;
      }

      if (!this.riskManager.canTrade(decision.action, decision.entry_price, decision.quantity)) {
        const riskFail: ExecutionResult = {
          executed: false,
          rejection_reason: 'Risk manager rejection',
          decision,
        };
        await this.logDecision(decision, riskFail);
        return riskFail;
      }

      const order: TradeOrder = {
        symbol: decision.symbol,
        action: decision.action as 'BUY' | 'SELL',
        quantity: decision.quantity,
        price: decision.entry_price,
        orderType: 'MARKET',
      };

      try {
        await this.dhanClient.placeOrder(order);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Dhan order failed';
        const failure: ExecutionResult = {
          executed: false,
          rejection_reason: message,
          decision,
        };
        await this.logDecision(decision, failure);
        return failure;
      }

      this.riskManager.recordTrade({
        symbol: decision.symbol,
        action: decision.action as 'BUY' | 'SELL',
        entryPrice: decision.entry_price,
        quantity: decision.quantity,
      });

      const executed: ExecutionResult = {
        executed: true,
        order,
        decision,
      };

      // ── Compound: Persist trade to SQLite ─────────────────────────────────
      try {
        const tradeId = db.insertTrade({
          symbol: decision.symbol,
          action: decision.action as 'BUY' | 'SELL',
          entry_price: decision.entry_price,
          target_price: decision.target_price,
          stop_loss: decision.stop_loss,
          quantity: decision.quantity,
          entry_time: new Date().toISOString(),
          outcome: 'OPEN',
          confidence: decision.confidence,
          risk_flag: '',
          reasoning: decision.reason,
          rsi_at_entry: marketData.indicators?.rsi ?? 0,
          ema9_at_entry: marketData.indicators?.ema9 ?? 0,
          ema21_at_entry: marketData.indicators?.ema21 ?? 0,
          macd_line_at_entry: marketData.indicators?.macd?.line ?? 0,
          sentiment_at_entry: researchBrief?.overallSentiment ?? 'NEUTRAL',
          sentiment_score_at_entry: researchBrief?.sentimentScore ?? 0,
          nse_announcement_flag: researchBrief?.nseAnnouncementFlag ?? false,
        });
        executed.tradeId = tradeId;
        console.log(`[TRADER] Trade logged to SQLite with id ${tradeId}`);
      } catch (dbErr) {
        console.error('[TRADER] Failed to log trade to SQLite:', (dbErr as Error).message);
      }

      await this.logDecision(decision, executed);
      return executed;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Execution error';
      const failure: ExecutionResult = {
        executed: false,
        rejection_reason: message,
        decision,
      };
      await this.logDecision(decision, failure);
      return failure;
    }
  }

  /**
   * Log decision outcome using DecisionLogger.
   */
  private async logDecision(decision: ClaudeTradeDecision, result: ExecutionResult): Promise<void> {
    const logEntry: LogEntry = {
      timestamp: new Date().toISOString(),
      symbol: decision.symbol,
      action: decision.action,
      confidence: decision.confidence,
      entry_price: decision.entry_price,
      target_price: decision.target_price,
      stop_loss: decision.stop_loss,
      quantity: decision.quantity,
      reason: result.rejection_reason ?? decision.reason,
      executed: result.executed,
      executionRejectedReason: result.rejection_reason,
    };

    await this.decisionLogger.log(logEntry);
  }

  /**
   * Apply research brief sentiment analysis to modify trading confidence
   * Rules:
   * 1. If sentiment opposes Claude decision, reduce confidence by 2 points
   * 2. If sentiment aligns with Claude decision AND confidence > 60, increase by 1 point
   * @param decision The original Claude decision
   * @param brief The research sentiment brief
   * @returns Modified decision (by reference)
   */
  private applyResearchBrief(
    decision: ClaudeTradeDecision,
    brief: ResearchBrief,
  ): ClaudeTradeDecision {
    const isBuyDecision = decision.action === 'BUY';
    const isSellDecision = decision.action === 'SELL';
    const sentimentIsBullish = brief.overallSentiment === 'BULLISH';
    const sentimentIsBearish = brief.overallSentiment === 'BEARISH';

    // Check if sentiment opposes the decision
    const sentimentOpposed =
      (isBuyDecision && sentimentIsBearish && brief.sentimentScore < -0.3) ||
      (isSellDecision && sentimentIsBullish && brief.sentimentScore > 0.3);

    if (sentimentOpposed) {
      const previousConfidence = decision.confidence;
      decision.confidence = Math.max(0, decision.confidence - 2);
      // eslint-disable-next-line no-console
      console.warn(
        '[TRADER] Sentiment contradicts Claude decision - reduced confidence from',
        previousConfidence,
        'to',
        decision.confidence,
      );
      return decision;
    }

    // Check if sentiment aligns with decision
    const sentimentAligned =
      (isBuyDecision && sentimentIsBullish) || (isSellDecision && sentimentIsBearish);

    if (sentimentAligned && brief.confidence > 60) {
      decision.confidence = Math.min(10, decision.confidence + 1);
      // eslint-disable-next-line no-console
      console.log(
        '[TRADER] Sentiment aligns with Claude decision - increased confidence to',
        decision.confidence,
      );
      return decision;
    }

    return decision;
  }
}
