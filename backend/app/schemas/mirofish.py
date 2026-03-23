"""Schemas for MiroFish sidecar integration endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class MiroFishBridgeResponse(BaseModel):
    """Standardized response for MiroFish bridge calls."""

    ok: bool = Field(..., description="Whether the bridge call succeeded")
    status: str = Field(..., description="high-level state: success|degraded|disabled|error")
    message: str = Field(..., description="Human-readable outcome")
    source: str = Field(default="mirofish", description="Upstream system")
    degraded: bool = Field(default=False, description="True when fail-open fallback was used")
    data: Optional[Any] = Field(default=None, description="Raw upstream payload when available")
    error: Optional[str] = Field(default=None, description="Error details if call failed")


class MiroFishSimulationCreateRequest(BaseModel):
    """Payload for creating a MiroFish simulation."""

    project_id: str
    graph_id: Optional[str] = None
    enable_twitter: bool = True
    enable_reddit: bool = True


class MiroFishSimulationPrepareRequest(BaseModel):
    """Payload for preparing simulation environment."""

    simulation_id: str
    entity_types: Optional[list[str]] = None
    use_llm_for_profiles: bool = True
    parallel_profile_count: int = 5
    force_regenerate: bool = False


class MiroFishSimulationStartRequest(BaseModel):
    """Payload for starting a simulation run."""

    simulation_id: str
    platform: str = "parallel"
    max_rounds: Optional[int] = None
    enable_graph_memory_update: bool = False
    force: bool = False


class MiroFishReportGenerateRequest(BaseModel):
    """Payload for report generation."""

    simulation_id: str
    force_regenerate: bool = False


class MiroFishReportStatusRequest(BaseModel):
    """Payload for report status polling."""

    task_id: Optional[str] = None
    simulation_id: Optional[str] = None


class MiroFishAdvisoryRunRequest(BaseModel):
    """Payload to orchestrate report generation, polling, and normalization."""

    simulation_id: str
    symbol: Optional[str] = None
    force_regenerate: bool = False
    wait_timeout_seconds: int = Field(default=90, ge=10, le=600)
    poll_interval_seconds: int = Field(default=5, ge=2, le=30)
    store_result: bool = True


class MiroFishAdvisoryLatestQuery(BaseModel):
    """Query params for fetching latest advisory output."""

    symbol: Optional[str] = None
    simulation_id: Optional[str] = None


class MiroFishNormalizedAdvisory(BaseModel):
    """Normalized advisory fields consumed by downstream automation."""

    scenario_bias: str = Field(..., description="risk_on|neutral|risk_off")
    tail_risk_score: float = Field(..., ge=0, le=1)
    narrative_confidence: float = Field(..., ge=0, le=1)
    summary: str


class MiroFishAdvisoryEnvelope(BaseModel):
    """Orchestration result payload with normalized advisory and metadata."""

    simulation_id: str
    symbol: Optional[str] = None
    task_id: Optional[str] = None
    report_id: Optional[str] = None
    completed: bool = False
    timed_out: bool = False
    status: str
    normalized: Optional[MiroFishNormalizedAdvisory] = None
    raw_report: Optional[Any] = None
    polls: int = 0
