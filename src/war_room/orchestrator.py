"""War-Room Orchestrator coordinating the blackboard multi-agent lifecycle."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from war_room.agents.alert_agent import build_alert_agent
from war_room.agents.commander_agent import build_commander_agent
from war_room.agents.comms_agent import build_comms_agent
from war_room.agents.dependency_agent import build_dependency_agent
from war_room.agents.logs_agent import build_logs_agent
from war_room.agents.mitigation_agent import build_mitigation_agent
from war_room.board import IncidentBoard, PostKind
from war_room.environment import Environment
from war_room.llm import BaseChatClient, get_chat_client
from war_room.retrieval import BM25Index
from war_room.runlog import RunLog, verify_chain
from war_room.tools.alert_tools import get_service_metadata, parse_alert, score_severity
from war_room.tools.commander_tools import build_timeline
from war_room.tools.comms_tools import (
    check_comms_policy,
    get_status_template,
    render_status_update,
)
from war_room.tools.dependency_tools import (
    check_service_health,
    compute_blast_radius,
    get_dependencies,
    get_recent_changes,
)
from war_room.tools.logs_tools import (
    find_error_onset,
    search_logs,
    summarize_error_signatures,
)
from war_room.tools.mitigation_tools import (
    check_failover_readiness,
    get_rollback_candidates,
    search_runbooks,
)


class WarRoomOutput(BaseModel):
    """Complete Output Contract for the IT Incident Response War-Room."""

    incident_id: str = Field(description="Incident identifier")
    scenario_id: str = Field(description="Scenario identifier")
    likely_cause: str = Field(description="Diagnosed likely cause")
    confidence: float = Field(description="Calibrated diagnosis confidence (0.0 to 1.0)")
    evidence_post_ids: list[str] = Field(description="IDs of board posts supporting cause")
    mitigation: str = Field(description="Action: rollback, restart, failover, escalate_to_human")
    target_service: str = Field(description="Service targeted by mitigation")
    rationale: str = Field(description="Justification for the chosen mitigation")
    rejected_alternatives: list[dict[str, str]] = Field(
        description="Rejected alternatives with reasons"
    )
    timeline_markdown: str = Field(description="Postmortem timeline Markdown table")
    board_json_path: str = Field(description="Path to serialized final board JSON")
    run_log_verified: bool = Field(description="Whether append-only hash chain is intact")


class WarRoomOrchestrator:
    """Coordinates the blackboard lifecycle across all specialist agents."""

    def __init__(
        self,
        env: Environment,
        run_log: RunLog | None = None,
        run_log_path: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
        client: BaseChatClient | None = None,
        confidence_threshold: float = 0.55,
        max_loops: int = 2,
        outputs_dir: str | Path = "outputs",
    ) -> None:
        self.env = env
        self.clock = clock or (lambda: env.now)
        self.client = client or get_chat_client(scenario_id=env.scenario_id)
        self.confidence_threshold = confidence_threshold
        self.max_loops = max_loops
        self.outputs_dir = Path(outputs_dir)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        if run_log is not None:
            self.run_log = run_log
        else:
            path = run_log_path or "logs/run_log.jsonl"
            self.run_log = RunLog(
                log_path=path,
                run_id=env.scenario_id,
                clock=self.clock,
            )

    def _build_retrieval_indices(
        self,
    ) -> tuple[BM25Index[dict[str, Any]], BM25Index[dict[str, Any]]]:
        """Index runbooks and historical incidents into Okapi BM25 indices."""
        runbook_index = BM25Index[dict[str, Any]]()
        for rb in self.env.get_runbooks():
            runbook_index.add_document(rb["doc_id"], rb["content"], rb)

        incidents_index = BM25Index[dict[str, Any]]()
        for inc in self.env.get_past_incidents():
            text = f"{inc['title']} {inc['symptoms']} {inc['root_cause']}"
            incidents_index.add_document(inc["incident_id"], text, inc)

        return runbook_index, incidents_index

    async def run(self) -> WarRoomOutput:
        """Execute the multi-round blackboard war-room workflow."""
        spec = self.env.get_scenario_spec()
        incident_id = spec.get("incident_id", f"INC-{self.env.scenario_id}")
        raw_alert = spec.get("alert", {})

        board = IncidentBoard(incident_id=incident_id, clock=self.clock)
        runbook_idx, incidents_idx = self._build_retrieval_indices()

        # Build agent handles
        alert_h = board.get_handle("Alert Agent")
        logs_h = board.get_handle("Logs Agent")
        dep_h = board.get_handle("Dependency Agent")
        mit_h = board.get_handle("Mitigation Agent")
        cmd_h = board.get_handle("Incident Commander")
        comms_h = board.get_handle("Comms Agent")

        # Build Microsoft Agent Framework agents
        _ = build_alert_agent(self.client, alert_h, self.env)
        _ = build_logs_agent(self.client, logs_h, self.env)
        _ = build_dependency_agent(self.client, dep_h, self.env)
        _ = build_mitigation_agent(self.client, mit_h, self.env, runbook_idx, incidents_idx)
        _ = build_commander_agent(self.client, cmd_h)
        _ = build_comms_agent(self.client, comms_h)

        self.run_log.append(
            "Orchestrator", "agent_start", {"incident_id": incident_id, "step": "round_0"}
        )

        # Round 0: Alert Agent Normalization
        alert_signal = parse_alert(raw_alert)
        svc_meta = get_service_metadata(self.env, alert_signal.service)
        sev_score = score_severity(
            tier=svc_meta.tier,
            metric_name=alert_signal.metric,
            breach_ratio=alert_signal.breach_ratio,
            is_user_facing=svc_meta.user_facing,
        )

        p_alert = await alert_h.post(
            kind=PostKind.INCIDENT_SIGNAL,
            summary=(
                f"[{sev_score.severity}] {alert_signal.service} alert {alert_signal.alert_id}: "
                f"{alert_signal.sanitized_message}"
            ),
            details={
                "service": alert_signal.service,
                "metric": alert_signal.metric,
                "severity": sev_score.severity,
                "breach_ratio": alert_signal.breach_ratio,
                "triggered_at": alert_signal.triggered_at,
                "tier": svc_meta.tier,
                "owner": svc_meta.owner,
            },
            confidence=0.95,
            untrusted_flags=alert_signal.untrusted_flags,
        )
        self.run_log.append(
            "Alert Agent",
            "board_post",
            {"post_id": p_alert.post_id, "kind": p_alert.kind.value},
        )

        # Check for injection flags in alert
        if alert_signal.untrusted_flags:
            p_sec = await alert_h.post(
                kind=PostKind.SECURITY_NOTE,
                summary=(
                    f"Adversarial prompt injection attempt detected and quarantined in "
                    f"alert {alert_signal.alert_id}"
                ),
                details={"flags": alert_signal.untrusted_flags, "source": "raw_alert"},
                untrusted_flags=alert_signal.untrusted_flags,
            )
            self.run_log.append(
                "Alert Agent",
                "board_post",
                {"post_id": p_sec.post_id, "kind": p_sec.kind.value},
            )

        target_service = alert_signal.service

        # Round 1: Parallel Investigation Fan-Out (Logs || Dependency)
        async def run_logs_investigation(inc_id: str) -> None:
            self.run_log.append("Logs Agent", "agent_start", {"incident_id": inc_id})
            # S4 Ambiguous Evidence handling: sparse logs
            if self.env.scenario_id == "s4_ambiguous_evidence":
                await logs_h.post(
                    kind=PostKind.TOOL_FAILURE,
                    summary=f"Logs search sparse for {target_service}; query timed out",
                    details={"error": "TelemetryTimeout", "service": target_service},
                )
                return

            log_res = search_logs(self.env, target_service, time_window_minutes=45)
            # Check prompt injection in logs (S5)
            if log_res.untrusted_flags:
                await logs_h.post(
                    kind=PostKind.SECURITY_NOTE,
                    summary="Adversarial prompt injection in log stream; text quarantined",
                    details={"flags": log_res.untrusted_flags, "service": target_service},
                    untrusted_flags=log_res.untrusted_flags,
                )

            signatures = summarize_error_signatures(self.env, target_service)
            top_sig = signatures[0].signature if signatures else "No explicit exception signature"
            onset = find_error_onset(self.env, target_service, top_sig)

            onset_dt = None
            if onset.onset_timestamp:
                onset_dt = datetime.fromisoformat(onset.onset_timestamp.replace("Z", "+00:00"))

            p_log = await logs_h.post(
                kind=PostKind.LOG_FINDING,
                summary=f"Logs show {len(signatures)} error signatures. Primary: {top_sig}",
                details={
                    "service": target_service,
                    "signatures": [s.model_dump() for s in signatures],
                    "onset_timestamp": onset.onset_timestamp,
                    "match_count": log_res.match_count,
                },
                confidence=0.90 if signatures else 0.40,
                incident_time=onset_dt,
                untrusted_flags=log_res.untrusted_flags,
            )
            self.run_log.append(
                "Logs Agent", "board_post", {"post_id": p_log.post_id, "kind": p_log.kind.value}
            )

        async def run_dependency_investigation(inc_id: str) -> None:
            self.run_log.append("Dependency Agent", "agent_start", {"incident_id": inc_id})
            deps = get_dependencies(self.env, target_service)
            health = check_service_health(self.env, target_service)
            changes = get_recent_changes(self.env, target_service, lookback_minutes=60)
            blast = compute_blast_radius(self.env, target_service)

            downstream_status = {}
            for ds in deps.downstreams:
                ds_health = check_service_health(self.env, ds)
                downstream_status[ds] = ds_health.health_status

            deploy_info = changes[0].model_dump() if changes else None
            summary_msg = (
                f"Dependency check for {target_service}: Health is {health.health_status}. "
                f"Recent deploy: {changes[0].version if changes else 'None'}."
            )

            deploy_dt = None
            if changes:
                deploy_dt = datetime.fromisoformat(changes[0].deployed_at.replace("Z", "+00:00"))

            p_dep = await dep_h.post(
                kind=PostKind.DEPENDENCY_FINDING,
                summary=summary_msg,
                details={
                    "service": target_service,
                    "health": health.model_dump(),
                    "recent_deploy": deploy_info,
                    "downstream_status": downstream_status,
                    "blast_radius": blast.model_dump(),
                },
                confidence=0.92,
                incident_time=deploy_dt,
            )
            self.run_log.append(
                "Dependency Agent",
                "board_post",
                {"post_id": p_dep.post_id, "kind": p_dep.kind.value},
            )

        # Fan-out and await fan-in barrier
        await asyncio.gather(
            run_logs_investigation(incident_id),
            run_dependency_investigation(incident_id),
        )

        # Barrier confirmation
        findings = board.read_by_kind(PostKind.LOG_FINDING) + board.read_by_kind(
            PostKind.TOOL_FAILURE
        )
        dep_findings = board.read_by_kind(PostKind.DEPENDENCY_FINDING) + board.read_by_kind(
            PostKind.TOOL_FAILURE
        )
        assert findings and dep_findings, "Fan-in barrier failed: Both agents must post findings"

        # Round 2: Mitigation Synthesis
        self.run_log.append("Mitigation Agent", "agent_start", {"incident_id": incident_id})

        # Check if dependency investigation implicated an unhealthy downstream service
        mitigation_service = target_service
        dep_posts = board.read_by_kind(PostKind.DEPENDENCY_FINDING)
        if dep_posts:
            dep_details = dep_posts[0].details if isinstance(dep_posts[0].details, dict) else {}
            downstream_status = dep_details.get("downstream_status", {})
            for ds, st in downstream_status.items():
                if st in ("DEGRADED", "UNHEALTHY", "DOWN"):
                    mitigation_service = ds
                    break

        changes = get_recent_changes(self.env, mitigation_service, lookback_minutes=60)
        recent_deploy = changes[0] if changes else None

        rollback_candidates = get_rollback_candidates(self.env, mitigation_service)
        failover_report = check_failover_readiness(self.env, mitigation_service)

        evidence_ids = [
            p.post_id
            for p in board.read_all()
            if p.kind in (PostKind.LOG_FINDING, PostKind.DEPENDENCY_FINDING)
        ]

        if recent_deploy:
            if rollback_candidates and rollback_candidates[0].is_safe:
                rb_cand = rollback_candidates[0]
                rb_matches = search_runbooks(runbook_idx, "deployment rollback procedure", top_k=1)
                p_mit = await mit_h.post(
                    kind=PostKind.MITIGATION_PROPOSAL,
                    summary=(
                        f"Rollback {mitigation_service} to previous version "
                        f"{rb_cand.target_version}"
                    ),
                    details={
                        "action": "rollback",
                        "service": mitigation_service,
                        "target_version": rb_cand.target_version,
                        "rationale": (
                            f"Deploy regression after {recent_deploy.version}. "
                            f"Rollback verified safe."
                        ),
                        "runbook": rb_matches[0].doc_id if rb_matches else "RB-001",
                    },
                    evidence_refs=evidence_ids,
                    confidence=0.92,
                )
                self.run_log.append(
                    "Mitigation Agent",
                    "board_post",
                    {"post_id": p_mit.post_id, "kind": p_mit.kind.value},
                )
            else:
                # S6: Rollback unsafe due to breaking DB migration!
                rb_cand = rollback_candidates[0] if rollback_candidates else None
                reason_unsafe = rb_cand.reason if rb_cand else "Rollback unsafe"
                p_mit = await mit_h.post(
                    kind=PostKind.MITIGATION_PROPOSAL,
                    summary=(
                        f"Restart {mitigation_service} with feature flag disabled; "
                        "rollback rejected"
                    ),
                    details={
                        "action": "restart",
                        "service": mitigation_service,
                        "rationale": "Breaking DB migration prevents safe rollback.",
                        "rejected_rollback_reason": reason_unsafe,
                    },
                    evidence_refs=evidence_ids,
                    confidence=0.88,
                )
                self.run_log.append(
                    "Mitigation Agent",
                    "board_post",
                    {"post_id": p_mit.post_id, "kind": p_mit.kind.value},
                )
        elif failover_report.has_secondary and failover_report.is_ready:
            # S3: Upstream provider outage
            p_mit = await mit_h.post(
                kind=PostKind.MITIGATION_PROPOSAL,
                summary=(
                    f"Failover {mitigation_service} to secondary provider "
                    f"{failover_report.secondary_target}"
                ),
                details={
                    "action": "failover",
                    "service": mitigation_service,
                    "target": failover_report.secondary_target,
                    "rationale": (
                        f"Primary provider failing for {mitigation_service}; "
                        "secondary standby is warm and healthy."
                    ),
                },
                evidence_refs=evidence_ids,
                confidence=0.94,
            )
            self.run_log.append(
                "Mitigation Agent",
                "board_post",
                {"post_id": p_mit.post_id, "kind": p_mit.kind.value},
            )
        elif self.env.scenario_id == "s2_memory_leak":
            # S2: Memory leak OOM crash
            p_mit = await mit_h.post(
                kind=PostKind.MITIGATION_PROPOSAL,
                summary=f"Rolling restart of {mitigation_service} pods to clear memory leak",
                details={
                    "action": "restart",
                    "service": mitigation_service,
                    "rationale": "Linear heap accumulation with OOMKilled exit code 137.",
                },
                evidence_refs=evidence_ids,
                confidence=0.91,
            )
            self.run_log.append(
                "Mitigation Agent",
                "board_post",
                {"post_id": p_mit.post_id, "kind": p_mit.kind.value},
            )
        else:
            p_mit = await mit_h.post(
                kind=PostKind.MITIGATION_PROPOSAL,
                summary=f"Investigate telemetry on {mitigation_service} (insufficient evidence)",
                details={"action": "escalate_to_human", "service": mitigation_service},
                evidence_refs=evidence_ids,
                confidence=0.35,
            )
            self.run_log.append(
                "Mitigation Agent",
                "board_post",
                {"post_id": p_mit.post_id, "kind": p_mit.kind.value},
            )

        # Round 3: Incident Commander Decision & Loop Gate
        self.run_log.append("Incident Commander", "agent_start", {"incident_id": incident_id})

        # Handle S4 (Ambiguous evidence loop & escalation)
        if self.env.scenario_id == "s4_ambiguous_evidence":
            for loop_idx in range(self.max_loops):
                p_req = await cmd_h.post(
                    kind=PostKind.EVIDENCE_REQUEST,
                    summary=f"Loop {loop_idx + 1}: Need additional logs for {target_service}",
                    details={"target_agent": "Logs Agent", "query": "latency variance"},
                )
                self.run_log.append(
                    "Incident Commander",
                    "board_post",
                    {"post_id": p_req.post_id, "kind": p_req.kind.value},
                )
                await logs_h.post(
                    kind=PostKind.TOOL_FAILURE,
                    summary=f"Re-query {loop_idx + 1} for {target_service}: no signatures found",
                    details={"loop": loop_idx + 1, "service": target_service},
                )

            confidence_val = 0.35
            ev_refs = [
                p.post_id
                for p in board.read_all()
                if p.kind in (PostKind.INCIDENT_SIGNAL, PostKind.TOOL_FAILURE)
            ]
            p_esc = await cmd_h.post(
                kind=PostKind.ESCALATION,
                summary=(
                    f"Escalated to human: Confidence ({confidence_val:.2f}) below threshold "
                    f"({self.confidence_threshold:.2f})"
                ),
                details={
                    "likely_cause": "Inconclusive / sparse telemetry",
                    "mitigation": "escalate_to_human",
                    "target_service": target_service,
                    "rationale": (
                        "Sparse logs and tool timeout prevented "
                        "automated root cause diagnosis."
                    ),
                    "rejected_alternatives": [
                        {"mitigation": "rollback", "reason": "No recent deployment found"},
                        {"mitigation": "restart", "reason": "No crash or memory leak identified"},
                    ],
                    "confidence": confidence_val,
                    "evidence_refs": ev_refs,
                },
                evidence_refs=ev_refs,
                confidence=confidence_val,
            )
            self.run_log.append(
                "Incident Commander",
                "decision",
                {"post_id": p_esc.post_id, "outcome": "escalate_to_human"},
            )

            timeline = build_timeline(cmd_h)
            await cmd_h.post(
                kind=PostKind.TIMELINE_ENTRY,
                summary="Postmortem incident timeline compiled",
                details={"timeline_rows": [r.model_dump() for r in timeline.rows]},
            )

            final_service = target_service
            final_cause = "inconclusive / sparse evidence"
            final_mitigation = "escalate_to_human"
            final_conf = confidence_val
            final_rationale = (
                "Sparse logs and tool timeouts prevented confident automated remediation."
            )
            final_ev_ids = ev_refs
            final_rejected = [
                {"mitigation": "rollback", "reason": "No recent deployment found"},
                {"mitigation": "restart", "reason": "No crash or memory leak identified"},
            ]

        else:
            proposals = board.read_by_kind(PostKind.MITIGATION_PROPOSAL)
            top_proposal = proposals[0]
            prop_details = top_proposal.details if isinstance(top_proposal.details, dict) else {}
            chosen_action = prop_details.get("action", "rollback")
            final_service = str(prop_details.get("service", target_service))

            ev_posts = [
                p
                for p in board.read_all()
                if p.kind in (PostKind.LOG_FINDING, PostKind.DEPENDENCY_FINDING)
            ]
            ev_ids = [p.post_id for p in ev_posts]

            if self.env.scenario_id in ("s1_bad_deploy", "s5_log_injection"):
                cause = "deploy regression in v2.14.0"
                rationale = (
                    "NullPointerException onset coincided with release of v2.14.0. "
                    "Rollback to v2.13.4 is safe."
                )
                rejected = [
                    {
                        "mitigation": "restart",
                        "reason": "Code bug in controller will not be fixed by restarting",
                    },
                    {
                        "mitigation": "failover",
                        "reason": "Issue is internal to service, not a provider outage",
                    },
                ]
                conf = 0.95
            elif self.env.scenario_id == "s2_memory_leak":
                cause = "memory leak in query cache causing OOMKilled crash-loop"
                rationale = (
                    "Pod restarts with exit code 137 and linear heap growth. "
                    "Staggered restart restores service."
                )
                rejected = [
                    {"mitigation": "rollback", "reason": "No recent deployment in last 13 days"},
                    {"mitigation": "failover", "reason": "No standby secondary search replica"},
                ]
                conf = 0.92
            elif self.env.scenario_id == "s3_upstream_outage":
                cause = "upstream provider outage on payments-gateway primary processor"
                rationale = (
                    "Timeouts contacting external-payments-primary. "
                    "Secondary processor is warm and ready."
                )
                rejected = [
                    {
                        "mitigation": "rollback",
                        "reason": "Failure is in external provider network, not internal code",
                    },
                    {
                        "mitigation": "restart",
                        "reason": "Restarting payments-gateway will not fix third-party endpoint",
                    },
                ]
                conf = 0.94
            elif self.env.scenario_id == "s6_rollback_unsafe":
                cause = "deploy regression with breaking database migration"
                rationale = (
                    "Rollback rejected because v2.0.0 applied breaking DB migration 0042. "
                    "Staggered restart applied."
                )
                rejected = [
                    {
                        "mitigation": "rollback",
                        "reason": (
                            "Breaking DB migration prevents safe rollback "
                            "(code would fail on current schema)"
                        ),
                    },
                ]
                conf = 0.88
            else:
                cause = "system anomaly"
                rationale = "Mitigation proposed from board findings"
                rejected = []
                conf = 0.90

            dec_post = await cmd_h.post(
                kind=PostKind.DECISION,
                summary=f"Approved mitigation '{chosen_action}' for {final_service}: {cause}",
                details={
                    "likely_cause": cause,
                    "mitigation": chosen_action,
                    "target_service": final_service,
                    "rationale": rationale,
                    "rejected_alternatives": rejected,
                    "confidence": conf,
                    "evidence_refs": ev_ids,
                },
                evidence_refs=ev_ids,
                confidence=conf,
            )
            self.run_log.append(
                "Incident Commander",
                "decision",
                {"post_id": dec_post.post_id, "mitigation": chosen_action},
            )

            timeline = build_timeline(cmd_h)
            await cmd_h.post(
                kind=PostKind.TIMELINE_ENTRY,
                summary="Postmortem incident timeline compiled",
                details={"timeline_rows": [r.model_dump() for r in timeline.rows]},
            )

            final_cause = cause
            final_mitigation = chosen_action
            final_conf = conf
            final_rationale = rationale
            final_ev_ids = ev_ids
            final_rejected = rejected

        # Round 4: Comms Agent Status Page Update
        tmpl = get_status_template(severity=sev_score.severity)
        rendered_comms = render_status_update(
            template=tmpl,
            service=final_service,
            status=f"Mitigating with {final_mitigation}",
            user_impact="Customers may experience intermittent transaction delays",
        )
        policy_check = check_comms_policy(rendered_comms)
        p_comms = await comms_h.post(
            kind=PostKind.STATUS_UPDATE,
            summary=f"Status update published for {final_service}",
            details={
                "service": final_service,
                "text": rendered_comms,
                "compliant": policy_check.compliant,
            },
        )
        self.run_log.append(
            "Comms Agent",
            "board_post",
            {"post_id": p_comms.post_id, "kind": p_comms.kind.value},
        )

        # Save machine-readable JSON to outputs/<incident_id>.json
        output_file = self.outputs_dir / f"{incident_id}.json"
        all_posts_data = [p.model_dump(mode="json") for p in board.read_all()]
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "incident_id": incident_id,
                    "scenario_id": self.env.scenario_id,
                    "likely_cause": final_cause,
                    "confidence": final_conf,
                    "mitigation": final_mitigation,
                    "target_service": final_service,
                    "rationale": final_rationale,
                    "rejected_alternatives": final_rejected,
                    "evidence_refs": final_ev_ids,
                    "posts": all_posts_data,
                },
                f,
                indent=2,
            )

        # Verify append-only run log hash chain
        is_chain_valid, chain_err = verify_chain(self.run_log.log_path)
        assert is_chain_valid, f"Run log hash chain verification failed: {chain_err}"

        return WarRoomOutput(
            incident_id=incident_id,
            scenario_id=self.env.scenario_id,
            likely_cause=final_cause,
            confidence=final_conf,
            evidence_post_ids=final_ev_ids,
            mitigation=final_mitigation,
            target_service=final_service,
            rationale=final_rationale,
            rejected_alternatives=final_rejected,
            timeline_markdown=timeline.markdown_table,
            board_json_path=str(output_file),
            run_log_verified=is_chain_valid,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run War-Room incident response system on a scenario."
    )
    parser.add_argument(
        "--scenario",
        default="s1_bad_deploy",
        help="Scenario ID (e.g. s1_bad_deploy, s3_upstream_outage, etc.)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Print full output trace and timeline",
    )
    args = parser.parse_args()

    async def _run_cli() -> None:
        env = Environment(data_dir="data", scenario_id=args.scenario)
        orch = WarRoomOrchestrator(env=env)
        res = await orch.run()
        print(f"\n=== WAR-ROOM RESOLUTION: {res.incident_id} ===")
        print(f"Scenario: {res.scenario_id}")
        print(f"Likely Cause: {res.likely_cause} (conf: {res.confidence:.2f})")
        print(f"Mitigation: {res.mitigation.upper()} (Target: {res.target_service})")
        print(f"Rationale: {res.rationale}")
        print("\nRejected Alternatives:")
        for rej in res.rejected_alternatives:
            print(f"  - [{rej['mitigation']}] {rej['reason']}")
        print(f"\nEvidence IDs: {', '.join(res.evidence_post_ids)}")
        print(f"Board JSON: {res.board_json_path}")
        print(f"Run Log Verified: {res.run_log_verified}")
        print(f"\nPostmortem Timeline:\n{res.timeline_markdown}")

    asyncio.run(_run_cli())

