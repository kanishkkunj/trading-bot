"""Lightweight model registry with MLflow hooks, A/B testing, and rollback."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

log = structlog.get_logger()
try:  # pragma: no cover - optional dependency
    import mlflow
except ImportError:  # pragma: no cover
    mlflow = None


@dataclass
class ModelRecord:
    name: str
    version: str
    path: str
    stage: str = "Staging"
    metrics: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, Any] = field(default_factory=dict)
    shadow_of: Optional[str] = None


class ModelRegistry:
    """Minimal registry supporting versions, A/B testing, and rollback."""

    def __init__(self, storage_path: str | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self.records: list[ModelRecord] = []
        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def register(self, name: str, version: str, path: str, metrics: dict[str, Any], stage: str = "Staging", tags: dict[str, Any] | None = None) -> ModelRecord:
        record = ModelRecord(name=name, version=version, path=path, metrics=metrics, stage=stage, tags=tags or {})
        self.records.append(record)
        self._persist()
        if mlflow:
            mlflow.log_params({"model_name": name, "version": version})
            mlflow.log_metrics(metrics)
        log.info("model_registered", name=name, version=version, stage=stage)
        return record

    def promote(self, name: str, version: str, stage: str) -> None:
        for rec in self.records:
            if rec.name == name and rec.version == version:
                rec.stage = stage
        self._persist()
        log.info("model_promoted", name=name, version=version, stage=stage)

    def get_active(self, name: str, stage: str = "Production") -> Optional[ModelRecord]:
        candidates = [r for r in self.records if r.name == name and r.stage == stage]
        if not candidates:
            return None
        candidates.sort(key=lambda r: r.version, reverse=True)
        return candidates[0]

    def start_shadow(self, name: str, version: str, shadow_of: str) -> None:
        for rec in self.records:
            if rec.name == name and rec.version == version:
                rec.shadow_of = shadow_of
                rec.stage = "Shadow"
        self._persist()
        log.info("shadow_started", name=name, version=version, shadow_of=shadow_of)

    def assign_canary(self, name: str, versions: dict[str, float]) -> dict[str, float]:
        total = sum(versions.values()) or 1.0
        normalized = {v: w / total for v, w in versions.items()}
        log.info("canary_assignment", name=name, weights=normalized)
        return normalized

    def rollback(self, name: str, target_version: str) -> Optional[ModelRecord]:
        target = next((r for r in self.records if r.name == name and r.version == target_version), None)
        if not target:
            log.warning("rollback_failed", reason="version_missing", name=name, version=target_version)
            return None
        target.stage = "Production"
        for rec in self.records:
            if rec.name == name and rec.version != target_version:
                rec.stage = "Archived"
        self._persist()
        log.info("rollback_complete", name=name, version=target_version)
        return target

    def _persist(self) -> None:
        if not self.storage_path:
            return
        payload = [record.__dict__ for record in self.records]
        self.storage_path.write_text(json.dumps(payload, indent=2))

    def _load(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text())
            self.records = [ModelRecord(**item) for item in data]
        except Exception as exc:  # noqa: BLE001
            log.warning("registry_load_failed", error=str(exc))
