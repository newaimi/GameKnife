import type { JobResponse } from "@gameknife/shared-types";
import type { TFunction } from "@gameknife/i18n";
import { readFirstJobOutputAsset } from "./jobs";

export interface JobPresentationOverride {
  title?: string;
  initial?: string;
  displayName?: string;
  thumbnailPath?: string;
  fileMeta?: string;
  retryRoute?: string | null;
}

export type JobPresentationResolver = (
  job: JobResponse,
) => JobPresentationOverride | null;

export function readJobTitle(job: JobResponse, t: TFunction) {
  const titleMap: Record<string, string> = {
    background_remove: "types.backgroundRemove",
    image_upscale: "types.imageUpscale",
    asset_board_region_detect: "types.assetBoardRegionDetect",
    asset_board_cutout: "types.assetBoardCutout",
    asset_board_region_refine: "types.assetBoardRegionRefine",
    asset_board_export: "types.assetBoardExport",
    asset_quality_check: "types.assetQualityCheck",
    sequence_clean: "types.sequenceClean",
    sequence_video_to_frames: "types.sequenceVideoToFrames",
    sequence_export_frames: "types.sequenceExportFrames",
    sequence_export_spine: "types.sequenceExportSpine",
    sound_effect_generate: "types.soundEffectGenerate",
  };
  const key = titleMap[job.type];
  return key ? t(key) : job.type.includes("export") ? t("types.componentExport") : job.type;
}

export function readJobInitial(job: JobResponse, t: TFunction) {
  if (job.type === "asset_quality_check") return t("initials.quality");
  if (job.type === "sound_effect_generate") return t("initials.sound");
  if (job.type === "sequence_video_to_frames") return t("initials.video");
  if (job.type.includes("sequence")) return t("initials.frame");
  if (job.type === "image_upscale") return t("initials.upscale");
  return job.type.includes("asset") ? t("initials.board") : t("initials.image");
}

export function readJobDisplayName(job: JobResponse, t: TFunction) {
  if (job.type === "sound_effect_generate") {
    const prompt = readString(job.result.prompt).trim();
    if (prompt) return prompt.length > 36 ? `${prompt.slice(0, 36)}...` : prompt;
    return t("types.soundEffectGenerate");
  }
  return job.input_filename ?? readJobTitle(job, t);
}

export function readJobThumbnailPath(job: JobResponse) {
  if (job.type === "sound_effect_generate") return "";
  const firstOutputAsset = readFirstJobOutputAsset(job);
  if ((job.type === "background_remove" || job.type === "image_upscale") && firstOutputAsset?.url) {
    return firstOutputAsset.url;
  }
  return readString(job.result.cutout_url) || readString(job.result.input_asset_url);
}

export function formatJobFileMeta(job: JobResponse, t: TFunction) {
  if (job.type === "sound_effect_generate") {
    return `WAV · ${job.result.duration_seconds ?? job.parameters.duration_seconds ?? "-"}s`;
  }
  return `${formatJobFileType(job, t)} · ${formatFileSize(job.input_size_bytes ?? 0, t)}`;
}

export function formatJobStatus(status: JobResponse["status"], t: TFunction) {
  if (status === "success") return t("status.succeeded");
  if (status === "failed") return t("status.failed");
  return status === "running" ? t("status.running") : t("status.queued");
}

export function formatAbsoluteTime(value: string, language: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(language, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelativeTime(value: string, language: string, t: TFunction) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 60 * 1000) return t("presentation.justNow");
  if (diffMs < 60 * 60 * 1000) return t("presentation.minutesAgo", { count: Math.max(1, Math.round(diffMs / 60000)) });
  if (diffMs < 24 * 60 * 60 * 1000) return t("presentation.hoursAgo", { count: Math.max(1, Math.round(diffMs / 3600000)) });
  return formatAbsoluteTime(value, language);
}

function formatJobFileType(job: JobResponse, t: TFunction) {
  if (job.type === "sound_effect_generate") return "WAV";
  if ((job.type.includes("sequence") || job.type.includes("export")) && readFirstJobOutputAsset(job)) return "ZIP";
  const mimeType = job.input_mime_type ?? "";
  if (mimeType.includes("jpeg")) return "JPG";
  if (mimeType.includes("png")) return "PNG";
  if (mimeType.includes("webp")) return "WEBP";
  return t("presentation.image");
}

function formatFileSize(sizeBytes: number, t: TFunction) {
  if (!sizeBytes) return t("presentation.unknownSize");
  if (sizeBytes < 1024 * 1024) return `${Math.max(1, Math.round(sizeBytes / 1024))}KB`;
  return `${(sizeBytes / 1024 / 1024).toFixed(1)}MB`;
}

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}
