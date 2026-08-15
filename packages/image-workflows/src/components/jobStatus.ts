import type { JobStatus } from "@gameknife/shared-types";
import type { StatusTone } from "@gameknife/ui-kit";

export function readJobStatusPresentation(status: JobStatus): { label: string; tone: StatusTone; busy: boolean } {
  switch (status) {
    case "running":
      return { label: "处理中", tone: "info", busy: true };
    case "success":
      return { label: "已完成", tone: "success", busy: false };
    case "failed":
      return { label: "失败", tone: "danger", busy: false };
    case "pending":
    default:
      return { label: "等待中", tone: "warning", busy: true };
  }
}
