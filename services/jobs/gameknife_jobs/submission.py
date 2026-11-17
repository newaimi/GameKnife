from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from gameknife_core import JobRecord


@dataclass(frozen=True, slots=True)
class TaskSubmission:
    """Request-scoped commercial submission identifiers; both remain optional for Community."""

    idempotency_key: str | None = None
    quote_id: str | None = None
    request_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "idempotency_key", _normalize_optional_identifier(self.idempotency_key, "idempotency_key"))
        object.__setattr__(self, "quote_id", _normalize_optional_identifier(self.quote_id, "quote_id"))
        object.__setattr__(self, "request_digest", _normalize_optional_digest(self.request_digest))


@dataclass(frozen=True, slots=True)
class JobSubmissionResult:
    """The persisted job returned by submission and whether an earlier request created it."""

    job: JobRecord
    replayed: bool = False


def bind_task_submission_request(
    submission: TaskSubmission,
    *,
    method: str,
    path: str,
    body: bytes,
) -> TaskSubmission:
    """Bind submission identifiers to the client-visible HTTP request.

    The digest intentionally excludes server snapshots such as Sequence revision and
    canvas capacity. A retry can therefore replay the accepted Job before mutable
    resource validation, while a different path, body, or quote still conflicts.
    """

    normalized_method = str(method or "").strip().upper()
    normalized_path = str(path or "").strip()
    if not normalized_method or not normalized_path.startswith("/"):
        raise ValueError("request method and absolute path are required")
    payload: dict[str, Any] = {
        "method": normalized_method,
        "path": normalized_path,
        "body": _canonical_request_body(body),
        "quote_id": submission.quote_id,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return TaskSubmission(
        idempotency_key=submission.idempotency_key,
        quote_id=submission.quote_id,
        request_digest=hashlib.sha256(encoded).hexdigest(),
    )


def _normalize_optional_identifier(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string when provided")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty when provided")
    return normalized


def _normalize_optional_digest(value: str | None) -> str | None:
    normalized = _normalize_optional_identifier(value, "request_digest")
    if normalized is None:
        return None
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized.lower()):
        raise ValueError("request_digest must be a SHA-256 hex digest")
    return normalized.lower()


def _canonical_request_body(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Invalid JSON is rejected later by FastAPI. Hashing raw bytes here keeps the
        # dependency deterministic without turning parsing failures into a replay.
        return {"raw_sha256": hashlib.sha256(body).hexdigest()}
