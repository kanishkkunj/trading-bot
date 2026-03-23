"""MiroFish bridge API routes.

These routes expose a guarded integration path to MiroFish while keeping
TradeCraft's execution path independent.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.mirofish_advisory import MiroFishAdvisory
from app.schemas.mirofish import (
    MiroFishAdvisoryEnvelope,
    MiroFishAdvisoryRunRequest,
	MiroFishBridgeResponse,
	MiroFishReportGenerateRequest,
	MiroFishReportStatusRequest,
    MiroFishNormalizedAdvisory,
	MiroFishSimulationCreateRequest,
	MiroFishSimulationPrepareRequest,
	MiroFishSimulationStartRequest,
)
from app.services.mirofish_service import MiroFishService

router = APIRouter()


def _extract_nested(data: dict[str, Any] | None, *keys: str) -> Any:
    """Safely extract nested keys from dictionaries."""
    current: Any = data or {}
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _extract_report_text(raw_report: Any) -> str:
    """Derive a single text block from different report payload shapes."""
    if isinstance(raw_report, str):
        return raw_report
    if not isinstance(raw_report, dict):
        return ""

    candidates = [
        _extract_nested(raw_report, "data", "markdown_content"),
        _extract_nested(raw_report, "data", "summary"),
        _extract_nested(raw_report, "data", "content"),
        _extract_nested(raw_report, "markdown_content"),
        _extract_nested(raw_report, "summary"),
        _extract_nested(raw_report, "content"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    sections = _extract_nested(raw_report, "data", "sections")
    if isinstance(sections, list):
        joined = []
        for section in sections:
            if isinstance(section, dict) and isinstance(section.get("content"), str):
                joined.append(section["content"].strip())
        return "\n".join([s for s in joined if s])

    return ""


def _normalize_advisory(report_text: str) -> MiroFishNormalizedAdvisory:
    """Normalize free-form report text into actionable advisory fields."""
    text = (report_text or "").strip()
    low = text.lower()

    risk_off_tokens = ["risk-off", "bearish", "downside", "drawdown", "selloff", "crash"]
    risk_on_tokens = ["risk-on", "bullish", "upside", "breakout", "accumulation", "rally"]
    high_tail_tokens = ["tail risk", "black swan", "liquidity stress", "extreme volatility", "panic"]
    low_tail_tokens = ["stable", "contained volatility", "low risk", "muted volatility"]

    risk_off_score = sum(1 for t in risk_off_tokens if t in low)
    risk_on_score = sum(1 for t in risk_on_tokens if t in low)

    if risk_off_score > risk_on_score:
        scenario_bias = "risk_off"
    elif risk_on_score > risk_off_score:
        scenario_bias = "risk_on"
    else:
        scenario_bias = "neutral"

    tail_high_score = sum(1 for t in high_tail_tokens if t in low)
    tail_low_score = sum(1 for t in low_tail_tokens if t in low)
    tail_risk_score = 0.5
    if tail_high_score > tail_low_score:
        tail_risk_score = 0.75
    elif tail_low_score > tail_high_score:
        tail_risk_score = 0.3

    if len(text) >= 1200:
        narrative_confidence = 0.8
    elif len(text) >= 500:
        narrative_confidence = 0.68
    elif len(text) >= 120:
        narrative_confidence = 0.55
    else:
        narrative_confidence = 0.4

    summary = text[:800] if text else "No report content available from MiroFish."

    return MiroFishNormalizedAdvisory(
        scenario_bias=scenario_bias,
        tail_risk_score=round(float(tail_risk_score), 4),
        narrative_confidence=round(float(narrative_confidence), 4),
        summary=summary,
    )


async def _store_advisory(
    db: AsyncSession,
    envelope: MiroFishAdvisoryEnvelope,
    degraded: bool,
    raw_payload: Any,
) -> None:
    """Persist normalized advisory output for downstream consumption."""
    if not envelope.normalized:
        return

    record = MiroFishAdvisory(
        symbol=(envelope.symbol or None),
        simulation_id=envelope.simulation_id,
        task_id=envelope.task_id,
        report_id=envelope.report_id,
        scenario_bias=envelope.normalized.scenario_bias,
        tail_risk_score=envelope.normalized.tail_risk_score,
        narrative_confidence=envelope.normalized.narrative_confidence,
        summary=envelope.normalized.summary,
        status=envelope.status,
        degraded=degraded,
        raw_payload=raw_payload if isinstance(raw_payload, dict) else {"raw": str(raw_payload)},
        created_at=datetime.utcnow(),
    )

    db.add(record)
    await db.commit()


@router.get("/health", response_model=MiroFishBridgeResponse)
async def mirofish_health() -> MiroFishBridgeResponse:
    """Check MiroFish connectivity and readiness."""
    service = MiroFishService()
    result = await service.health()
    return MiroFishBridgeResponse(**result)


@router.post("/simulation/create", response_model=MiroFishBridgeResponse)
async def create_simulation(payload: MiroFishSimulationCreateRequest) -> MiroFishBridgeResponse:
    """Create a MiroFish simulation from existing project/graph IDs."""
    service = MiroFishService()
    result = await service.create_simulation(payload.model_dump(exclude_none=True))
    return MiroFishBridgeResponse(**result)


@router.post("/simulation/prepare", response_model=MiroFishBridgeResponse)
async def prepare_simulation(payload: MiroFishSimulationPrepareRequest) -> MiroFishBridgeResponse:
    """Prepare MiroFish simulation environment and profiles."""
    service = MiroFishService()
    result = await service.prepare_simulation(payload.model_dump(exclude_none=True))
    return MiroFishBridgeResponse(**result)


@router.post("/simulation/start", response_model=MiroFishBridgeResponse)
async def start_simulation(payload: MiroFishSimulationStartRequest) -> MiroFishBridgeResponse:
    """Start a prepared MiroFish simulation."""
    service = MiroFishService()
    result = await service.start_simulation(payload.model_dump(exclude_none=True))
    return MiroFishBridgeResponse(**result)


@router.post("/report/generate", response_model=MiroFishBridgeResponse)
async def generate_report(payload: MiroFishReportGenerateRequest) -> MiroFishBridgeResponse:
    """Start report generation for a simulation in MiroFish."""
    service = MiroFishService()
    result = await service.generate_report(payload.model_dump(exclude_none=True))
    return MiroFishBridgeResponse(**result)


@router.post("/report/status", response_model=MiroFishBridgeResponse)
async def get_report_status(payload: MiroFishReportStatusRequest) -> MiroFishBridgeResponse:
    """Check MiroFish report generation status by task or simulation id."""
    service = MiroFishService()
    result = await service.report_status(payload.model_dump(exclude_none=True))
    return MiroFishBridgeResponse(**result)


@router.get("/report/by-simulation/{simulation_id}", response_model=MiroFishBridgeResponse)
async def get_report_by_simulation(simulation_id: str) -> MiroFishBridgeResponse:
    """Fetch generated report data for a simulation ID."""
    service = MiroFishService()
    result = await service.report_by_simulation(simulation_id)
    return MiroFishBridgeResponse(**result)


@router.post("/advisory/run", response_model=MiroFishAdvisoryEnvelope)
async def run_advisory(
    payload: MiroFishAdvisoryRunRequest,
    db: AsyncSession = Depends(get_db),
) -> MiroFishAdvisoryEnvelope:
    """Run report generation + polling + normalization and optionally persist result."""
    service = MiroFishService()

    generate_result = await service.generate_report(
        {
            "simulation_id": payload.simulation_id,
            "force_regenerate": payload.force_regenerate,
        }
    )

    generate_data = generate_result.get("data") if isinstance(generate_result, dict) else None
    task_id = _extract_nested(generate_data, "data", "task_id") or _extract_nested(generate_data, "task_id")
    report_id = _extract_nested(generate_data, "data", "report_id") or _extract_nested(generate_data, "report_id")

    if not task_id and not report_id and generate_result.get("status") in {"disabled", "error"}:
        envelope = MiroFishAdvisoryEnvelope(
            simulation_id=payload.simulation_id,
            symbol=payload.symbol,
            status=generate_result.get("status", "error"),
            completed=False,
            timed_out=False,
            normalized=MiroFishNormalizedAdvisory(
                scenario_bias="neutral",
                tail_risk_score=0.5,
                narrative_confidence=0.3,
                summary=generate_result.get("message", "MiroFish unavailable"),
            ),
            polls=0,
        )
        if payload.store_result:
            await _store_advisory(
                db,
                envelope,
                degraded=bool(generate_result.get("degraded", False)),
                raw_payload=generate_result,
            )
        return envelope

    completed = False
    timed_out = False
    polls = 0
    status = "processing"
    status_payload: dict[str, Any] | None = None

    loop = asyncio.get_running_loop()
    deadline = loop.time() + payload.wait_timeout_seconds
    while loop.time() < deadline:
        polls += 1
        status_result = await service.report_status(
            {
                "task_id": task_id,
                "simulation_id": payload.simulation_id,
            }
        )
        status_payload = status_result

        status_data = status_result.get("data") if isinstance(status_result, dict) else None
        status_value = (
            _extract_nested(status_data, "data", "status")
            or _extract_nested(status_data, "status")
            or status_result.get("status")
            or "processing"
        )
        status = str(status_value)

        if status in {"completed", "success", "ready"}:
            completed = True
            break
        if status in {"failed", "error"}:
            break

        await asyncio.sleep(payload.poll_interval_seconds)

    if not completed and status not in {"failed", "error"}:
        timed_out = True
        status = "timeout"

    report_result = await service.report_by_simulation(payload.simulation_id)
    report_data = report_result.get("data") if isinstance(report_result, dict) else None
    report_id = report_id or _extract_nested(report_data, "data", "report_id") or _extract_nested(
        report_data, "report_id"
    )

    report_text = _extract_report_text(report_data)
    if not report_text and status_payload:
        report_text = _extract_report_text(status_payload)

    normalized = _normalize_advisory(report_text)
    envelope = MiroFishAdvisoryEnvelope(
        simulation_id=payload.simulation_id,
        symbol=payload.symbol,
        task_id=task_id,
        report_id=report_id,
        completed=completed,
        timed_out=timed_out,
        status=status,
        normalized=normalized,
        raw_report=report_data,
        polls=polls,
    )

    if payload.store_result:
        await _store_advisory(
            db,
            envelope,
            degraded=bool(report_result.get("degraded", False)),
            raw_payload=(report_data if isinstance(report_data, dict) else report_result),
        )

    return envelope


@router.get("/advisory/latest", response_model=MiroFishAdvisoryEnvelope)
async def get_latest_advisory(
    symbol: str | None = None,
    simulation_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> MiroFishAdvisoryEnvelope:
    """Return latest stored normalized advisory, optionally filtered."""
    query = select(MiroFishAdvisory)
    if symbol:
        query = query.where(MiroFishAdvisory.symbol == symbol.upper())
    if simulation_id:
        query = query.where(MiroFishAdvisory.simulation_id == simulation_id)
    query = query.order_by(desc(MiroFishAdvisory.created_at)).limit(1)

    result = await db.execute(query)
    row = result.scalar_one_or_none()

    if not row:
        return MiroFishAdvisoryEnvelope(
            simulation_id=simulation_id or "",
            symbol=symbol.upper() if symbol else None,
            status="not_found",
            completed=False,
            timed_out=False,
            normalized=MiroFishNormalizedAdvisory(
                scenario_bias="neutral",
                tail_risk_score=0.5,
                narrative_confidence=0.0,
                summary="No stored MiroFish advisory found.",
            ),
            polls=0,
        )

    return MiroFishAdvisoryEnvelope(
        simulation_id=row.simulation_id,
        symbol=row.symbol,
        task_id=row.task_id,
        report_id=row.report_id,
        completed=row.status in {"completed", "success", "ready"},
        timed_out=row.status == "timeout",
        status=row.status,
        normalized=MiroFishNormalizedAdvisory(
            scenario_bias=row.scenario_bias,
            tail_risk_score=float(row.tail_risk_score),
            narrative_confidence=float(row.narrative_confidence),
            summary=row.summary,
        ),
        raw_report=row.raw_payload,
        polls=0,
    )
