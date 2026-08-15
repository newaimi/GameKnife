import type { JobResponse } from "@gameknife/shared-types";
import { FeedbackMessage } from "@gameknife/ui-kit";
import { JobStatusBadge } from "./JobStatusBadge";

export function StatusLine({ error, job }: { error: string; job: JobResponse | null }) {
  if (error) {
    return <FeedbackMessage className="workflow-status-message" tone="danger">{error}</FeedbackMessage>;
  }
  if (!job) {
    return null;
  }
  return <JobStatusBadge status={job.status} />;
}
