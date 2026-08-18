import { useCallback } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { ModelInstallStatus } from "@gameknife/shared-types";

export type RequiredModel = "birefnet" | "upscale" | "stable-audio";

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
      // Let the job request provide the final error if the status endpoint fails. A transient status request must
      // not block a model that may already be usable.
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
  window.sessionStorage.setItem("gameknife-required-model", model);
  window.location.href = "/settings";
}
