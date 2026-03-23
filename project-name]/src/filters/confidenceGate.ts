/**
 * Confidence gate to allow or reject trade execution based on threshold.
 */
import { ClaudeTradeDecision } from '../types';

const rawThreshold = Number(process.env.CONFIDENCE_THRESHOLD ?? 7);
const threshold = rawThreshold > 10 ? Math.round(rawThreshold / 10) : rawThreshold;

/**
 * Decide whether to execute a trade based on confidence and action.
 */
export function shouldExecute(decision: ClaudeTradeDecision): boolean {
  if (!decision) return false;
  if (decision.action === 'HOLD') {
    // eslint-disable-next-line no-console
    console.log('[CONFIDENCE_GATE] Rejected: action is HOLD');
    return false;
  }
  if (decision.confidence < threshold) {
    // eslint-disable-next-line no-console
    console.log(`[CONFIDENCE_GATE] Rejected: confidence ${decision.confidence} below threshold ${threshold}`);
    return false;
  }
  return true;
}
