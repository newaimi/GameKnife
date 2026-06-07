import type { JobResponse } from "@gameknife/shared-types";
import { formatJobStatus } from "../utils/jobPresentation";

export function StatusLine({ error, job }: { error: string; job: JobResponse | null }) {
  if (error) {
    return <p className="error-text">{error}</p>;
  }
  if (!job) {
    return null;
  }
  return <span className="status-text">{formatJobStatus(job.status)}</span>;
}
