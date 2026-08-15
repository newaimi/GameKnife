import type { JobStatus } from "@gameknife/shared-types";
import { StatusBadge } from "@gameknife/ui-kit";
import { readJobStatusPresentation } from "./jobStatus";

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const presentation = readJobStatusPresentation(status);
  return (
    <StatusBadge tone={presentation.tone} busy={presentation.busy} aria-label={`任务状态：${presentation.label}`}>
      {presentation.label}
    </StatusBadge>
  );
}
