import type { JobStatus } from "@gameknife/shared-types";
import { useTranslation } from "react-i18next";
import { StatusBadge } from "@gameknife/ui-kit";
import { readJobStatusPresentation } from "./jobStatus";

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { t } = useTranslation("jobs");
  const presentation = readJobStatusPresentation(status, t);
  return (
    <StatusBadge tone={presentation.tone} busy={presentation.busy} aria-label={t("presentation.statusLabel", { status: presentation.label })}>
      {presentation.label}
    </StatusBadge>
  );
}
