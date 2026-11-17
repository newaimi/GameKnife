from __future__ import annotations

import json

from gameknife_core import AssetRecord, JobRecord, RequestContext
from gameknife_jobs import GameKnifeRepository, ResourceReferenceError

from gameknife_api.schemas import AssetResponse, JobResponse


def build_asset_response(asset: AssetRecord) -> AssetResponse:
    """Build the stable API representation for one stored Asset."""

    return AssetResponse(
        id=asset.id,
        filename=asset.original_name,
        kind=asset.kind,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        storage_state=asset.storage_state,
        created_by=asset.created_by,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        url=f"/api/assets/{asset.id}",
    )


def build_job_response(
    job: JobRecord,
    context: RequestContext,
    repository: GameKnifeRepository,
) -> JobResponse:
    """Assemble a Job response from edition-neutral records and Asset links."""

    result = json.loads(job.result_json)
    input_asset = (
        repository.get_asset_for_workspace(job.input_asset_id, context.workspace.id)
        if job.input_asset_id is not None
        else None
    )
    if input_asset is not None:
        result.setdefault("input_asset_url", f"/api/assets/{input_asset.id}")
    input_assets = []
    for link in repository.list_job_input_assets_for_workspace(
        job.id,
        context.workspace.id,
    ):
        linked_asset = repository.get_asset_for_workspace(
            link.asset_id,
            context.workspace.id,
        )
        if linked_asset is not None:
            input_assets.append(
                {
                    "role": link.input_role,
                    "position": link.position,
                    "asset": build_asset_response(linked_asset),
                }
            )

    return JobResponse(
        id=job.id,
        type=job.job_type,
        status=job.status,  # type: ignore[arg-type]
        input_asset_id=job.input_asset_id,
        input_assets=input_assets,
        input_filename=input_asset.original_name if input_asset is not None else None,
        input_mime_type=input_asset.mime_type if input_asset is not None else None,
        input_size_bytes=input_asset.size_bytes if input_asset is not None else None,
        parameters=json.loads(job.parameters_json),
        result=result,
        device=job.device,
        duration_ms=job.duration_ms,
        error_message=job.error_message,
        error_code=(
            str(result["error_code"])
            if isinstance(result.get("error_code"), str) and result["error_code"]
            else "JOB_EXECUTION_FAILED" if job.status == "failed" else None
        ),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def build_resource_reference_detail(
    exc: ResourceReferenceError,
) -> dict[str, object]:
    """Preserve one structured deletion-conflict contract across product assemblies."""

    return {
        "code": "RESOURCE_REFERENCED",
        "message": "The resource is still used by a job, sequence, or derived asset and cannot be deleted.",
        "resource": {"kind": exc.resource_kind, "id": exc.resource_id},
        "references": [
            {
                "asset_id": reference.asset_id,
                "input_job_ids": list(reference.input_job_ids),
                "output_job_ids": list(reference.output_job_ids),
                "source_sequence_frame_ids": list(
                    reference.source_sequence_frame_ids
                ),
                "processed_sequence_frame_ids": list(
                    reference.processed_sequence_frame_ids
                ),
                "derived_asset_ids": list(reference.derived_asset_ids),
                "style_profile_ids": list(reference.style_profile_ids),
            }
            for reference in exc.references
        ],
    }
