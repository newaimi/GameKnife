import { useCallback } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { ModelInstallStatus } from "@gameknife/shared-types";

export type RequiredModel = "birefnet" | "upscale" | "stable-audio";

const MODEL_LABEL: Record<RequiredModel, string> = {
  birefnet: "BiRefNet",
  upscale: "图片放大",
  "stable-audio": "Stable Audio",
};

export function useModelRequirement() {
  return useCallback(async (model: RequiredModel) => {
    try {
      const status = await readInstallStatus(model);
      if (isInstalled(status)) {
        return true;
      }
      openSettingsForModel(model);
      return false;
    } catch {
      // 状态接口失败时继续让创建任务请求给出最终错误，避免网络抖动把本可执行的本地任务直接拦住。
      return true;
    }
  }, []);
}

function isInstalled(status: ModelInstallStatus) {
  return Boolean(status.installed ?? status.status === "success");
}

function readInstallStatus(model: RequiredModel): Promise<ModelInstallStatus> {
  switch (model) {
    case "upscale":
      return gameKnifeApiClient.getUpscaleModelInstallStatus();
    case "stable-audio":
      return gameKnifeApiClient.getStableAudioInstallStatus();
    case "birefnet":
    default:
      return gameKnifeApiClient.getBiRefNetInstallStatus();
  }
}

function openSettingsForModel(model: RequiredModel) {
  window.sessionStorage.setItem("gameknife-model-settings-message", `需要先下载安装 ${MODEL_LABEL[model]} 模型文件。`);
  window.location.href = "/settings";
}
