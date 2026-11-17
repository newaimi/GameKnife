import type { ModelInstallStatus } from "@gameknife/shared-types";
import type { TFunction } from "@gameknife/i18n";
import type { StatusTone } from "@gameknife/ui-kit";

export type ModelInstallPresentation = {
  label: string;
  tone: StatusTone;
  busy: boolean;
  installed: boolean;
  progress: number;
  message: string;
  error: string;
  installBlocked: boolean;
};

export function readModelInstallPresentation(status: ModelInstallStatus | null, t: TFunction): ModelInstallPresentation {
  const installed = Boolean(status?.installed ?? status?.status === "success");
  const progress = status?.progress ?? (installed ? 100 : 0);
  if (installed) {
    return {
      label: t("install.installed"),
      tone: "success",
      busy: false,
      installed: true,
      progress,
      message: t("install.installedMessage"),
      error: "",
      installBlocked: true,
    };
  }

  switch (status?.status) {
    case "running":
      return { label: t("install.installing"), tone: "info", busy: true, installed: false, progress, message: t("install.installingMessage"), error: status.error ?? "", installBlocked: true };
    case "failed":
      return { label: t("install.failed"), tone: "danger", busy: false, installed: false, progress, message: t("install.failedMessage"), error: status.error ?? "", installBlocked: false };
    case "unavailable":
      return { label: t("install.unavailable"), tone: "danger", busy: false, installed: false, progress, message: t("install.unavailableMessage"), error: status.error ?? "", installBlocked: true };
    case "unconfigured":
      return { label: t("install.unconfigured"), tone: "warning", busy: false, installed: false, progress, message: t("install.unconfiguredMessage"), error: status.error ?? "", installBlocked: false };
    case "success":
      return { label: t("install.installed"), tone: "success", busy: false, installed: true, progress: 100, message: t("install.installedMessage"), error: "", installBlocked: true };
    case "idle":
    default:
      return {
        label: t("install.notInstalled"),
        tone: "neutral",
        busy: false,
        installed: false,
        progress,
        message: t("install.notInstalledMessage"),
        error: status?.error ?? "",
        installBlocked: false,
      };
  }
}
