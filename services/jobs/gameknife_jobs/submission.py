from __future__ import annotations

from dataclasses import dataclass

from gameknife_core import JobRecord


@dataclass(frozen=True, slots=True)
class TaskSubmission:
    """Request-scoped commercial submission identifiers; both remain optional for Community."""

    idempotency_key: str | None = None
    quote_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "idempotency_key", _normalize_optional_identifier(self.idempotency_key, "idempotency_key"))
        object.__setattr__(self, "quote_id", _normalize_optional_identifier(self.quote_id, "quote_id"))


@dataclass(frozen=True, slots=True)
class JobSubmissionResult:
    """The persisted job returned by submission and whether an earlier request created it."""

    job: JobRecord
    replayed: bool = False


def _normalize_optional_identifier(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string when provided")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty when provided")
    return normalized
