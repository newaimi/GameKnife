import type { JobResponse } from "@gameknife/shared-types";

export function readJobRetryRoute(job: JobResponse): string | null {
  if (job.type === "background_remove") return "/tools/background-remove";
  if (job.type === "image_upscale") return "/tools/upscale";
  if (job.type === "asset_board_cutout" || job.type === "asset_board_export") return "/tools/asset-board";
  if (job.type === "sequence_generate_video") return "/tools/video-generate";
  if (job.type === "sequence_video_to_frames") return "/tools/video-to-sequence";
  if (job.type === "sound_effect_generate") return "/tools/sound-effect";
  if (job.type === "project_export_package") return "/assets";
  if (job.type.startsWith("sequence_")) {
    const sequenceId = typeof job.parameters.sequence_id === "string" ? job.parameters.sequence_id : "";
    return sequenceId ? `/tools/sequence?sequence=${encodeURIComponent(sequenceId)}` : "/tools/sequence";
  }
  return null;
}
