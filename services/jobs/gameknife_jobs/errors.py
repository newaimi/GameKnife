from __future__ import annotations

from gameknife_core import AssetReferenceSummary


class AssetWriteInProgressError(RuntimeError):
    """Raised when another request owns the pending write for the same Asset ID."""

    def __init__(self, asset_id: str) -> None:
        self.asset_id = asset_id
        super().__init__(f"Asset {asset_id} is currently being stored.")


class InvalidJobStateTransitionError(RuntimeError):
    """Raised when a job update would replace or bypass an established state."""

    def __init__(self, job_id: str, current_status: str, requested_status: str) -> None:
        self.job_id = job_id
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(f"Job {job_id} cannot transition from {current_status} to {requested_status}.")


class JobDeliveryRequirementError(RuntimeError):
    """Raised when a job has not persisted the delivery required for success."""

    def __init__(self, job_id: str, job_type: str) -> None:
        self.job_id = job_id
        self.job_type = job_type
        super().__init__(f"Job {job_id} does not satisfy the delivery requirement for job type {job_type}.")


class SequenceActiveJobError(RuntimeError):
    """Raised when a user mutation targets a sequence claimed by a running job."""

    def __init__(self, sequence_id: str) -> None:
        self.sequence_id = sequence_id
        super().__init__(f"Sequence {sequence_id} is currently being processed.")


class ResourceReferenceError(RuntimeError):
    """Raised when deletion would remove a resource that is still in use."""

    def __init__(
        self,
        resource_kind: str,
        resource_id: str,
        references: tuple[AssetReferenceSummary, ...],
    ) -> None:
        self.resource_kind = resource_kind
        self.resource_id = resource_id
        self.references = references
        super().__init__(f"{resource_kind} {resource_id} is still referenced.")
