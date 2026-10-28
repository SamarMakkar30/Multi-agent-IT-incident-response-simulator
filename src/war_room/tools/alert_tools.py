"""Domain tools for the Alert Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from war_room.environment import Environment
from war_room.guards import sanitize_untrusted_input


class AlertSignal(BaseModel):
    """Normalized incident signal extracted from raw alert payload."""

    alert_id: str = Field(description="Unique identifier of the alert")
    service: str = Field(description="Target service affected by alert")
    metric: str = Field(description="Name of the breached telemetry metric")
    current_value: float = Field(description="Observed metric value")
    threshold: float = Field(description="Configured SLO threshold")
    breach_ratio: float = Field(description="Ratio of current value to threshold")
    triggered_at: str = Field(description="Timestamp when alert fired")
    sanitized_message: str = Field(description="Safe message with injection patterns quarantined")
    untrusted_flags: list[str] = Field(default_factory=list, description="Security flags")


class SeverityScore(BaseModel):
    """Deterministic severity classification (SEV1-SEV4)."""

    severity: str = Field(description="Assigned severity level (SEV1, SEV2, SEV3, SEV4)")
    rationale: str = Field(description="Deterministic reasoning based on service tier and impact")


class ServiceMetadata(BaseModel):
    """Service ownership, tier, and SLO characteristics."""

    service: str = Field(description="Name of the service")
    tier: int = Field(description="Service criticality tier (1=Core, 2=Dependent, 3=Background)")
    owner: str = Field(description="Owning team")
    slo: float = Field(description="Target SLO availability percentage")
    user_facing: bool = Field(description="Whether the service directly serves end users")


def parse_alert(raw_alert: dict[str, Any]) -> AlertSignal:
    """Parse and normalize raw alert payload into a validated incident signal."""
    message = str(raw_alert.get("message", ""))
    sanitized_msg, flags = sanitize_untrusted_input(message)

    current_val = float(raw_alert.get("current_value", 0.0))
    threshold = float(raw_alert.get("threshold", 1.0))
    ratio = current_val / max(threshold, 1e-6)

    return AlertSignal(
        alert_id=str(raw_alert.get("alert_id", "ALT-UNKNOWN")),
        service=str(raw_alert.get("service", "unknown")),
        metric=str(raw_alert.get("metric", "unknown")),
        current_value=current_val,
        threshold=threshold,
        breach_ratio=round(ratio, 2),
        triggered_at=str(raw_alert.get("triggered_at", "")),
        sanitized_message=sanitized_msg,
        untrusted_flags=flags,
    )


def score_severity(
    tier: int,
    metric_name: str,
    breach_ratio: float,
    is_user_facing: bool,
) -> SeverityScore:
    """Compute deterministic incident severity score according to standard production rubric."""
    if tier == 1 and is_user_facing and (breach_ratio >= 2.0 or "5xx" in metric_name.lower()):
        return SeverityScore(
            severity="SEV1",
            rationale=(
                f"Tier 1 user-facing service breached critical threshold "
                f"(breach ratio {breach_ratio:.1f}x on {metric_name})"
            ),
        )
    if tier == 1 or (is_user_facing and breach_ratio >= 1.5):
        return SeverityScore(
            severity="SEV2",
            rationale=(
                f"High-impact service degradation on Tier {tier} (breach ratio {breach_ratio:.1f}x)"
            ),
        )
    if breach_ratio >= 1.0:
        return SeverityScore(
            severity="SEV3",
            rationale=f"Moderate SLO threshold breach on Tier {tier} component",
        )
    return SeverityScore(
        severity="SEV4",
        rationale="Minor latency or informational anomaly within soft recovery boundaries",
    )


def get_service_metadata(env: Environment, service_name: str) -> ServiceMetadata:
    """Fetch service ownership, tier, and SLO characteristics from topology registry."""
    meta = env.get_service_metadata(service_name)
    if not meta:
        return ServiceMetadata(
            service=service_name,
            tier=3,
            owner="unknown",
            slo=0.99,
            user_facing=False,
        )
    return ServiceMetadata(
        service=service_name,
        tier=meta.get("tier", 3),
        owner=meta.get("owner", "unknown"),
        slo=meta.get("slo", 0.99),
        user_facing=meta.get("user_facing", False),
    )
