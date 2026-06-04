import { useEffect, useState } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { RuntimeSettings, VideoGenerationConfig } from "@gameknife/shared-types";

export type WorkflowDeviceSource = "birefnet" | "upscale" | "character-rig" | "stable-audio" | "video-generation";

const UNKNOWN_DEVICE = "未知";

export function useWorkflowDevice(source: WorkflowDeviceSource) {
  const [device, setDevice] = useState(UNKNOWN_DEVICE);

  useEffect(() => {
    let alive = true;

    gameKnifeApiClient
      .getSettings()
      .then((settings) => {
        if (alive) {
          setDevice(readWorkflowDevice(settings, source));
        }
      })
      .catch(() => {
        if (alive) {
          setDevice(UNKNOWN_DEVICE);
        }
      });

    return () => {
      alive = false;
    };
  }, [source]);

  return device;
}

function readWorkflowDevice(settings: RuntimeSettings, source: WorkflowDeviceSource) {
  switch (source) {
    case "upscale":
      return settings.upscale_models.device || UNKNOWN_DEVICE;
    case "character-rig":
      return settings.character_rig_models.device || UNKNOWN_DEVICE;
    case "stable-audio":
      return settings.stable_audio.device || UNKNOWN_DEVICE;
    case "video-generation":
      // 视频生成走外部 API，没有本地推理设备；这里展示 settings 中的供应商，避免硬编码 Community 造成误导。
      return formatVideoGenerationProvider(settings.video_generation.provider);
    case "birefnet":
    default:
      return settings.birefnet.device || UNKNOWN_DEVICE;
  }
}

function formatVideoGenerationProvider(provider: VideoGenerationConfig["provider"]) {
  if (provider === "seedance") {
    return "Seedance";
  }
  return "DashScope";
}
