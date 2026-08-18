import type { JobStatus } from "@gameknife/shared-types";
import type { StatusTone } from "@gameknife/ui-kit";
import type { TFunction } from "@gameknife/i18n";

export function readJobStatusPresentation(status: JobStatus, t: TFunction): { label: string; tone: StatusTone; busy: boolean } {
  switch (status) {
    case "running":
      return { label: t("status.running"), tone: "info", busy: true };
    case "success":
      return { label: t("status.succeeded"), tone: "success", busy: false };
    case "failed":
      return { label: t("status.failed"), tone: "danger", busy: false };
    case "pending":
    default:
      return { label: t("status.queued"), tone: "warning", busy: true };
  }
}
