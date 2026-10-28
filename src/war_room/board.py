"""Incident Board (Blackboard) implementation.

Append-only, concurrency-safe, author-bound blackboard coordinating all agent
investigation findings, mitigation proposals, and incident commander decisions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PostKind(StrEnum):
    """Allowed post types on the Incident Board."""

    INCIDENT_SIGNAL = "incident_signal"
    LOG_FINDING = "log_finding"
    DEPENDENCY_FINDING = "dependency_finding"
    MITIGATION_PROPOSAL = "mitigation_proposal"
    EVIDENCE_REQUEST = "evidence_request"
    DECISION = "decision"
    TIMELINE_ENTRY = "timeline_entry"
    ESCALATION = "escalation"
    STATUS_UPDATE = "status_update"
    TOOL_FAILURE = "tool_failure"
    SECURITY_NOTE = "security_note"


class Post(BaseModel):
    """Immutable entry on the blackboard."""

    post_id: str = Field(description="Unique identifier, e.g. P-001")
    seq: int = Field(ge=1, description="Strictly monotonic sequence number")
    author: str = Field(description="Agent role or author identity")
    kind: PostKind = Field(description="Category of the blackboard post")
    summary: str = Field(description="Short human-readable summary of the finding/action")
    details: dict[str, Any] | str = Field(
        default_factory=dict, description="Structured or raw payload"
    )
    evidence_refs: list[str] = Field(
        default_factory=list, description="Referenced post IDs justifying this post"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confidence score if applicable"
    )
    incident_time: datetime | None = Field(
        default=None, description="Timestamp of event in the target system"
    )
    posted_at: datetime = Field(description="War-room timestamp when posted")
    untrusted_flags: list[str] = Field(
        default_factory=list, description="Security flags if untrusted content detected"
    )

    model_config = ConfigDict(frozen=True)  # Enforces immutability of individual post instances


# Strict permission matrix mapping Author role to permitted PostKind types
AUTHOR_PERMISSIONS: dict[str, set[PostKind]] = {
    "Alert Agent": {PostKind.INCIDENT_SIGNAL, PostKind.SECURITY_NOTE},
    "Logs Agent": {PostKind.LOG_FINDING, PostKind.TOOL_FAILURE, PostKind.SECURITY_NOTE},
    "Dependency Agent": {
        PostKind.DEPENDENCY_FINDING,
        PostKind.TOOL_FAILURE,
        PostKind.SECURITY_NOTE,
    },
    "Mitigation Agent": {
        PostKind.MITIGATION_PROPOSAL,
        PostKind.TOOL_FAILURE,
        PostKind.SECURITY_NOTE,
    },
    "Incident Commander": {
        PostKind.DECISION,
        PostKind.EVIDENCE_REQUEST,
        PostKind.TIMELINE_ENTRY,
        PostKind.ESCALATION,
        PostKind.SECURITY_NOTE,
    },
    "Comms Agent": {PostKind.STATUS_UPDATE, PostKind.SECURITY_NOTE},
}


class PermissionError(Exception):
    """Raised when an agent attempts to publish a forbidden post kind."""


class IncidentBoard:
    """Shared append-only blackboard for an incident war-room."""

    def __init__(
        self,
        incident_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.incident_id = incident_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._posts: list[Post] = []
        self._lock = asyncio.Lock()
        self._seq_counter = 0

    @property
    def posts(self) -> list[Post]:
        """Return a copy of all posts in chronological sequence."""
        return list(self._posts)

    def read_all(self) -> list[Post]:
        """Read all posts currently on the board."""
        return list(self._posts)

    def read_by_kind(self, kind: PostKind | str) -> list[Post]:
        """Read posts matching a specific kind."""
        target_kind = PostKind(kind) if isinstance(kind, str) else kind
        return [p for p in self._posts if p.kind == target_kind]

    def get_post(self, post_id: str) -> Post | None:
        """Find a post by its post_id."""
        for p in self._posts:
            if p.post_id == post_id:
                return p
        return None

    async def post(
        self,
        author: str,
        kind: PostKind | str,
        summary: str,
        details: dict[str, Any] | str | None = None,
        evidence_refs: list[str] | None = None,
        confidence: float | None = None,
        incident_time: datetime | None = None,
        untrusted_flags: list[str] | None = None,
    ) -> Post:
        """Publish a new post to the blackboard under strict concurrency control."""
        target_kind = PostKind(kind) if isinstance(kind, str) else kind

        # Validate author permissions
        allowed_kinds = AUTHOR_PERMISSIONS.get(author)
        if allowed_kinds is None:
            # Fallback: unrecognized author can only post security notes
            if target_kind != PostKind.SECURITY_NOTE:
                raise PermissionError(
                    f"Unregistered agent '{author}' cannot post {target_kind.value}"
                )
        elif target_kind not in allowed_kinds:
            raise PermissionError(f"Agent '{author}' is not permitted to post {target_kind.value}")

        async with self._lock:
            self._seq_counter += 1
            seq = self._seq_counter
            post_id = f"P-{seq:03d}"
            posted_at = self._clock()

            new_post = Post(
                post_id=post_id,
                seq=seq,
                author=author,
                kind=target_kind,
                summary=summary,
                details=details if details is not None else {},
                evidence_refs=list(evidence_refs) if evidence_refs else [],
                confidence=confidence,
                incident_time=incident_time,
                posted_at=posted_at,
                untrusted_flags=list(untrusted_flags) if untrusted_flags else [],
            )
            self._posts.append(new_post)
            return new_post

    def get_handle(self, author: str) -> BoardHandle:
        """Create an author-bound handle to interact with the board."""
        return BoardHandle(board=self, author=author)


class BoardHandle:
    """An agent's author-bound handle to the Incident Board.

    Guarantees the agent cannot forge another author's identity.
    """

    def __init__(self, board: IncidentBoard, author: str) -> None:
        self._board = board
        self._author = author

    @property
    def author(self) -> str:
        return self._author

    @property
    def incident_id(self) -> str:
        return self._board.incident_id

    def read_all(self) -> list[Post]:
        """Read all posts on the board."""
        return self._board.read_all()

    def read_by_kind(self, kind: PostKind | str) -> list[Post]:
        """Read posts by kind."""
        return self._board.read_by_kind(kind)

    def get_post(self, post_id: str) -> Post | None:
        """Look up a specific post by ID."""
        return self._board.get_post(post_id)

    async def post(
        self,
        kind: PostKind | str,
        summary: str,
        details: dict[str, Any] | str | None = None,
        evidence_refs: list[str] | None = None,
        confidence: float | None = None,
        incident_time: datetime | None = None,
        untrusted_flags: list[str] | None = None,
    ) -> Post:
        """Post to the board using the bound author identity."""
        return await self._board.post(
            author=self._author,
            kind=kind,
            summary=summary,
            details=details,
            evidence_refs=evidence_refs,
            confidence=confidence,
            incident_time=incident_time,
            untrusted_flags=untrusted_flags,
        )
