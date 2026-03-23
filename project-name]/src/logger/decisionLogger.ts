/**
 * DecisionLogger writes decisions locally and optionally to Google Sheets.
 */
import fs from 'fs';
import path from 'path';
import axios from 'axios';
import { LogEntry } from '../types';

const LOG_DIR = path.resolve(process.cwd(), 'logs');
const LOG_FILE = path.join(LOG_DIR, 'decisions.json');
const GOOGLE_SHEETS_WEBHOOK_URL = process.env.GOOGLE_SHEETS_WEBHOOK_URL;

/**
 * Ensure the log file exists.
 */
function ensureLogFile(): void {
  if (!fs.existsSync(LOG_DIR)) {
    fs.mkdirSync(LOG_DIR, { recursive: true });
  }
  if (!fs.existsSync(LOG_FILE)) {
    fs.writeFileSync(LOG_FILE, '[]', 'utf-8');
  }
}

/**
 * Append an entry to the local JSON log.
 */
async function appendLocal(entry: LogEntry): Promise<void> {
  ensureLogFile();
  const raw = fs.readFileSync(LOG_FILE, 'utf-8');
  const data: LogEntry[] = JSON.parse(raw);
  data.push(entry);
  fs.writeFileSync(LOG_FILE, JSON.stringify(data, null, 2), 'utf-8');
}

/**
 * DecisionLogger logs decisions locally and optionally forwards to Google Sheets.
 */
export class DecisionLogger {
  /**
   * Log a decision locally and optionally to Google Sheets.
   */
  public async log(entry: LogEntry): Promise<void> {
    try {
      await appendLocal(entry);
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('[DecisionLogger] Failed to write local log', error);
    }

    try {
      await this.sendToGoogleSheets(entry);
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('[DecisionLogger] Failed to send to Google Sheets', error);
    }
  }

  /**
   * Send the decision to Google Sheets webhook if configured.
   */
  public async sendToGoogleSheets(entry: LogEntry): Promise<void> {
    if (!GOOGLE_SHEETS_WEBHOOK_URL) return;
    await axios.post(GOOGLE_SHEETS_WEBHOOK_URL, entry, { timeout: 10000 });
  }
}
