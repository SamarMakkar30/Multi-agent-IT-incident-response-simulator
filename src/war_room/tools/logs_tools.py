"""Domain tools for the Logs Agent."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from war_room.environment import Environment
from war_room.guards import sanitize_untrusted_input


class LogEntry(BaseModel):
    """Sanitized log entry."""

    timestamp: str = Field(description="Timestamp of the log line")
    level: str = Field(description="Log severity level (INFO, WARN, ERROR, CRITICAL)")
    service: str = Field(description="Emitting service")
    message: str = Field(description="Sanitized log message")
    signature: str | None = Field(default=None, description="Exception or error signature")
    untrusted_flags: list[str] = Field(default_factory=list, description="Security flags")


class LogSearchResult(BaseModel):
    """Outcome of log search query."""

    service: str = Field(description="Queried service")
    query: str = Field(description="Search filter applied")
    match_count: int = Field(description="Total matching records found")
    entries: list[LogEntry] = Field(description="Retrieved log entries")
    untrusted_flags: list[str] = Field(default_factory=list, description="Aggregated flags")


class ErrorSignatureSummary(BaseModel):
    """Clustered exception signature summary."""

    signature: str = Field(description="Exception or failure signature")
    count: int = Field(description="Number of occurrences")
    first_seen: str = Field(description="Earliest timestamp observed")
    last_seen: str = Field(description="Most recent timestamp observed")
    sample_message: str = Field(description="Representative message excerpt")


class ErrorOnsetInfo(BaseModel):
    """Information identifying the onset of an error condition."""

    service: str = Field(description="Service name")
    signature: str = Field(description="Error signature")
    onset_timestamp: str | None = Field(description="First recorded appearance of the error")
    preceding_log_count: int = Field(description="Normal log count prior to onset")


def search_logs(
    env: Environment,
    service_name: str,
    query: str = "",
    time_window_minutes: int = 30,
) -> LogSearchResult:
    """Search service application logs within a sliding time window before simulated now."""
    raw_logs = env.get_logs(
        service_name=service_name,
        query=query if query else None,
        time_window_minutes=time_window_minutes,
    )

    entries = []
    aggregated_flags = set()

    for item in raw_logs:
        raw_msg = str(item.get("message", ""))
        sanitized_msg, flags = sanitize_untrusted_input(raw_msg)
        for flag in flags:
            aggregated_flags.add(flag)

        entries.append(
            LogEntry(
                timestamp=str(item.get("timestamp", "")),
                level=str(item.get("level", "INFO")),
                service=str(item.get("service", service_name)),
                message=sanitized_msg,
                signature=item.get("signature"),
                untrusted_flags=flags,
            )
        )

    return LogSearchResult(
        service=service_name,
        query=query,
        match_count=len(entries),
        entries=entries,
        untrusted_flags=sorted(aggregated_flags),
    )


def summarize_error_signatures(
    env: Environment,
    service_name: str,
    time_window_minutes: int = 60,
) -> list[ErrorSignatureSummary]:
    """Aggregate and cluster error signatures by frequency and time span."""
    raw_logs = env.get_logs(service_name=service_name, time_window_minutes=time_window_minutes)

    sig_counts: Counter[str] = Counter()
    sig_first: dict[str, str] = {}
    sig_last: dict[str, str] = {}
    sig_sample: dict[str, str] = {}

    for item in raw_logs:
        if item.get("level") in ("ERROR", "CRITICAL") or item.get("signature"):
            sig = str(item.get("signature") or item.get("message", "UnknownError")[:60])
            ts = str(item.get("timestamp", ""))
            sig_counts[sig] += 1
            if sig not in sig_first:
                sig_first[sig] = ts
                sig_sample[sig], _ = sanitize_untrusted_input(str(item.get("message", "")))
            sig_last[sig] = ts

    summaries = []
    for sig, count in sig_counts.most_common():
        summaries.append(
            ErrorSignatureSummary(
                signature=sig,
                count=count,
                first_seen=sig_first[sig],
                last_seen=sig_last[sig],
                sample_message=sig_sample[sig],
            )
        )
    return summaries


def find_error_onset(
    env: Environment,
    service_name: str,
    error_signature: str,
) -> ErrorOnsetInfo:
    """Locate the exact onset timestamp when an error signature first appeared."""
    raw_logs = env.get_logs(service_name=service_name, time_window_minutes=120)

    onset_ts = None
    preceding_count = 0

    for item in raw_logs:
        sig = item.get("signature", "")
        msg = item.get("message", "")
        if (
            error_signature.lower() in str(sig).lower()
            or error_signature.lower() in str(msg).lower()
        ):
            onset_ts = str(item.get("timestamp", ""))
            break
        preceding_count += 1

    return ErrorOnsetInfo(
        service=service_name,
        signature=error_signature,
        onset_timestamp=onset_ts,
        preceding_log_count=preceding_count,
    )
