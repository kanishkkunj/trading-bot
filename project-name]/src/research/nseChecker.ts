/**
 * NseChecker verifies recent NSE (National Stock Exchange) announcements
 * Never blocks trading - always returns false on error
 */

import axios from 'axios';

export class NseChecker {
    /**
     * Check if there are recent NSE announcements for a symbol (last 2 hours)
     * Wraps in try/catch - returns false on failure without blocking
     * @param symbol Stock symbol to check
     * @returns True if announcement found in last 2 hours, false otherwise
     */
    public async checkRecentAnnouncements(symbol: string): Promise<boolean> {
        try {
            const response = await axios.get(
                `https://www.nseindia.com/api/corp-info?symbol=${encodeURIComponent(symbol)}&corpType=announcements`,
                {
                    headers: {
                        'User-Agent': 'Mozilla/5.0',
                        'Accept': 'application/json',
                    },
                    timeout: 5000,
                },
            );

            const data = response.data as any;

            // Check if we have announcements
            if (!data || !Array.isArray(data)) {
                return false;
            }

            // Check if any announcement is within the last 2 hours
            const now = new Date();
            const twoHoursAgo = new Date(now.getTime() - 2 * 60 * 60 * 1000);

            for (const announcement of data) {
                if (announcement.date) {
                    try {
                        const announcementDate = new Date(announcement.date);
                        if (announcementDate >= twoHoursAgo && announcementDate <= now) {
                            return true;
                        }
                    } catch {
                        // Invalid date format, skip
                        continue;
                    }
                }
            }

            return false;
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error(
                '[NseChecker] Error checking announcements:',
                error instanceof Error ? error.message : error,
            );
            // Don't block trading on API failure
            return false;
        }
    }
}
