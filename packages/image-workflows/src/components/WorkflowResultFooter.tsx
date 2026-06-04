import type { ReactNode } from "react";
import type { JobResponse } from "@gameknife/shared-types";
import { FailureDialog } from "./FailureDialog";
import { JobResult } from "./JobResult";
import { RecentJobs } from "../pages/jobs/RecentJobs";
import type { FailureDialogState } from "../types/failure";

interface WorkflowResultFooterProps {
  job: JobResponse | null;
  refreshKey: string;
  failureDialog: FailureDialogState | null;
  onCloseFailure: () => void;
  children?: ReactNode;
}

export function WorkflowResultFooter({ job, refreshKey, failureDialog, onCloseFailure, children }: WorkflowResultFooterProps) {
  return (
    <>
      <section className="workspace-result-panel">
        {children}
        <JobResult job={job} />
      </section>
      <RecentJobs refreshKey={refreshKey} />
      {failureDialog ? <FailureDialog dialog={failureDialog} onClose={onCloseFailure} /> : null}
    </>
  );
}
