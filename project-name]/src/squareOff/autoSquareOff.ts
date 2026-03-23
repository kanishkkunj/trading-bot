/**
 * Auto square-off scheduler for closing all positions before market close.
 */
import cron from 'node-cron';
import { riskManager } from '../risk/riskManager';
import { dhanClient } from '../dhan/dhanClient';
import { TradeOrder } from '../types';

export let noNewTrades = false;

/**
 * Close all open positions via Dhan and update risk manager.
 */
export async function closeAllPositions(): Promise<string[]> {
  const closedSymbols: string[] = [];
  try {
    const positions = await dhanClient.getPositions();

    for (const position of positions) {
      const netQty = Number(position?.netQty ?? 0);
      if (netQty <= 0) continue;

      const symbol: string = position.tradingSymbol ?? position.symbol;
      const order: TradeOrder = {
        symbol,
        action: 'SELL',
        quantity: netQty,
        price: Number(position?.ltp ?? position?.avgPrice ?? 0),
        orderType: 'MARKET',
      };

      await dhanClient.placeOrder(order);
      riskManager.closeTrade(symbol, order.price);
      closedSymbols.push(symbol);
    }

    return closedSymbols;
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to close positions';
    // eslint-disable-next-line no-console
    console.error('[AUTO_SQUARE_OFF] closeAllPositions failed', error);
    throw new Error(`[AUTO_SQUARE_OFF] ${message}`);
  }
}

/**
 * Initialize cron jobs for auto square-off (3:10 PM IST) and new-trade cutoff (2:45 PM IST).
 */
export function initAutoSquareOff(): void {
  cron.schedule('45 14 * * 1-5', () => {
    noNewTrades = true;
    // eslint-disable-next-line no-console
    console.log('[AUTO_SQUARE_OFF] New trades disabled after 2:45 PM IST');
  }, {
    timezone: 'Asia/Kolkata',
  });

  cron.schedule('10 15 * * 1-5', async () => {
    // eslint-disable-next-line no-console
    console.log('[AUTO_SQUARE_OFF] Starting auto square-off');
    await closeAllPositions();
  }, {
    timezone: 'Asia/Kolkata',
  });
}
