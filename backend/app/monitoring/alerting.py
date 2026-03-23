"""Alerting via Slack/PagerDuty plus domain-specific triggers."""

from __future__ import annotations

from typing import Any, Dict, Optional

import structlog

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

log = structlog.get_logger()


class SlackNotifier:
    """Send Slack webhook alerts."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, text: str, channel: Optional[str] = None) -> None:
        if not httpx:
            log.warning("httpx_missing_for_slack", message=text)
            return
        payload: Dict[str, Any] = {"text": text}
        if channel:
            payload["channel"] = channel
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.error("slack_alert_failed", error=str(exc), text=text)


class PagerDutyNotifier:
    """Trigger PagerDuty events using Events v2 API."""

    def __init__(self, routing_key: str):
        self.routing_key = routing_key
        self.url = "https://events.pagerduty.com/v2/enqueue"

    async def trigger(self, summary: str, severity: str = "error", source: str = "tradecraft") -> None:
        if not httpx:
            log.warning("httpx_missing_for_pagerduty", summary=summary)
            return
        event = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": summary,
                "severity": severity,
                "source": source,
            },
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.url, json=event)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.error("pagerduty_trigger_failed", error=str(exc), summary=summary)


class AlertManager:
    """Domain-specific alert rules for drawdowns, performance, and data quality."""

    def __init__(
        self,
        slack: Optional[SlackNotifier] = None,
        pagerduty: Optional[PagerDutyNotifier] = None,
        drawdown_warn: float = 5.0,
        drawdown_crit: float = 10.0,
        perf_drop_pct: float = 20.0,
        stale_price_seconds: float = 60.0,
    ) -> None:
        self.slack = slack
        self.pagerduty = pagerduty
        self.drawdown_warn = drawdown_warn
        self.drawdown_crit = drawdown_crit
        self.perf_drop_pct = perf_drop_pct
        self.stale_price_seconds = stale_price_seconds

    async def check_drawdown(self, drawdown_pct: float) -> None:
        if drawdown_pct >= self.drawdown_crit:
            await self._notify(f"CRITICAL: drawdown {drawdown_pct:.2f}%", critical=True)
        elif drawdown_pct >= self.drawdown_warn:
            await self._notify(f"Warning: drawdown {drawdown_pct:.2f}%")

    async def check_model_performance(self, rolling_sharpe: float, baseline_sharpe: float) -> None:
        if baseline_sharpe <= 0:
            return
        drop = ((baseline_sharpe - rolling_sharpe) / baseline_sharpe) * 100
        if drop >= self.perf_drop_pct:
            await self._notify(
                f"Model performance degradation: Sharpe {rolling_sharpe:.2f} vs baseline {baseline_sharpe:.2f} ({drop:.1f}% drop)",
                critical=False,
            )

    async def check_data_quality(self, missing_ticks: int, stale_price_seconds: float) -> None:
        if missing_ticks > 0:
            await self._notify(f"Data quality issue: missing ticks {missing_ticks}")
        if stale_price_seconds > self.stale_price_seconds:
            await self._notify(f"Data stale: last price age {stale_price_seconds:.1f}s", critical=True)

    async def _notify(self, message: str, critical: bool = False) -> None:
        if self.slack:
            await self.slack.send(message)
        if critical and self.pagerduty:
            await self.pagerduty.trigger(summary=message, severity="critical")
        elif self.pagerduty:
            await self.pagerduty.trigger(summary=message, severity="error")
        log.info("alert_dispatched", message=message, critical=critical)
