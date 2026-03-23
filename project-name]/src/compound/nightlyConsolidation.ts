/**
 * Nightly consolidation job — runs after market close (3:30 PM IST, Mon-Fri).
 * 1. Runs post-mortems on any unanalysed losses.
 * 2. Computes and persists daily metrics.
 * 3. Sends a Telegram summary with lessons learned.
 */
import cron from 'node-cron';
import axios from 'axios';
import { db } from '../db/database';
import { performanceTracker } from './performanceTracker';
import { postMortemAgent } from './postMortemAgent';
import { PostMortem } from '../types';

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN ?? '';
const TELEGRAM_CHAT_ID = '5700806464';
const TELEGRAM_API_URL = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;

/** Pause execution for a given number of milliseconds */
function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Send a plain-text message via Telegram.
 * Never throws — logs errors silently.
 */
async function sendTelegram(text: string): Promise<void> {
    if (!TELEGRAM_BOT_TOKEN) {
        console.warn('[NightlyConsolidation] TELEGRAM_BOT_TOKEN not set — skipping Telegram');
        return;
    }
    try {
        await axios.post(
            TELEGRAM_API_URL,
            { chat_id: TELEGRAM_CHAT_ID, text, parse_mode: 'Markdown' },
            { timeout: 10_000 },
        );
    } catch (err) {
        console.error('[NightlyConsolidation] Telegram send failed:', (err as Error).message);
    }
}

/**
 * Result payload from a nightly consolidation run.
 */
export interface NightlyConsolidationResult {
    summary: string;
    lessons: string[];
    processedLosses: number;
    totalTrades: number;
    startedAt: string;
    completedAt: string;
}

/**
 * Core nightly consolidation logic — exposed for manual triggering and API use.
 * @param options sendTelegram controls whether summary is pushed directly from here
 */
export async function runNightlyConsolidation(
    options: { sendTelegram?: boolean } = {},
): Promise<NightlyConsolidationResult> {
    const shouldSendTelegram = options.sendTelegram ?? true;
    const startTime = new Date().toISOString();
    console.log(`[NightlyConsolidation] Starting consolidation at ${startTime}`);

    try {
        const todaysTrades = db.getTodaysTrades();
        console.log(
            `[NightlyConsolidation] Processing ${todaysTrades.length} trades for today`,
        );

        // Step 1: Run post-mortems on LOSS trades that don't have a lesson yet
        const lossesWithoutLesson = todaysTrades.filter(
            (t) => t.outcome === 'LOSS' && !t.lesson,
        );
        const postMortems: PostMortem[] = [];

        for (const trade of lossesWithoutLesson) {
            const pm = await postMortemAgent.analyzeFailure(trade);
            if (pm) postMortems.push(pm);
            // Rate limit: 2-second delay between post-mortem calls
            if (lossesWithoutLesson.indexOf(trade) < lossesWithoutLesson.length - 1) {
                await sleep(2_000);
            }
        }

        // Step 2: Compute and persist daily metrics
        const metrics = performanceTracker.calculateMetrics(todaysTrades);
        db.saveDailyMetrics(metrics);
        console.log('[NightlyConsolidation] Daily metrics saved to SQLite');

        // Step 3: Build and send Telegram summary
        let message = performanceTracker.getDailySummaryText(metrics);

        const lessons = postMortems.slice(0, 3).map((pm) => `[${pm.failure_cause}] ${pm.lesson}`);

        if (lessons.length > 0) {
            const lessonLines = postMortems
                .slice(0, 3) // top 3 lessons
                .map((pm, i) => `  ${i + 1}. [${pm.failure_cause}] ${pm.lesson}`)
                .join('\n');
            message += `\n\n📝 *Lessons Learned*\n${lessonLines}`;
        }

        if (shouldSendTelegram) {
            await sendTelegram(message);
        }

        const endTime = new Date().toISOString();
        console.log(`[NightlyConsolidation] Consolidation complete at ${endTime}`);

        return {
            summary: message,
            lessons,
            processedLosses: lossesWithoutLesson.length,
            totalTrades: todaysTrades.length,
            startedAt: startTime,
            completedAt: endTime,
        };
    } catch (err) {
        console.error('[NightlyConsolidation] Fatal error:', (err as Error).message);
        const endTime = new Date().toISOString();
        return {
            summary: 'Nightly consolidation failed.',
            lessons: [],
            processedLosses: 0,
            totalTrades: 0,
            startedAt: startTime,
            completedAt: endTime,
        };
    }
}

/**
 * Schedule and start the nightly consolidation cron job.
 * Runs at 3:30 PM IST (10:00 UTC) Mon-Fri.
 */
export function startNightlyConsolidation(): void {
    // '30 15 * * 1-5' = 3:30 PM every weekday
    cron.schedule(
        '30 15 * * 1-5',
        () => {
            runNightlyConsolidation();
        },
        { timezone: 'Asia/Kolkata' },
    );
    console.log('[NightlyConsolidation] Scheduled for 3:30 PM IST, Mon-Fri');
}
