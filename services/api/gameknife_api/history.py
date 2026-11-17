from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class JobHistoryConfiguration:
    """Job groups exposed by one product assembly through the shared history route."""

    downloadable_job_types: tuple[str, ...]
    task_center_job_types: tuple[str, ...]
    category_job_types: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "category_job_types",
            MappingProxyType(
                {
                    category: tuple(job_types)
                    for category, job_types in self.category_job_types.items()
                }
            ),
        )

    def extend(
        self,
        *,
        downloadable_job_types: tuple[str, ...] = (),
        task_center_job_types: tuple[str, ...] = (),
        category_job_types: Mapping[str, tuple[str, ...]] | None = None,
    ) -> JobHistoryConfiguration:
        """Return a product-specific configuration without mutating public defaults."""

        merged_categories = dict(self.category_job_types)
        for category, job_types in (category_job_types or {}).items():
            merged_categories[category] = tuple(job_types)
        return JobHistoryConfiguration(
            downloadable_job_types=tuple(
                dict.fromkeys((*self.downloadable_job_types, *downloadable_job_types))
            ),
            task_center_job_types=tuple(
                dict.fromkeys((*self.task_center_job_types, *task_center_job_types))
            ),
            category_job_types=merged_categories,
        )


COMMUNITY_JOB_HISTORY_CONFIGURATION = JobHistoryConfiguration(
    downloadable_job_types=(
        "background_remove",
        "asset_board_cutout",
        "asset_board_export",
        "sequence_export_frames",
        "sequence_export_spine",
        "image_upscale",
        "sound_effect_generate",
        "project_export_package",
    ),
    task_center_job_types=(
        "background_remove",
        "asset_board_cutout",
        "asset_board_export",
        "asset_quality_check",
        "image_upscale",
        "sequence_clean",
        "sequence_video_to_frames",
        "sequence_export_frames",
        "sequence_export_spine",
        "sound_effect_generate",
        "project_export_package",
    ),
    category_job_types={
        "background": ("background_remove",),
        "upscale": ("image_upscale",),
        "sound": ("sound_effect_generate",),
        "asset_board": (
            "asset_board_region_detect",
            "asset_board_cutout",
            "asset_board_region_refine",
            "asset_board_export",
        ),
        "quality": ("asset_quality_check",),
        "sequence": (
            "sequence_clean",
            "sequence_video_to_frames",
            "sequence_export_frames",
            "sequence_export_spine",
        ),
        "export": ("project_export_package",),
    },
)
