import axios from 'axios';
import { TradeOrder } from '../types';

const DHAN_BASE_URL = 'https://api.dhan.co';

/**
 * DhanClient wraps order and positions endpoints.
 */
export class DhanClient {
  private readonly apiKey: string;
  private readonly clientId: string;

  constructor() {
    this.apiKey = process.env.DHAN_API_KEY ?? '';
    this.clientId = process.env.DHAN_CLIENT_ID ?? '';
  }

  /**
   * Place an order on Dhan.
   */
  public async placeOrder(order: TradeOrder): Promise<{ orderId: string; status: string }> {
    if (!this.apiKey || !this.clientId) {
      throw new Error('[DhanClient] Missing DHAN_API_KEY or DHAN_CLIENT_ID');
    }

    const payload = {
      dhanClientId: this.clientId,
      transactionType: order.action,
      exchangeSegment: 'NSE_EQ',
      productType: 'INTRADAY',
      orderType: order.orderType,
      tradingSymbol: order.symbol,
      quantity: order.quantity,
      price: order.orderType === 'LIMIT' ? order.price : 0,
    };

    try {
      const response = await axios.post(`${DHAN_BASE_URL}/orders`, payload, {
        headers: {
          'access-token': this.apiKey,
          'Content-Type': 'application/json',
        },
        timeout: 10000,
      });

      const { orderId, status } = response.data ?? {};
      if (!orderId) {
        throw new Error('[DhanClient] Order placement response missing orderId');
      }
      return { orderId, status: status ?? 'PENDING' };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown Dhan order error';
      throw new Error(`[DhanClient] Failed to place order: ${message}`);
    }
  }

  /**
   * Fetch open positions from Dhan.
   */
  public async getPositions(): Promise<any[]> {
    if (!this.apiKey) {
      throw new Error('[DhanClient] Missing DHAN_API_KEY');
    }

    try {
      const response = await axios.get(`${DHAN_BASE_URL}/positions`, {
        headers: {
          'access-token': this.apiKey,
          'Content-Type': 'application/json',
        },
        timeout: 10000,
      });

      return Array.isArray(response.data) ? response.data : [];
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown Dhan positions error';
      throw new Error(`[DhanClient] Failed to fetch positions: ${message}`);
    }
  }
}

export const dhanClient = new DhanClient();
