"""Domain tools for the Mitigation Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from war_room.environment import Environment
from war_room.retrieval import BM25Index


class RunbookMatch(BaseModel):
    """Matched operational runbook with BM25 score and recommendations."""

    doc_id: str = Field(description="Runbook identifier (e.g. RB-001-deploy-rollback)")
    score: float = Field(description="BM25 relevance score")
    title: str = Field(description="Runbook title")
    summary: str = Field(description="Summary of recommended actions")


class PastIncidentMatch(BaseModel):
    """Historical incident matching current symptoms."""

    incident_id: str = Field(description="Past incident ID")
    score: float = Field(description="BM25 similarity score")
    title: str = Field(description="Title of historical incident")
    root_cause: str = Field(description="Diagnosed root cause")
    resolution: str = Field(description="Applied mitigation (rollback, restart, failover)")
    target_service: str = Field(description="Target service mitigated")


class RollbackCandidate(BaseModel):
    """Release candidate available for rollback."""

    current_version: str = Field(description="Currently deployed release version")
    target_version: str = Field(description="Candidate version to roll back to")
    is_safe: bool = Field(description="Whether rollback is safe without schema conflicts")
    breaking_db_migration: bool = Field(description="Whether destructive DB migration was applied")
    reason: str = Field(description="Safety assessment rationale")


class FailoverReadinessReport(BaseModel):
    """Assessment of standby or secondary provider failover readiness."""

    service: str = Field(description="Service evaluated")
    has_secondary: bool = Field(description="Whether a secondary standby provider exists")
    secondary_target: str = Field(description="Name of the secondary provider or replica")
    is_ready: bool = Field(description="Whether secondary is warm and healthy")
    sync_lag_seconds: float = Field(description="Data replication lag in seconds")
    rationale: str = Field(description="Explanation of readiness status")


def search_runbooks(
    retriever: BM25Index[dict[str, Any]],
    query: str,
    top_k: int = 3,
) -> list[RunbookMatch]:
    """Retrieve operational runbooks relevant to observed symptoms using Okapi BM25."""
    results = retriever.search(query=query, top_k=top_k)
    matches = []
    for r in results:
        doc = r.document
        content = doc.get("content", "")
        # Extract title from first markdown header
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        title = lines[0].lstrip("#").strip() if lines else r.doc_id
        summary = " ".join(lines[1:4])[:200] if len(lines) > 1 else ""

        matches.append(
            RunbookMatch(
                doc_id=r.doc_id,
                score=round(r.score, 4),
                title=title,
                summary=summary,
            )
        )
    return matches


def find_similar_past_incidents(
    retriever: BM25Index[dict[str, Any]],
    symptoms: str,
    top_k: int = 3,
) -> list[PastIncidentMatch]:
    """Find historical incident resolutions matching current symptoms."""
    results = retriever.search(query=symptoms, top_k=top_k)
    matches = []
    for r in results:
        doc = r.document
        matches.append(
            PastIncidentMatch(
                incident_id=r.doc_id,
                score=round(r.score, 4),
                title=str(doc.get("title", "")),
                root_cause=str(doc.get("root_cause", "")),
                resolution=str(doc.get("resolution", "")),
                target_service=str(doc.get("service", "")),
            )
        )
    return matches


def get_rollback_candidates(
    env: Environment,
    service_name: str,
) -> list[RollbackCandidate]:
    """Inspect previous releases and verify database schema compatibility for rollback."""
    deploys = env.get_deploys(service_name=service_name, lookback_minutes=60 * 24 * 30)
    if not deploys:
        return []

    latest = deploys[0]
    prev_version = latest.get("previous_version")
    breaking_db = bool(latest.get("breaking_db_migration", False))

    if not prev_version:
        return []

    if breaking_db:
        return [
            RollbackCandidate(
                current_version=latest.get("version", "unknown"),
                target_version=prev_version,
                is_safe=False,
                breaking_db_migration=True,
                reason=(
                    f"Rollback to {prev_version} is UNSAFE: Release {latest.get('version')} "
                    f"applied a breaking DB migration. Older code will fail on current schema."
                ),
            )
        ]

    return [
        RollbackCandidate(
            current_version=latest.get("version", "unknown"),
            target_version=prev_version,
            is_safe=True,
            breaking_db_migration=False,
            reason=f"Rollback to {prev_version} is safe (no destructive DB schema changes).",
        )
    ]


def check_failover_readiness(
    env: Environment,
    service_name: str,
) -> FailoverReadinessReport:
    """Evaluate secondary standby provider or read-replica readiness."""
    metrics_data = env.get_metrics(service_name)
    providers = metrics_data.get("providers", {}) if metrics_data else {}

    # Check for payments gateway secondary provider
    if "external-payments-secondary" in providers:
        sec = providers["external-payments-secondary"]
        status = sec.get("status", "UNKNOWN")
        is_ready = status == "HEALTHY"
        return FailoverReadinessReport(
            service=service_name,
            has_secondary=True,
            secondary_target="external-payments-secondary",
            is_ready=is_ready,
            sync_lag_seconds=float(sec.get("sync_lag_seconds", 0.0)),
            rationale=f"Secondary is {status} (error rate {sec.get('error_rate', 0.0)}).",
        )

    # Check for database standby replica
    if service_name == "database-cluster":
        return FailoverReadinessReport(
            service=service_name,
            has_secondary=True,
            secondary_target="database-replica-az2",
            is_ready=True,
            sync_lag_seconds=0.1,
            rationale="Secondary hot standby database replica in AZ2 is fully synchronized.",
        )

    return FailoverReadinessReport(
        service=service_name,
        has_secondary=False,
        secondary_target="",
        is_ready=False,
        sync_lag_seconds=0.0,
        rationale="No dedicated secondary provider or hot standby configured.",
    )
