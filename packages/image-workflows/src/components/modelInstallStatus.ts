import type { ModelInstallStatus } from "@gameknife/shared-types";
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

export function readModelInstallPresentation(status: ModelInstallStatus | null): ModelInstallPresentation {
  const installed = Boolean(status?.installed ?? status?.status === "success");
  const progress = status?.progress ?? (installed ? 100 : 0);
  if (installed) {
    return {
      label: "已安装",
      tone: "success",
      busy: false,
      installed: true,
      progress,
      message: status?.message || "模型文件已安装。",
      error: "",
      installBlocked: true,
    };
  }

  switch (status?.status) {
    case "running":
      return { label: "安装中", tone: "info", busy: true, installed: false, progress, message: status.message, error: status.error ?? "", installBlocked: true };
    case "failed":
      return { label: "安装失败", tone: "danger", busy: false, installed: false, progress, message: status.message, error: status.error ?? "", installBlocked: false };
    case "unavailable":
      return { label: "服务不可用", tone: "danger", busy: false, installed: false, progress, message: status.message, error: status.error ?? "", installBlocked: true };
    case "unconfigured":
      return { label: "未配置", tone: "warning", busy: false, installed: false, progress, message: status.message, error: status.error ?? "", installBlocked: false };
    case "success":
      return { label: "已安装", tone: "success", busy: false, installed: true, progress: 100, message: status.message, error: "", installBlocked: true };
    case "idle":
    default:
      return {
        label: "未安装",
        tone: "neutral",
        busy: false,
        installed: false,
        progress,
        message: status?.message || "尚未手动安装。",
        error: status?.error ?? "",
        installBlocked: false,
      };
  }
}
