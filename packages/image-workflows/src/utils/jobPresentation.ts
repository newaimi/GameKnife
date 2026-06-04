import type { JobResponse } from "@gameknife/shared-types";
import { readFirstJobOutputAsset } from "./jobs";

export function readJobTitle(job: JobResponse) {
  const titleMap: Record<string, string> = {
    background_remove: "AI 去背景",
    image_upscale: "图片放大",
    asset_board_region_detect: "素材板区域识别",
    asset_board_cutout: "素材板抠图",
    asset_board_region_refine: "素材板框选刷新",
    asset_board_export: "素材板导出",
    sequence_clean: "序列帧清洗",
    sequence_generate_video: "视频生成",
    sequence_video_to_frames: "视频转序列帧",
    sequence_export_frames: "PNG 序列导出",
    sequence_export_spine: "Spine 导出",
    character_rig_analyze: "智能候选拆分",
    character_rig_refine_part: "骨骼部件精修",
    character_rig_export_spine: "Spine 骨骼导出",
    character_rig_export_dragonbones: "DragonBones 导出",
    sound_effect_generate: "声效生成",
  };
  return titleMap[job.type] ?? (job.type.includes("export") ? "组件导出" : job.type);
}

export function readJobInitial(job: JobResponse) {
  if (job.type === "sound_effect_generate") return "声";
  if (job.type.includes("character_rig")) return "骨";
  if (job.type === "sequence_generate_video" || job.type === "sequence_video_to_frames") return "视";
  if (job.type.includes("sequence")) return "帧";
  if (job.type === "image_upscale") return "放";
  return job.type.includes("asset") ? "板" : "图";
}

export function readJobDisplayName(job: JobResponse) {
  if (job.type === "sound_effect_generate") {
    const prompt = readString(job.result.prompt).trim();
    if (prompt) return prompt.length > 36 ? `${prompt.slice(0, 36)}...` : prompt;
    return "声效生成";
  }
  return job.input_filename ?? readJobTitle(job);
}

export function readJobThumbnailPath(job: JobResponse) {
  if (job.type === "sound_effect_generate") return "";
  const firstOutputAsset = readFirstJobOutputAsset(job);
  if ((job.type === "background_remove" || job.type === "image_upscale") && firstOutputAsset?.url) {
    return firstOutputAsset.url;
  }
  return readString(job.result.cutout_url) || readString(job.result.input_asset_url);
}

export function formatJobFileMeta(job: JobResponse) {
  if (job.type === "sound_effect_generate") {
    return `WAV · ${job.result.duration_seconds ?? job.parameters.duration_seconds ?? "-"}s`;
  }
  return `${formatJobFileType(job)} · ${formatFileSize(job.input_size_bytes ?? 0)}`;
}

export function formatJobStatus(status: JobResponse["status"]) {
  if (status === "success") return "已完成";
  if (status === "failed") return "失败";
  return status === "running" ? "处理中" : "等待中";
}

export function formatAbsoluteTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelativeTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 60 * 1000) return "刚刚";
  if (diffMs < 60 * 60 * 1000) return `${Math.max(1, Math.round(diffMs / 60000))}分钟前`;
  if (diffMs < 24 * 60 * 60 * 1000) return `${Math.max(1, Math.round(diffMs / 3600000))}小时前`;
  return formatAbsoluteTime(value);
}

function formatJobFileType(job: JobResponse) {
  if (job.type === "sound_effect_generate") return "WAV";
  if ((job.type.includes("character_rig") || job.type.includes("sequence") || job.type.includes("export")) && readFirstJobOutputAsset(job)) return "ZIP";
  const mimeType = job.input_mime_type ?? "";
  if (mimeType.includes("jpeg")) return "JPG";
  if (mimeType.includes("png")) return "PNG";
  if (mimeType.includes("webp")) return "WEBP";
  return "图片";
}

function formatFileSize(sizeBytes: number) {
  if (!sizeBytes) return "未知大小";
  if (sizeBytes < 1024 * 1024) return `${Math.max(1, Math.round(sizeBytes / 1024))}KB`;
  return `${(sizeBytes / 1024 / 1024).toFixed(1)}MB`;
}

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}
